"""Stable purchase updates and explicit review of uncertain imported rows."""
from collections import Counter
from datetime import date
from uuid import uuid4

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from .models import (
    PricingOption, ReportImport, ServiceCategory, ServicePurchase,
    ServicePurchaseMatchReview, ServicePurchaseVersion, Studio,
)


def attach_review_fingerprints(candidates):
    from .importers import hash_parts, service_purchase_snapshot

    counts = Counter()
    for candidate in candidates:
        snapshot = service_purchase_snapshot(candidate["payload"], candidate["related"])
        snapshot.pop("occurrence_index", None)
        # Reordering distinct date variants must not change a remembered decision.
        base = hash_parts([snapshot[key] for key in sorted(snapshot)])
        counts[base] += 1
        candidate["review_fingerprint"] = hash_parts([base, counts[base]])


def queue_purchase_review(candidate, reason):
    related = candidate["related"]
    review, created = ServicePurchaseMatchReview.objects.get_or_create(
        fingerprint=candidate["review_fingerprint"],
        defaults={
            "site": related["site"], "studio": related["studio"],
            "client": related["client"], "latest_raw_row": candidate["raw_row"],
            "reason": reason,
        },
    )
    if not created:
        review.latest_raw_row = candidate["raw_row"]
        # Do not overwrite the audit of a previous decision if its target vanished.
        review.status = "pending"
        review.reason = reason
        review.save(update_fields=["latest_raw_row", "status", "reason", "updated_at"])
    review.source_rows.add(candidate["raw_row"])
    return review


def apply_purchase_candidate(candidate, report_import, separate=False):
    from .importers import changed_fields, money, service_purchase_snapshot

    payload, related, raw_row = candidate["payload"], candidate["related"], candidate["raw_row"]
    purchase = candidate.get("service_purchase")
    previous_version = purchase.versions.order_by("-created_at", "-id").first() if purchase else None
    previous = previous_version.snapshot if previous_version else None
    snapshot = service_purchase_snapshot(payload, related)
    changes = changed_fields(previous, snapshot)
    values = {
        **related,
        "current_row_hash": candidate["row"]["hash"],
        "sale_date": payload["_sale_date"],
        "activation_date": payload.get("_activation_date"),
        "expiration_date": payload.get("_expiration_date"),
        "activation_offset_days": payload.get("_activation_offset_days"),
        "total_amount": money(payload.get("_total_amount")),
        "cash_equivalent": money(payload.get("_cash_equivalent")),
        "non_cash_equivalent": money(payload.get("_non_cash_equivalent")),
        "quantity": money(payload.get("_quantity")),
        "last_seen_import": report_import, "source_raw_row": raw_row,
    }
    if purchase is None:
        purchase = ServicePurchase.objects.create(
            # A manual separate-purchase decision must never steal another key.
            natural_key=uuid4().hex if separate else candidate["natural_key"],
            first_seen_import=report_import, **values,
        )
        outcome = "created"
    elif purchase.current_row_hash == candidate["row"]["hash"]:
        purchase.last_seen_import = report_import
        purchase.source_raw_row = raw_row
        purchase.save(update_fields=["last_seen_import", "source_raw_row", "updated_at"])
        outcome = "identical"
    else:
        # Keep the existing identity even if this export gives it a new ordinal.
        for field, value in values.items():
            setattr(purchase, field, value)
        purchase.save()
        outcome = "changed"
    version_count = int(bool(changes) or previous is None)
    if version_count:
        ServicePurchaseVersion.objects.create(
            service_purchase=purchase, report_import=report_import, raw_row=raw_row,
            row_hash=candidate["row"]["hash"], changed_fields=changes, snapshot=snapshot,
        )
    candidate["service_purchase"] = purchase
    return outcome, version_count


def candidate_from_review(review):
    from .importers import service_purchase_natural_key

    raw = review.latest_raw_row
    payload = raw.normalized_payload
    option = PricingOption.objects.filter(site=review.site, name=payload.get("Nombre")).first()
    category = ServiceCategory.objects.filter(site=review.site, name=payload.get("Categoría")).first()
    if not option:
        raise ValidationError("The pricing option no longer exists. Reimport the report before resolving this row.")
    return {
        "payload": payload, "raw_row": raw, "row": {"hash": raw.row_hash},
        "natural_key": service_purchase_natural_key(review.site, payload, review.studio),
        "related": {"site": review.site, "studio": review.studio, "client": review.client,
                    "pricing_option": option, "service_category": category},
    }


def rebuild_resolved_purchase_metrics(review, previous):
    """Rebuild old AND new coverage, including the following not-renewed month."""
    from analytics.models import MembershipMonthStatus
    from analytics.views import add_months, month_start, months_between, rebuild_membership_month
    from analytics.client_metrics import rebuild_client_metrics_after_import

    payload = review.latest_raw_row.normalized_payload
    dates = [date.fromisoformat(payload[key]) for key in ("_sale_date", "_activation_date", "_expiration_date") if payload.get(key)]
    dates.extend(value for value in previous if value)
    start = month_start(min(dates))
    end = add_months(month_start(max(dates)), 1)
    latest = MembershipMonthStatus.objects.filter(site=review.site).aggregate(value=Max("month"))["value"]
    if latest:
        end = max(end, latest)
    for month in months_between(start, end):
        rebuild_membership_month(review.site_id, month)
    rebuild_client_metrics_after_import(review.site_id, review.latest_raw_row.report_import_id)


@transaction.atomic
def resolve_purchase_review(review_id, studio_id, user, data):
    # Same lock order as the importer; only one decision/import per studio at once.
    Studio.objects.select_for_update().get(pk=studio_id)
    review = ServicePurchaseMatchReview.objects.select_for_update(of=("self",)).select_related(
        "latest_raw_row__report_import", "site", "studio", "client",
    ).get(pk=review_id, studio_id=studio_id)
    if review.status != "pending":
        raise ValidationError("This row has already been resolved. Refresh the list.")
    if str(data.get("raw_row_id", "")) != str(review.latest_raw_row_id):
        raise ValidationError("A newer upload changed this review. Refresh before deciding.")
    decision = data.get("decision")
    if decision not in {"update", "create", "ignore"}:
        raise ValidationError("Choose update, create, or ignore.")
    note = data.get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValidationError("The note must contain at most 2,000 characters.")
    previous = []
    if decision != "ignore":
        candidate = candidate_from_review(review)
        if decision == "update":
            try:
                purchase = ServicePurchase.objects.select_for_update().get(
                    pk=data.get("purchase_id"), site=review.site,
                    studio=review.studio, client=review.client,
                )
            except (ServicePurchase.DoesNotExist, ValueError, TypeError):
                raise ValidationError("Choose an existing purchase for this client and studio.")
            try:
                compared_at = parse_datetime(str(data.get("purchase_updated_at", "")))
            except ValueError:
                compared_at = None
            if compared_at != purchase.updated_at:
                raise ValidationError("The selected purchase changed. Refresh its comparison before deciding.")
            if purchase.source_raw_row_id and purchase.source_raw_row.report_import.uploaded_at > review.latest_raw_row.report_import.uploaded_at:
                raise ValidationError("This purchase has newer imported data. Upload the latest report before updating it.")
            # Never apply two rows from the same export to one purchase.
            if purchase.source_raw_row_id and purchase.source_raw_row.report_import_id == review.latest_raw_row.report_import_id:
                raise ValidationError("Another row in this report already represents this purchase. Choose another purchase or ignore this row.")
            previous = [purchase.sale_date, purchase.activation_date, purchase.expiration_date]
            candidate["service_purchase"] = purchase
        apply_purchase_candidate(candidate, review.latest_raw_row.report_import, separate=decision == "create")
        review.purchase = candidate["service_purchase"]
        # Keep the decision and derived metrics atomic: on failure it stays pending.
        rebuild_resolved_purchase_metrics(review, previous)
    review.status = decision
    review.resolved_by = user
    review.resolved_at = timezone.now()
    review.note = note
    review.decision_history.append({
        "decision": decision, "purchase_id": review.purchase_id if decision != "ignore" else None,
        "raw_row_id": review.latest_raw_row_id, "report_import_id": review.latest_raw_row.report_import_id,
        "resolved_by_id": user.pk, "resolved_by_name": user.email,
        "resolved_at": review.resolved_at.isoformat(), "note": note,
    })
    if decision == "ignore":
        review.purchase = None
    review.save()
    report_ids = review.source_rows.values_list("report_import_id", flat=True)
    for report in ReportImport.objects.filter(pk__in=report_ids, status=ReportImport.STATUS_NEEDS_REVIEW):
        if not report.service_purchase_raw_rows.filter(match_reviews__status="pending").exists():
            report.status = ReportImport.STATUS_COMPLETED
            report.save(update_fields=["status"])
    return review
