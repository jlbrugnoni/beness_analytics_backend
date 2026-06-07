from collections import defaultdict
from datetime import date

from django.db import transaction

from analytics.models import MembershipMonthStatus
from core_data.models import ServicePurchase, ServicePurchaseVersion


def purchase_group_key(purchase):
    return (
        purchase.site_id,
        purchase.studio_id,
        purchase.client_id,
        purchase.pricing_option_id,
        purchase.sale_date,
        purchase.total_amount,
        purchase.quantity,
    )


def purchase_date_key(purchase):
    return purchase.activation_date, purchase.expiration_date


def audit_purchase_repairs(site_id=None):
    purchases = ServicePurchase.objects.select_related(
        "client",
        "pricing_option",
        "studio",
    ).prefetch_related("versions")
    if site_id:
        purchases = purchases.filter(site_id=site_id)

    groups = defaultdict(list)
    for purchase in purchases.order_by("id"):
        groups[purchase_group_key(purchase)].append(purchase)

    safe_groups = []
    ambiguous_groups = []
    for grouped_purchases in groups.values():
        if len(grouped_purchases) < 2:
            continue
        versions = [
            version
            for purchase in grouped_purchases
            for version in purchase.versions.all()
        ]
        versions_by_import = defaultdict(list)
        for version in versions:
            versions_by_import[version.report_import_id].append(version)

        summary = {
            "site_id": grouped_purchases[0].site_id,
            "studio": grouped_purchases[0].studio.name if grouped_purchases[0].studio else None,
            "client": grouped_purchases[0].client.name,
            "client_id": grouped_purchases[0].client_id,
            "service": grouped_purchases[0].pricing_option.name,
            "sale_date": grouped_purchases[0].sale_date.isoformat(),
            "amount": float(grouped_purchases[0].total_amount),
            "quantity": float(grouped_purchases[0].quantity),
            "purchase_ids": [purchase.id for purchase in grouped_purchases],
            "date_variants": sorted({
                (
                    purchase.activation_date.isoformat() if purchase.activation_date else None,
                    purchase.expiration_date.isoformat() if purchase.expiration_date else None,
                )
                for purchase in grouped_purchases
            }),
        }
        safe = (
            versions
            and len(versions_by_import) >= 2
            and all(len(import_versions) == 1 for import_versions in versions_by_import.values())
        )
        (safe_groups if safe else ambiguous_groups).append({
            **summary,
            "reason": (
                "One distinguishable purchase row per import."
                if safe
                else "Multiple indistinguishable rows occur in at least one import."
            ),
        })

    return {
        "safe_groups": safe_groups,
        "ambiguous_groups": ambiguous_groups,
        "safe_group_count": len(safe_groups),
        "ambiguous_group_count": len(ambiguous_groups),
        "safe_purchase_records_to_merge": sum(
            len(group["purchase_ids"]) - 1 for group in safe_groups
        ),
    }


@transaction.atomic
def apply_purchase_repairs(site_id=None):
    audit = audit_purchase_repairs(site_id=site_id)
    affected_ranges = {}
    merged_records = 0

    for group in audit["safe_groups"]:
        purchases = list(
            ServicePurchase.objects.select_for_update()
            .filter(id__in=group["purchase_ids"])
            .order_by("id")
        )
        if len(purchases) < 2:
            continue
        canonical = purchases[0]
        duplicates = purchases[1:]
        versions = list(
            ServicePurchaseVersion.objects.filter(
                service_purchase_id__in=group["purchase_ids"]
            ).order_by("created_at", "id")
        )
        latest_version = versions[-1]
        latest_purchase = next(
            purchase
            for purchase in purchases
            if purchase.id == latest_version.service_purchase_id
        )

        dates = [
            value
            for purchase in purchases
            for value in (purchase.activation_date or purchase.sale_date, purchase.expiration_date)
            if value
        ]
        current_range = affected_ranges.get(canonical.site_id)
        range_start = min(dates)
        range_end = max(dates)
        affected_ranges[canonical.site_id] = (
            min(current_range[0], range_start) if current_range else range_start,
            max(current_range[1], range_end) if current_range else range_end,
        )

        for field in (
            "studio",
            "current_row_hash",
            "client",
            "service_category",
            "pricing_option",
            "sale_date",
            "activation_date",
            "expiration_date",
            "activation_offset_days",
            "total_amount",
            "cash_equivalent",
            "non_cash_equivalent",
            "quantity",
            "last_seen_import",
            "source_raw_row",
        ):
            setattr(canonical, field, getattr(latest_purchase, field))
        canonical.save()

        ServicePurchaseVersion.objects.filter(
            service_purchase_id__in=[purchase.id for purchase in duplicates]
        ).update(service_purchase=canonical)
        MembershipMonthStatus.objects.filter(
            source_purchase_id__in=[purchase.id for purchase in duplicates]
        ).update(source_purchase=canonical)
        ServicePurchase.objects.filter(
            id__in=[purchase.id for purchase in duplicates]
        ).delete()
        merged_records += len(duplicates)

    return {
        **audit,
        "applied": True,
        "merged_purchase_records": merged_records,
        "affected_ranges": {
            str(site_id): {
                "from": range_values[0].isoformat(),
                "to": range_values[1].isoformat(),
            }
            for site_id, range_values in affected_ranges.items()
        },
    }
