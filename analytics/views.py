from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from django.db import transaction
from django.db.models import Count, DecimalField, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from analytics.models import MembershipMonthStatus
from core_data.models import (
    AttendanceClassMatch,
    AttendanceVisit,
    PricingOption,
    SaleLine,
    ScheduledClass,
    ServicePurchase,
    Site,
    StudioClosure,
)


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def date_bounds(request):
    today = date.today()
    default_start = today.replace(day=1)
    default_end = today.replace(day=monthrange(today.year, today.month)[1])
    start = parse_date(request.query_params.get("date_from")) or default_start
    end = parse_date(request.query_params.get("date_to")) or default_end
    return start, end


def filtered_by_site(queryset, request):
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    return queryset


def filtered_attendance(queryset, request):
    queryset = filtered_by_site(queryset, request)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(visit_studio_id=studio_id)
    return queryset


def filtered_sales(queryset, request):
    queryset = filtered_by_site(queryset, request)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return queryset


def filtered_schedule(queryset, request):
    queryset = filtered_by_site(queryset, request)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return queryset


def filtered_closures(queryset, request):
    queryset = filtered_by_site(queryset, request)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(Q(studio_id=studio_id) | Q(studio__isnull=True))
    return queryset


def money_sum(queryset, field):
    return queryset.aggregate(
        total=Coalesce(Sum(field), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
    )["total"]


def decimal_value(value):
    return float(value or Decimal("0.00"))


def ratio_money(numerator, denominator):
    return decimal_value(numerator / denominator) if denominator else 0


def money_annotation(field):
    return Coalesce(Sum(field), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))


def money_rows(queryset, group_field, amount_field, label="name", limit=20):
    rows = (
        queryset.values(group_field)
        .annotate(total=money_annotation(amount_field), count=Count("id"))
        .order_by("-total")[:limit]
    )
    return [
        {
            label: row[group_field] or "N/A",
            "total": decimal_value(row["total"]),
            "count": row["count"],
        }
        for row in rows
    ]


def count_rows(queryset, group_field, label="name", limit=20):
    rows = queryset.values(group_field).annotate(total=Count("id")).order_by("-total")[:limit]
    return [{label: row[group_field] or "N/A", "total": row["total"]} for row in rows]


def date_money_rows(queryset, date_field, amount_field):
    rows = (
        queryset.annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(total=money_annotation(amount_field), count=Count("id"))
        .order_by("day")
    )
    return [
        {
            "date": row["day"].isoformat() if row["day"] else None,
            "total": decimal_value(row["total"]),
            "count": row["count"],
        }
        for row in rows
    ]


def date_count_rows(queryset, date_field):
    rows = (
        queryset.annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    return [{"date": row["day"].isoformat() if row["day"] else None, "total": row["total"]} for row in rows]


def attendance_hour_rows(queryset):
    counts = {}
    for value in queryset.values_list("visit_time_raw", flat=True):
        parsed_time = parse_time_value(value)
        if not parsed_time:
            continue
        counts[parsed_time.hour] = counts.get(parsed_time.hour, 0) + 1
    return [{"hour": f"{hour:02d}:00", "total": counts[hour]} for hour in sorted(counts)]


def weekday_name(value):
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[value.weekday()]


def weekday_money_rows(queryset, date_field, amount_field):
    rows = {}
    for item_date, amount in queryset.values_list(date_field, amount_field):
        if not item_date:
            continue
        weekday = item_date.weekday()
        row = rows.setdefault(weekday, {"weekday": weekday_name(item_date), "total": Decimal("0.00"), "count": 0})
        row["total"] += amount or Decimal("0.00")
        row["count"] += 1
    return [
        {"weekday": row["weekday"], "total": decimal_value(row["total"]), "count": row["count"]}
        for _, row in sorted(rows.items())
    ]


def weekday_count_rows(queryset, date_field):
    rows = {}
    for item_date in queryset.values_list(date_field, flat=True):
        if not item_date:
            continue
        weekday = item_date.weekday()
        row = rows.setdefault(weekday, {"weekday": weekday_name(item_date), "total": 0})
        row["total"] += 1
    return [row for _, row in sorted(rows.items())]


def instructor_quality_rows(queryset, limit=20):
    rows = (
        queryset.values("staff_member__name")
        .annotate(
            total=Count("id"),
            attended=Count("id", filter=Q(no_show=False, late_cancel=False)),
            no_shows=Count("id", filter=Q(no_show=True)),
            late_cancels=Count("id", filter=Q(late_cancel=True)),
            revenue=money_annotation("revenue"),
        )
        .order_by("-total")[:limit]
    )
    return [
        {
            "name": row["staff_member__name"] or "N/A",
            "total": row["total"],
            "attended": row["attended"],
            "no_shows": row["no_shows"],
            "late_cancels": row["late_cancels"],
            "no_show_rate": percentage(row["no_shows"], row["total"]),
            "late_cancel_rate": percentage(row["late_cancels"], row["total"]),
            "revenue": decimal_value(row["revenue"]),
        }
        for row in rows
    ]


def parse_time_value(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.casefold()
    normalized = normalized.replace("a. m.", "am").replace("p. m.", "pm")
    normalized = normalized.replace("a.m.", "am").replace("p.m.", "pm")
    normalized = normalized.replace("a m", "am").replace("p m", "pm")
    normalized = re.sub(r"\s+", " ", normalized).strip().upper()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(normalized, fmt).time().replace(second=0, microsecond=0)
        except ValueError:
            continue
    return None


def time_overlaps(start_a, end_a, start_b, end_b):
    if not all([start_a, end_a, start_b, end_b]):
        return False
    return start_a < end_b and start_b < end_a


def service_label(purchase):
    return purchase.pricing_option.name if purchase.pricing_option else "N/A"


def serialize_purchase(purchase, today=None, renewal=None):
    today = today or date.today()
    payload = {
        "client": purchase.client.name,
        "client_mindbody_id": purchase.client.mindbody_id,
        "client_email": purchase.client.email,
        "client_phone": purchase.client.phone,
        "client_id": purchase.client_id,
        "service": service_label(purchase),
        "sale_date": purchase.sale_date.isoformat() if purchase.sale_date else None,
        "activation_date": purchase.activation_date.isoformat() if purchase.activation_date else None,
        "expiration_date": purchase.expiration_date.isoformat() if purchase.expiration_date else None,
        "days_until_expiration": (purchase.expiration_date - today).days if purchase.expiration_date else None,
        "days_expired": (today - purchase.expiration_date).days if purchase.expiration_date and purchase.expiration_date < today else 0,
        "total_amount": decimal_value(purchase.total_amount),
    }
    if renewal:
        payload.update({
            "renewal_service": service_label(renewal),
            "renewal_sale_date": renewal.sale_date.isoformat() if renewal.sale_date else None,
            "renewal_expiration_date": renewal.expiration_date.isoformat() if renewal.expiration_date else None,
            "days_from_expiration_to_renewal": (
                renewal.sale_date - purchase.expiration_date
            ).days if renewal.sale_date and purchase.expiration_date else None,
        })
    return payload


def build_purchase_history(purchases):
    history = {}
    for purchase in purchases:
        history.setdefault(purchase.client_id, []).append(purchase)
    for client_purchases in history.values():
        client_purchases.sort(key=lambda item: (item.sale_date or date.min, item.id))
    return history


def find_next_purchase(purchase, client_purchases):
    for candidate in client_purchases:
        if candidate.id == purchase.id:
            continue
        if not candidate.sale_date or not purchase.sale_date:
            continue
        if candidate.sale_date < purchase.sale_date:
            continue
        if candidate.sale_date == purchase.sale_date and candidate.id <= purchase.id:
            continue
        if purchase.expiration_date and candidate.expiration_date and candidate.expiration_date < purchase.expiration_date:
            continue
        return candidate
    return None


def month_start(value):
    return value.replace(day=1)


def month_end(value):
    return value.replace(day=monthrange(value.year, value.month)[1])


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def months_between(start, end):
    current = month_start(start)
    final = month_start(end)
    months = []
    while current <= final:
        months.append(current)
        current = add_months(current, 1)
    return months


def inclusive_overlap_days(start_a, end_a, start_b, end_b):
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    if start > end:
        return 0
    return (end - start).days + 1


def union_days(intervals):
    if not intervals:
        return 0
    intervals = sorted(intervals)
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum((end - start).days + 1 for start, end in merged)


def infer_membership_studio(site_id, client_id, target_month):
    start = target_month
    end = month_end(target_month)
    month_attendance = (
        AttendanceVisit.objects.filter(
            site_id=site_id,
            client_id=client_id,
            visit_date__range=(start, end),
            no_show=False,
            late_cancel=False,
        )
        .values("visit_studio_id")
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )
    if month_attendance and month_attendance["visit_studio_id"]:
        return month_attendance["visit_studio_id"], MembershipMonthStatus.STUDIO_METHOD_ATTENDANCE_MONTH

    recent_attendance = (
        AttendanceVisit.objects.filter(
            site_id=site_id,
            client_id=client_id,
            visit_date__lt=start,
            no_show=False,
            late_cancel=False,
        )
        .order_by("-visit_date")
        .values("visit_studio_id")
        .first()
    )
    if recent_attendance and recent_attendance["visit_studio_id"]:
        return recent_attendance["visit_studio_id"], MembershipMonthStatus.STUDIO_METHOD_RECENT_ATTENDANCE

    return None, MembershipMonthStatus.STUDIO_METHOD_UNKNOWN


def membership_data_for_month(site_id, target_month):
    start = target_month
    end = month_end(target_month)
    month_days = (end - start).days + 1
    purchases = (
        ServicePurchase.objects.select_related("client", "pricing_option")
        .filter(
            site_id=site_id,
            pricing_option__track_retention=True,
            sale_date__lte=end,
        )
        .filter(Q(expiration_date__gte=start) | Q(expiration_date__isnull=True))
        .order_by("client_id", "sale_date", "id")
    )
    grouped = {}
    for purchase in purchases:
        active_start = purchase.activation_date or purchase.sale_date
        active_end = purchase.expiration_date or end
        if not active_start:
            continue
        overlap_days = inclusive_overlap_days(active_start, active_end, start, end)
        if overlap_days <= 0:
            continue
        row = grouped.setdefault(purchase.client_id, {
            "intervals": [],
            "value": Decimal("0.00"),
            "source_purchase": purchase,
        })
        row["intervals"].append((max(active_start, start), min(active_end, end)))
        row["value"] += purchase.total_amount or Decimal("0.00")
        if (
            not row["source_purchase"].sale_date
            or (purchase.sale_date or date.min) >= (row["source_purchase"].sale_date or date.min)
        ):
            row["source_purchase"] = purchase

    members = {}
    for client_id, row in grouped.items():
        days = min(union_days(row["intervals"]), month_days)
        if days >= 15:
            studio_id, method = infer_membership_studio(site_id, client_id, target_month)
            members[client_id] = {
                "days": days,
                "value": row["value"],
                "source_purchase": row["source_purchase"],
                "studio_id": studio_id,
                "studio_method": method,
            }
    return members


def historical_member_ids(site_id, before_month):
    purchases = ServicePurchase.objects.filter(
        site_id=site_id,
        pricing_option__track_retention=True,
        sale_date__lt=before_month,
    ).values_list("client_id", flat=True)
    return set(purchases)


def rebuild_membership_month(site_id, target_month):
    previous_month = add_months(target_month, -1)
    current_members = membership_data_for_month(site_id, target_month)
    previous_members = membership_data_for_month(site_id, previous_month)
    historical_members = historical_member_ids(site_id, previous_month)
    relevant_client_ids = set(current_members) | set(previous_members)
    rows = []

    for client_id in relevant_client_ids:
        current = current_members.get(client_id)
        previous = previous_members.get(client_id)
        if current and previous:
            status = MembershipMonthStatus.STATUS_RETAINED
            studio_id = current["studio_id"] or previous["studio_id"]
            studio_method = current["studio_method"] if current["studio_id"] else MembershipMonthStatus.STUDIO_METHOD_PREVIOUS_MONTH
        elif current:
            status = (
                MembershipMonthStatus.STATUS_REACTIVATED
                if client_id in historical_members
                else MembershipMonthStatus.STATUS_NEW
            )
            studio_id = current["studio_id"]
            studio_method = current["studio_method"]
        else:
            status = MembershipMonthStatus.STATUS_NOT_RENEWED
            studio_id = previous["studio_id"]
            studio_method = (
                MembershipMonthStatus.STUDIO_METHOD_PREVIOUS_MONTH
                if previous["studio_id"]
                else MembershipMonthStatus.STUDIO_METHOD_UNKNOWN
            )

        source = (current or previous)["source_purchase"]
        rows.append(MembershipMonthStatus(
            site_id=site_id,
            month=target_month,
            client_id=client_id,
            studio_id=studio_id,
            status=status,
            current_month_member=bool(current),
            previous_month_member=bool(previous),
            membership_days=current["days"] if current else 0,
            previous_membership_days=previous["days"] if previous else 0,
            membership_value=(current or previous)["value"],
            source_purchase=source,
            studio_inference_method=studio_method,
        ))

    with transaction.atomic():
        MembershipMonthStatus.objects.filter(site_id=site_id, month=target_month).delete()
        MembershipMonthStatus.objects.bulk_create(rows)
    return len(rows)


def membership_status_queryset(request):
    start, end = date_bounds(request)
    months = months_between(start, end)
    queryset = MembershipMonthStatus.objects.select_related(
        "site",
        "client",
        "studio",
        "source_purchase",
        "source_purchase__pricing_option",
    ).filter(month__in=months)
    queryset = filtered_by_site(queryset, request)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return start, end, months, queryset


def membership_history_for_statuses(statuses):
    status_rows = list(statuses)
    site_ids = {status.site_id for status in status_rows}
    client_ids = {status.client_id for status in status_rows}
    if not site_ids or not client_ids:
        return status_rows, {}

    rows = (
        ServicePurchase.objects.filter(
            site_id__in=site_ids,
            client_id__in=client_ids,
            pricing_option__track_retention=True,
        )
        .values("site_id", "client_id")
        .annotate(
            purchase_count=Count("id"),
            first_sale_date=Min("sale_date"),
            last_sale_date=Max("sale_date"),
            lifetime_value=money_annotation("total_amount"),
        )
    )
    history = {
        (row["site_id"], row["client_id"]): row
        for row in rows
    }
    return status_rows, history


def not_renewed_activity_for_statuses(status_rows):
    eligible = [
        status for status in status_rows
        if status.status == MembershipMonthStatus.STATUS_NOT_RENEWED
        and status.source_purchase
        and status.source_purchase.expiration_date
    ]
    if not eligible:
        return {}

    min_date = min(status.source_purchase.expiration_date + timedelta(days=1) for status in eligible)
    max_date = max(month_end(status.month) for status in eligible)
    site_ids = {status.site_id for status in eligible}
    client_ids = {status.client_id for status in eligible}

    attendance_rows = (
        AttendanceVisit.objects.filter(
            site_id__in=site_ids,
            client_id__in=client_ids,
            visit_date__range=(min_date, max_date),
            no_show=False,
            late_cancel=False,
        )
        .select_related("pricing_option")
        .order_by("visit_date")
    )
    attendance_by_client = {}
    for visit in attendance_rows:
        attendance_by_client.setdefault((visit.site_id, visit.client_id), []).append(visit)

    activity = {}
    for status in eligible:
        start = status.source_purchase.expiration_date + timedelta(days=1)
        end = month_end(status.month)
        visits = [
            visit for visit in attendance_by_client.get((status.site_id, status.client_id), [])
            if start <= visit.visit_date <= end
        ]
        paid_visits = [visit for visit in visits if (visit.revenue or Decimal("0.00")) > 0]
        unpaid_visits = [visit for visit in visits if (visit.revenue or Decimal("0.00")) <= 0]
        total_revenue = sum((visit.revenue or Decimal("0.00")) for visit in visits)
        pricing_options = sorted({
            visit.pricing_option.name
            for visit in visits
            if visit.pricing_option
        })

        if paid_visits:
            activity_status = "attending_paid"
        elif unpaid_visits:
            activity_status = "attending_unpaid"
        else:
            activity_status = "inactive"

        activity[status.id] = {
            "not_renewed_activity_status": activity_status,
            "post_expiration_attendance_count": len(visits),
            "post_expiration_paid_attendance_count": len(paid_visits),
            "post_expiration_unpaid_attendance_count": len(unpaid_visits),
            "post_expiration_revenue": decimal_value(total_revenue),
            "post_expiration_first_visit_date": visits[0].visit_date.isoformat() if visits else None,
            "post_expiration_last_visit_date": visits[-1].visit_date.isoformat() if visits else None,
            "post_expiration_pricing_options": pricing_options,
        }
    return activity


def default_not_renewed_activity(status):
    if status.status != MembershipMonthStatus.STATUS_NOT_RENEWED:
        return {
            "not_renewed_activity_status": None,
            "post_expiration_attendance_count": 0,
            "post_expiration_paid_attendance_count": 0,
            "post_expiration_unpaid_attendance_count": 0,
            "post_expiration_revenue": 0,
            "post_expiration_first_visit_date": None,
            "post_expiration_last_visit_date": None,
            "post_expiration_pricing_options": [],
        }
    return {
        "not_renewed_activity_status": "inactive",
        "post_expiration_attendance_count": 0,
        "post_expiration_paid_attendance_count": 0,
        "post_expiration_unpaid_attendance_count": 0,
        "post_expiration_revenue": 0,
        "post_expiration_first_visit_date": None,
        "post_expiration_last_visit_date": None,
        "post_expiration_pricing_options": [],
    }


def serialize_membership_status(status, membership_history=None, not_renewed_activity=None):
    purchase = status.source_purchase
    history = (membership_history or {}).get((status.site_id, status.client_id), {})
    activity = (not_renewed_activity or {}).get(status.id, default_not_renewed_activity(status))
    first_sale_date = history.get("first_sale_date")
    last_sale_date = history.get("last_sale_date")
    return {
        "id": status.id,
        "month": status.month.isoformat(),
        "status": status.status,
        "client": status.client.name,
        "client_mindbody_id": status.client.mindbody_id,
        "client_email": status.client.email,
        "client_phone": status.client.phone,
        "client_id": status.client_id,
        "studio": status.studio.name if status.studio else "Unknown",
        "studio_id": status.studio_id,
        "studio_inference_method": status.studio_inference_method,
        "service": service_label(purchase) if purchase else "N/A",
        "sale_date": purchase.sale_date.isoformat() if purchase and purchase.sale_date else None,
        "activation_date": purchase.activation_date.isoformat() if purchase and purchase.activation_date else None,
        "expiration_date": purchase.expiration_date.isoformat() if purchase and purchase.expiration_date else None,
        "membership_days": status.membership_days,
        "previous_membership_days": status.previous_membership_days,
        "total_amount": decimal_value(status.membership_value),
        "tracked_membership_purchase_count": history.get("purchase_count", 0),
        "first_membership_purchase_date": first_sale_date.isoformat() if first_sale_date else None,
        "last_membership_purchase_date": last_sale_date.isoformat() if last_sale_date else None,
        "lifetime_membership_value": decimal_value(history.get("lifetime_value")),
        **activity,
    }


def serialize_membership_status_rows(statuses):
    status_rows, membership_history = membership_history_for_statuses(statuses)
    not_renewed_activity = not_renewed_activity_for_statuses(status_rows)
    return [
        serialize_membership_status(row, membership_history, not_renewed_activity)
        for row in status_rows
    ]


def not_renewed_activity_summary(statuses):
    status_rows = list(statuses)
    activity = not_renewed_activity_for_statuses(status_rows)
    summary = {
        "inactive": 0,
        "attending_unpaid": 0,
        "attending_paid": 0,
        "attendance_count": 0,
        "unpaid_attendance_count": 0,
        "paid_attendance_count": 0,
        "revenue": Decimal("0.00"),
    }
    for status in status_rows:
        row = activity.get(status.id, default_not_renewed_activity(status))
        summary[row["not_renewed_activity_status"]] += 1
        summary["attendance_count"] += row["post_expiration_attendance_count"]
        summary["unpaid_attendance_count"] += row["post_expiration_unpaid_attendance_count"]
        summary["paid_attendance_count"] += row["post_expiration_paid_attendance_count"]
        summary["revenue"] += Decimal(str(row["post_expiration_revenue"] or 0))
    summary["revenue"] = decimal_value(summary["revenue"])
    return summary


def retention_groups(request):
    start, end, _, _, services = base_querysets(request)
    services = services.filter(pricing_option__track_retention=True)
    site_filtered_purchases = filtered_by_site(
        ServicePurchase.objects.filter(pricing_option__track_retention=True),
        request,
    )
    expired = (
        site_filtered_purchases.select_related("client", "pricing_option")
        .filter(expiration_date__range=(start, end))
        .order_by("expiration_date", "client__name")
    )
    expired_client_ids = list(expired.values_list("client_id", flat=True).distinct())
    purchase_history = build_purchase_history(
        site_filtered_purchases.select_related("client", "pricing_option").filter(client_id__in=expired_client_ids)
    )
    renewed = []
    not_renewed = []
    renewal_day_values = []
    for purchase in expired:
        renewal = find_next_purchase(purchase, purchase_history.get(purchase.client_id, []))
        if renewal:
            renewed.append((purchase, renewal))
            if renewal.sale_date and purchase.expiration_date:
                renewal_day_values.append((renewal.sale_date - purchase.expiration_date).days)
        else:
            not_renewed.append(purchase)
    return start, end, services, expired, renewed, not_renewed, renewal_day_values


def average(values):
    return round(sum(values) / len(values), 2) if values else None


def percentage(numerator, denominator):
    return round(numerator / denominator * 100, 2) if denominator else 0


def base_querysets(request):
    start, end = date_bounds(request)
    attendance = filtered_attendance(AttendanceVisit.objects.filter(visit_date__range=(start, end)), request)
    sales = filtered_sales(SaleLine.objects.filter(sale_date__range=(start, end)), request)
    services = filtered_by_site(ServicePurchase.objects.filter(sale_date__range=(start, end)), request)
    return start, end, attendance, sales, services


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary_view(request):
    start, end, attendance, sales, services = base_querysets(request)
    attendance_count = attendance.count()
    no_shows = attendance.filter(no_show=True).count()
    late_cancels = attendance.filter(late_cancel=True).count()
    attended = attendance.filter(no_show=False, late_cancel=False).count()
    active_clients = attendance.values("client_id").distinct().count()
    sales_revenue = money_sum(sales, "paid_total")
    service_revenue = money_sum(services, "total_amount")
    visit_revenue = money_sum(attendance, "revenue")
    sale_count = sales.values("sale_number").distinct().count()

    return Response({
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "studio_filter_limited": bool(request.query_params.get("studio")),
        "totals": {
            "attendance_visits": attendance_count,
            "attended_visits": attended,
            "no_shows": no_shows,
            "late_cancels": late_cancels,
            "no_show_rate": round(no_shows / attendance_count * 100, 2) if attendance_count else 0,
            "late_cancel_rate": round(late_cancels / attendance_count * 100, 2) if attendance_count else 0,
            "active_clients": active_clients,
            "sales_revenue": decimal_value(sales_revenue),
            "service_revenue": decimal_value(service_revenue),
            "visit_revenue": decimal_value(visit_revenue),
            "average_ticket": ratio_money(sales_revenue, sale_count),
            "average_revenue_per_attended_visit": ratio_money(visit_revenue, attended),
            "sales_count": sale_count,
            "sale_lines": sales.count(),
            "service_purchases": services.count(),
        },
        "site_count": Site.objects.count(),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revenue_view(request):
    _, _, attendance, sales, services = base_querysets(request)
    sales_revenue = money_sum(sales, "paid_total")
    sale_count = sales.values("sale_number").distinct().count()
    return Response({
        "studio_filter_limited": bool(request.query_params.get("studio")),
        "sales_revenue": decimal_value(sales_revenue),
        "service_revenue": decimal_value(money_sum(services, "total_amount")),
        "visit_revenue": decimal_value(money_sum(attendance, "revenue")),
        "discounts": decimal_value(money_sum(sales, "discount_amount")),
        "taxes": decimal_value(money_sum(sales, "tax")),
        "sale_count": sale_count,
        "average_ticket": ratio_money(sales_revenue, sale_count),
        "sales_by_date": date_money_rows(sales, "sale_date", "paid_total"),
        "sales_by_weekday": weekday_money_rows(sales, "sale_date", "paid_total"),
        "services_by_date": date_money_rows(services, "sale_date", "total_amount"),
        "services_by_weekday": weekday_money_rows(services, "sale_date", "total_amount"),
        "visits_by_date": date_money_rows(attendance, "visit_date", "revenue"),
        "visits_by_weekday": weekday_money_rows(attendance, "visit_date", "revenue"),
        "by_payment_method": money_rows(sales, "payment_method__name", "paid_total"),
        "by_studio": money_rows(sales, "studio__name", "paid_total"),
        "by_item": money_rows(sales, "item_name", "paid_total"),
        "by_service": money_rows(services, "pricing_option__name", "total_amount"),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_view(request):
    _, _, attendance, _, _ = base_querysets(request)
    total = attendance.count()
    attended = attendance.filter(no_show=False, late_cancel=False).count()
    visit_revenue = money_sum(attendance, "revenue")
    return Response({
        "total": total,
        "attended": attended,
        "no_shows": attendance.filter(no_show=True).count(),
        "late_cancels": attendance.filter(late_cancel=True).count(),
        "zero_revenue": attendance.filter(revenue=0).count(),
        "visit_revenue": decimal_value(visit_revenue),
        "average_revenue_per_attended_visit": ratio_money(visit_revenue, attended),
        "by_date": date_count_rows(attendance, "visit_date"),
        "by_weekday": weekday_count_rows(attendance, "visit_date"),
        "by_studio": count_rows(attendance, "visit_studio__name"),
        "by_instructor": count_rows(attendance, "staff_member__name"),
        "instructor_quality": instructor_quality_rows(attendance),
        "by_service": count_rows(attendance, "pricing_option__name"),
        "by_hour": attendance_hour_rows(attendance),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_view(request):
    start, end, months, statuses = membership_status_queryset(request)
    previous_members = statuses.filter(previous_month_member=True).count()
    current_members = statuses.filter(current_month_member=True).count()
    retained = statuses.filter(status=MembershipMonthStatus.STATUS_RETAINED).count()
    new_members = statuses.filter(status=MembershipMonthStatus.STATUS_NEW).count()
    reactivated = statuses.filter(status=MembershipMonthStatus.STATUS_REACTIVATED).count()
    not_renewed = statuses.filter(status=MembershipMonthStatus.STATUS_NOT_RENEWED)
    not_renewed_count = not_renewed.count()
    not_renewed_activity = not_renewed_activity_summary(not_renewed)
    tracked_products = filtered_by_site(PricingOption.objects.filter(track_retention=True), request).count()

    return Response({
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "months": [month.isoformat() for month in months],
        "snapshot_rows": statuses.count(),
        "tracked_pricing_options": tracked_products,
        "previous_month_members": previous_members,
        "current_month_members": current_members,
        "retained_members": retained,
        "new_members": new_members,
        "reactivated_members": reactivated,
        "not_renewed_services": not_renewed_count,
        "not_renewed_members": not_renewed_count,
        "not_renewed_inactive": not_renewed_activity["inactive"],
        "not_renewed_attending_unpaid": not_renewed_activity["attending_unpaid"],
        "not_renewed_attending_paid": not_renewed_activity["attending_paid"],
        "not_renewed_post_expiration_attendance": not_renewed_activity["attendance_count"],
        "not_renewed_post_expiration_unpaid_attendance": not_renewed_activity["unpaid_attendance_count"],
        "not_renewed_post_expiration_paid_attendance": not_renewed_activity["paid_attendance_count"],
        "not_renewed_post_expiration_revenue": not_renewed_activity["revenue"],
        "renewal_rate": percentage(retained, previous_members),
        "churn_rate": percentage(not_renewed_count, previous_members),
        "not_renewed_value": decimal_value(money_sum(not_renewed, "membership_value")),
        "not_renewed_clients": serialize_membership_status_rows(not_renewed.order_by("month", "client__name")[:25]),
        "retained_samples": serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_RETAINED).order_by("month", "client__name")[:25]
        ),
        "new_member_samples": serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_NEW).order_by("month", "client__name")[:25]
        ),
        "reactivated_samples": serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_REACTIVATED).order_by("month", "client__name")[:25]
        ),
        "definition": (
            "La retencion mensual usa snapshots. Un cliente cuenta como miembro de un mes si tuvo al menos "
            "15 dias cubiertos por productos marcados con track_retention. Not renewed se cuenta en el mes "
            "en que el cliente deja de ser miembro, no en el mes en que expiro el servicio anterior."
        ),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_followup_view(request):
    _, _, _, statuses = membership_status_queryset(request)
    status_value = request.query_params.get("status", "not_renewed")
    search = str(request.query_params.get("search") or "").strip().casefold()
    status_map = {
        "retained": MembershipMonthStatus.STATUS_RETAINED,
        "renewed": MembershipMonthStatus.STATUS_RETAINED,
        "new": MembershipMonthStatus.STATUS_NEW,
        "reactivated": MembershipMonthStatus.STATUS_REACTIVATED,
        "not_renewed": MembershipMonthStatus.STATUS_NOT_RENEWED,
    }
    queryset = statuses.filter(status=status_map.get(status_value, MembershipMonthStatus.STATUS_NOT_RENEWED))
    rows = serialize_membership_status_rows(queryset.order_by("month", "client__name"))

    if search:
        rows = [
            row for row in rows
            if search in str(row.get("client") or "").casefold()
            or search in str(row.get("client_mindbody_id") or "").casefold()
            or search in str(row.get("service") or "").casefold()
            or search in str(row.get("studio") or "").casefold()
        ]

    rows.sort(key=lambda row: (row.get("month") or "", row.get("client") or ""))
    return Response({
        "status": status_value,
        "count": len(rows),
        "rows": rows,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_membership_months_view(request):
    start = parse_date(request.data.get("date_from") or request.query_params.get("date_from"))
    end = parse_date(request.data.get("date_to") or request.query_params.get("date_to"))
    month_value = request.data.get("month") or request.query_params.get("month")
    if month_value and not start:
        start = parse_date(f"{month_value}-01")
        end = month_end(start) if start else None
    if not start or not end:
        start, end = date_bounds(request)

    site_id = request.data.get("site") or request.query_params.get("site")
    sites = Site.objects.filter(id=site_id) if site_id else Site.objects.all()
    months = months_between(start, end)
    results = []
    for site in sites:
        for target_month in months:
            results.append({
                "site": site.name,
                "site_id": site.id,
                "month": target_month.isoformat(),
                "rows": rebuild_membership_month(site.id, target_month),
            })
    return Response({
        "rebuilt": results,
        "total_rows": sum(row["rows"] for row in results),
    })


def candidate_classes_for_visit(visit, visit_time, scheduled_by_slot):
    if not visit_time:
        return []
    return scheduled_by_slot.get(
        (
            visit.site_id,
            visit.visit_studio_id,
            visit.visit_date,
            visit_time,
        ),
        [],
    )


def match_visit_to_class(visit, scheduled_by_slot):
    visit_time = parse_time_value(visit.visit_time_raw)
    candidates = candidate_classes_for_visit(visit, visit_time, scheduled_by_slot)
    if not candidates:
        return {
            "scheduled_class": None,
            "match_method": AttendanceClassMatch.METHOD_UNMATCHED,
            "confidence": Decimal("0.00"),
            "candidate_class_ids": [],
            "notes": "No scheduled class found for site, studio, date and start time.",
        }

    exact_instructor = [
        scheduled_class
        for scheduled_class in candidates
        if scheduled_class.staff_member_id and scheduled_class.staff_member_id == visit.staff_member_id
    ]
    if len(exact_instructor) == 1:
        return {
            "scheduled_class": exact_instructor[0],
            "match_method": AttendanceClassMatch.METHOD_EXACT_INSTRUCTOR_TIME,
            "confidence": Decimal("1.00"),
            "candidate_class_ids": [scheduled_class.id for scheduled_class in candidates],
            "notes": "",
        }

    if len(candidates) == 1:
        return {
            "scheduled_class": candidates[0],
            "match_method": AttendanceClassMatch.METHOD_SINGLE_CLASS_SAME_TIME,
            "confidence": Decimal("0.75"),
            "candidate_class_ids": [candidates[0].id],
            "notes": "Matched by site, studio, date and time; instructor was not exact.",
        }

    return {
        "scheduled_class": None,
        "match_method": AttendanceClassMatch.METHOD_AMBIGUOUS,
        "confidence": Decimal("0.40"),
        "candidate_class_ids": [scheduled_class.id for scheduled_class in candidates],
        "notes": "Multiple scheduled classes found for the same site, studio, date and time.",
    }


def rebuild_attendance_class_matches(site_id=None, start=None, end=None):
    visits = AttendanceVisit.objects.select_related("staff_member").filter(visit_date__range=(start, end))
    scheduled_classes = ScheduledClass.objects.select_related("staff_member").filter(
        class_date__range=(start, end),
    ).exclude(status__in=[ScheduledClass.STATUS_CANCELLED, ScheduledClass.STATUS_UNAVAILABLE])
    if site_id:
        visits = visits.filter(site_id=site_id)
        scheduled_classes = scheduled_classes.filter(site_id=site_id)

    scheduled_by_slot = {}
    for scheduled_class in scheduled_classes:
        key = (
            scheduled_class.site_id,
            scheduled_class.studio_id,
            scheduled_class.class_date,
            scheduled_class.start_time.replace(second=0, microsecond=0),
        )
        scheduled_by_slot.setdefault(key, []).append(scheduled_class)

    stats = {
        "visits_processed": 0,
        "matches_created": 0,
        "matches_updated": 0,
        "exact_instructor_time": 0,
        "single_class_same_time": 0,
        "ambiguous": 0,
        "unmatched": 0,
    }
    method_counter_keys = {
        AttendanceClassMatch.METHOD_EXACT_INSTRUCTOR_TIME: "exact_instructor_time",
        AttendanceClassMatch.METHOD_SINGLE_CLASS_SAME_TIME: "single_class_same_time",
        AttendanceClassMatch.METHOD_AMBIGUOUS: "ambiguous",
        AttendanceClassMatch.METHOD_UNMATCHED: "unmatched",
    }

    for visit in visits.iterator():
        match = match_visit_to_class(visit, scheduled_by_slot)
        _, created = AttendanceClassMatch.objects.update_or_create(
            attendance_visit=visit,
            defaults=match,
        )
        stats["visits_processed"] += 1
        stats["matches_created" if created else "matches_updated"] += 1
        stats[method_counter_keys[match["match_method"]]] += 1

    return stats


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_attendance_class_matches_view(request):
    start = parse_date(request.data.get("date_from") or request.query_params.get("date_from"))
    end = parse_date(request.data.get("date_to") or request.query_params.get("date_to"))
    if not start or not end:
        start, end = date_bounds(request)
    site_id = request.data.get("site") or request.query_params.get("site")

    with transaction.atomic():
        stats = rebuild_attendance_class_matches(site_id=site_id, start=start, end=end)

    return Response({
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "site_id": site_id,
        **stats,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def occupation_view(request):
    start, end, attendance, _, _ = base_querysets(request)
    scheduled_classes = filtered_schedule(
        ScheduledClass.objects.select_related("site", "studio", "room").filter(class_date__range=(start, end)),
        request,
    )
    closures = list(
        filtered_closures(
            StudioClosure.objects.select_related("site", "studio", "room").filter(
                active=True,
                closure_date__range=(start, end),
            ),
            request,
        )
    )

    def is_closed(scheduled_class):
        for closure in closures:
            if closure.closure_date != scheduled_class.class_date:
                continue
            if closure.studio_id and closure.studio_id != scheduled_class.studio_id:
                continue
            if closure.room_id and closure.room_id != scheduled_class.room_id:
                continue
            if closure.all_day:
                return True
            if time_overlaps(closure.start_time, closure.end_time, scheduled_class.start_time, scheduled_class.end_time):
                return True
        return False

    available_classes = [
        scheduled_class
        for scheduled_class in scheduled_classes
        if scheduled_class.status == ScheduledClass.STATUS_SCHEDULED and not is_closed(scheduled_class)
    ]
    available_class_ids = [scheduled_class.id for scheduled_class in available_classes]
    class_match_rows = (
        AttendanceClassMatch.objects.filter(scheduled_class_id__in=available_class_ids)
        .values(
            "scheduled_class_id",
            "attendance_visit__no_show",
            "attendance_visit__late_cancel",
        )
    )
    attended_by_class = {}
    for row in class_match_rows:
        if row["attendance_visit__no_show"] or row["attendance_visit__late_cancel"]:
            continue
        scheduled_class_id = row["scheduled_class_id"]
        attended_by_class[scheduled_class_id] = attended_by_class.get(scheduled_class_id, 0) + 1

    slots = {}
    by_studio = {}
    by_day = {}
    by_room = {}

    for scheduled_class in available_classes:
        attended_count = attended_by_class.get(scheduled_class.id, 0)
        key = (
            scheduled_class.site_id,
            scheduled_class.studio_id,
            scheduled_class.class_date,
            scheduled_class.start_time.replace(second=0, microsecond=0),
        )
        slot = slots.setdefault(key, {
            "site": scheduled_class.site.name,
            "studio": scheduled_class.studio.name,
            "date": scheduled_class.class_date.isoformat(),
            "start_time": scheduled_class.start_time.strftime("%H:%M"),
            "capacity": 0,
            "scheduled_classes": 0,
            "attended": 0,
        })
        slot["capacity"] += scheduled_class.capacity
        slot["scheduled_classes"] += 1
        slot["attended"] += attended_count

        studio_row = by_studio.setdefault(scheduled_class.studio_id, {
            "name": scheduled_class.studio.name,
            "capacity": 0,
            "attended": 0,
            "scheduled_classes": 0,
        })
        studio_row["capacity"] += scheduled_class.capacity
        studio_row["scheduled_classes"] += 1
        studio_row["attended"] += attended_count

        day_key = scheduled_class.class_date.isoformat()
        day_row = by_day.setdefault(day_key, {"date": day_key, "capacity": 0, "attended": 0, "scheduled_classes": 0})
        day_row["capacity"] += scheduled_class.capacity
        day_row["scheduled_classes"] += 1
        day_row["attended"] += attended_count

        room_name = scheduled_class.room.name if scheduled_class.room else "N/A"
        room_key = scheduled_class.room_id or f"none-{scheduled_class.studio_id}"
        room_row = by_room.setdefault(room_key, {
            "name": room_name,
            "studio": scheduled_class.studio.name,
            "capacity": 0,
            "attended": 0,
            "scheduled_classes": 0,
        })
        room_row["capacity"] += scheduled_class.capacity
        room_row["scheduled_classes"] += 1
        room_row["attended"] += attended_count

    total_capacity = 0
    matched_attended = 0
    for key, slot in slots.items():
        total_capacity += slot["capacity"]
        matched_attended += slot["attended"]
        slot["occupation_rate"] = percentage(slot["attended"], slot["capacity"])

    for row in by_studio.values():
        row["occupation_rate"] = percentage(row["attended"], row["capacity"])
    for row in by_day.values():
        row["occupation_rate"] = percentage(row["attended"], row["capacity"])
    for row in by_room.values():
        row["occupation_rate"] = percentage(row["attended"], row["capacity"])

    unresolved_attended = AttendanceClassMatch.objects.filter(
        attendance_visit__visit_date__range=(start, end),
        attendance_visit__no_show=False,
        attendance_visit__late_cancel=False,
        match_method__in=[
            AttendanceClassMatch.METHOD_AMBIGUOUS,
            AttendanceClassMatch.METHOD_UNMATCHED,
        ],
    )
    if request.query_params.get("site"):
        unresolved_attended = unresolved_attended.filter(attendance_visit__site_id=request.query_params.get("site"))
    if request.query_params.get("studio"):
        unresolved_attended = unresolved_attended.filter(attendance_visit__visit_studio_id=request.query_params.get("studio"))
    unscheduled_attended = unresolved_attended.count()

    return Response({
        "formula": "ocupacion = asistencias reales / capacidad programada",
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "scheduled_classes": scheduled_classes.count(),
        "available_classes": len(available_classes),
        "closed_or_unavailable_classes": scheduled_classes.count() - len(available_classes),
        "closures": len(closures),
        "scheduled_capacity": total_capacity,
        "matched_attended_visits": matched_attended,
        "unscheduled_attended_visits": unscheduled_attended,
        "unresolved_attended_visits": unscheduled_attended,
        "occupation_rate": percentage(matched_attended, total_capacity),
        "by_studio": sorted(by_studio.values(), key=lambda row: row["name"]),
        "by_day": sorted(by_day.values(), key=lambda row: row["date"]),
        "by_room_capacity": sorted(by_room.values(), key=lambda row: (row["studio"], row["name"])),
        "by_slot": sorted(slots.values(), key=lambda row: (row["date"], row["start_time"], row["studio"]))[:100],
        "note": (
            "La ocupacion usa los emparejamientos guardados entre asistencias y clases programadas. "
            "Reconstruye los emparejamientos despues de importar agenda o asistencia para actualizar estos datos."
        ),
    })
