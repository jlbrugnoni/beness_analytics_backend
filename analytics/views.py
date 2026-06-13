from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import ceil
import re

from django.db import transaction
from django.db.models import Count, DecimalField, F, Max, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from analytics.client_metrics import aggregate_client_monthly_metrics
from analytics.models import ClientStudioMonthlyMetric, MembershipMonthStatus
from core_data.access import scoped_queryset_for_user, user_has_capability
from core_data.models import (
    AttendanceClassMatch,
    AttendanceVisit,
    Client,
    PricingOption,
    SaleLine,
    ScheduledClass,
    ServicePurchase,
    Site,
    Studio,
    StudioClosure,
)


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def date_bounds(request, start=None, end=None):
    if start and end:
        return start, end
    today = date.today()
    default_start = today.replace(day=1)
    default_end = today.replace(day=monthrange(today.year, today.month)[1])
    start = parse_date(request.query_params.get("date_from")) or default_start
    end = parse_date(request.query_params.get("date_to")) or default_end
    return start, end


def client_directory_period(request):
    period = request.query_params.get("period", "month")
    allowed_periods = {"month", "last_3_months", "last_6_months", "last_12_months", "lifetime"}
    if period not in allowed_periods:
        period = "month"

    latest_complete = add_months(month_start(date.today()), -1)
    month_value = parse_date(f"{request.query_params.get('month')}-01") if request.query_params.get("month") else None
    selected_month = month_start(month_value or latest_complete)
    if period == "lifetime":
        return period, None, None, selected_month

    month_count = {
        "month": 1,
        "last_3_months": 3,
        "last_6_months": 6,
        "last_12_months": 12,
    }[period]
    start = add_months(selected_month, -(month_count - 1))
    return period, start, selected_month, selected_month


def client_directory_sort_value(row, field):
    value = row.get(field)
    if value is None:
        if field in {"client", "membership_status", "primary_studio"}:
            return ""
        return -1
    if isinstance(value, str):
        return value.casefold()
    return value


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def client_directory_view(request):
    period, start_month, end_month, selected_month = client_directory_period(request)
    site_id = request.query_params.get("site")
    studio_id = request.query_params.get("studio")
    search = (request.query_params.get("search") or "").strip()
    status_value = request.query_params.get("status")

    clients = scoped_queryset_for_user(
        Client.objects.select_related("site"),
        request.user,
        site_field="site_id",
    )
    if site_id:
        clients = clients.filter(site_id=site_id)
    if search:
        clients = clients.filter(
            Q(name__icontains=search)
            | Q(mindbody_id__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    metric_scope = scoped_queryset_for_user(
        ClientStudioMonthlyMetric.objects.select_related("studio", "client"),
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    if site_id:
        metric_scope = metric_scope.filter(site_id=site_id)
    if studio_id:
        metric_scope = metric_scope.filter(studio_id=studio_id)
    if start_month and end_month:
        metric_scope = metric_scope.filter(month__range=(start_month, end_month))

    represented_client_ids = metric_scope.values_list("client_id", flat=True).distinct()
    clients = clients.filter(id__in=represented_client_ids)
    client_rows = list(clients.values(
        "id",
        "name",
        "mindbody_id",
        "email",
        "phone",
        "site_id",
        "site__name",
    ))
    client_ids = [row["id"] for row in client_rows]

    metrics_by_client = {}
    for metric in metric_scope.filter(client_id__in=client_ids).iterator():
        metrics_by_client.setdefault(metric.client_id, []).append(metric)

    lifetime_metrics = scoped_queryset_for_user(
        ClientStudioMonthlyMetric.objects.filter(client_id__in=client_ids),
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    if site_id:
        lifetime_metrics = lifetime_metrics.filter(site_id=site_id)

    primary_candidates = {}
    last_visit_by_client = {}
    for metric in lifetime_metrics.select_related("studio").iterator():
        if metric.last_visit_date:
            current_last = last_visit_by_client.get(metric.client_id)
            if current_last is None or metric.last_visit_date > current_last:
                last_visit_by_client[metric.client_id] = metric.last_visit_date
        if not metric.studio_id or metric.attended_visits <= 0:
            continue
        key = (metric.client_id, metric.studio_id)
        candidate = primary_candidates.setdefault(key, {
            "client_id": metric.client_id,
            "studio_id": metric.studio_id,
            "studio": metric.studio.name,
            "attended_visits": 0,
            "last_visit_date": None,
        })
        candidate["attended_visits"] += metric.attended_visits
        if metric.last_visit_date and (
            candidate["last_visit_date"] is None
            or metric.last_visit_date > candidate["last_visit_date"]
        ):
            candidate["last_visit_date"] = metric.last_visit_date

    primary_by_client = {}
    for candidate in primary_candidates.values():
        current = primary_by_client.get(candidate["client_id"])
        candidate_key = (
            candidate["attended_visits"],
            candidate["last_visit_date"] or date.min,
            candidate["studio"].casefold(),
        )
        current_key = (
            current["attended_visits"],
            current["last_visit_date"] or date.min,
            current["studio"].casefold(),
        ) if current else None
        if current_key is None or candidate_key > current_key:
            primary_by_client[candidate["client_id"]] = candidate

    today = date.today()
    can_see_money = can_view_money(request)
    rows = []
    for client in client_rows:
        totals = aggregate_client_monthly_metrics(metrics_by_client.get(client["id"], []))
        last_visit = last_visit_by_client.get(client["id"])
        primary = primary_by_client.get(client["id"])
        total_bookings = totals["total_bookings"]
        row = {
            "client_id": client["id"],
            "client": client["name"],
            "mindbody_id": client["mindbody_id"],
            "email": client["email"],
            "phone": client["phone"],
            "site_id": client["site_id"],
            "site": client["site__name"],
            "membership_status": totals["membership_status"],
            "primary_studio_id": primary["studio_id"] if primary else None,
            "primary_studio": primary["studio"] if primary else None,
            "last_visit_date": last_visit.isoformat() if last_visit else None,
            "days_since_last_visit": (today - last_visit).days if last_visit else None,
            "attended_visits": totals["attended_visits"],
            "active_weeks": totals["active_weeks"],
            "total_bookings": total_bookings,
            "attendance_rate": percentage(totals["attended_visits"], total_bookings),
            "no_show_rate": percentage(totals["no_shows"], total_bookings),
            "late_cancel_rate": percentage(totals["late_cancels"], total_bookings),
            "service_spending": decimal_value(totals["service_spending"]) if can_see_money else None,
            "total_sales_spending": decimal_value(totals["general_sales_spending"]) if can_see_money else None,
        }
        if not status_value or row["membership_status"] == status_value:
            rows.append(row)

    sort_field = request.query_params.get("ordering", "client")
    descending = sort_field.startswith("-")
    sort_field = sort_field.lstrip("-")
    allowed_sort_fields = {
        "client",
        "membership_status",
        "primary_studio",
        "last_visit_date",
        "days_since_last_visit",
        "attended_visits",
        "active_weeks",
        "attendance_rate",
        "no_show_rate",
        "late_cancel_rate",
        "service_spending",
        "total_sales_spending",
    }
    if sort_field not in allowed_sort_fields:
        sort_field = "client"
        descending = False
    rows.sort(
        key=lambda row: (
            client_directory_sort_value(row, sort_field),
            row["client"].casefold(),
        ),
        reverse=descending,
    )

    try:
        page_size = min(max(int(request.query_params.get("page_size", 25)), 1), 100)
    except (TypeError, ValueError):
        page_size = 25
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    count = len(rows)
    pages = ceil(count / page_size) if count else 0
    if pages and page > pages:
        page = pages
    offset = (page - 1) * page_size

    available_sites = scoped_queryset_for_user(
        Site.objects.all(),
        request.user,
        site_field="id",
    ).values("id", "name")
    available_studios = scoped_queryset_for_user(
        Studio.objects.select_related("site"),
        request.user,
        studio_field="id",
    )

    return Response({
        "period": {
            "mode": period,
            "month": selected_month.strftime("%Y-%m"),
            "from": start_month.isoformat() if start_month else None,
            "to": month_end(end_month).isoformat() if end_month else None,
        },
        "count": count,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "ordering": f"-{sort_field}" if descending else sort_field,
        "results": rows[offset:offset + page_size],
        "filters": {
            "sites": list(available_sites),
            "studios": [
                {
                    "id": studio.id,
                    "name": studio.name,
                    "site_id": studio.site_id,
                    "site": studio.site.name,
                }
                for studio in available_studios
            ],
            "membership_statuses": [
                {"value": value, "label": label}
                for value, label in MembershipMonthStatus.STATUS_CHOICES
            ],
        },
    })


def filtered_by_site(queryset, request):
    queryset = scoped_queryset_for_user(queryset, request.user)
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    return queryset


def filtered_attendance(queryset, request):
    queryset = scoped_queryset_for_user(queryset, request.user, site_field="site_id", studio_field="visit_studio_id")
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(visit_studio_id=studio_id)
    return queryset


def filtered_sales(queryset, request):
    queryset = scoped_queryset_for_user(queryset, request.user, site_field="site_id", studio_field="studio_id")
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return queryset


def filtered_services(queryset, request):
    queryset = scoped_queryset_for_user(queryset, request.user, site_field="site_id", studio_field="studio_id")
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return queryset


def filtered_schedule(queryset, request):
    queryset = scoped_queryset_for_user(queryset, request.user, site_field="site_id", studio_field="studio_id")
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    studio_id = request.query_params.get("studio")
    if studio_id:
        queryset = queryset.filter(studio_id=studio_id)
    return queryset


def filtered_closures(queryset, request):
    queryset = scoped_queryset_for_user(
        queryset,
        request.user,
        studio_field="studio_id",
        include_null_studio=True,
    )
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
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


def can_view_money(request):
    return user_has_capability(request.user, "can_view_money")


def capability_error(request, capability):
    if user_has_capability(request.user, capability):
        return None
    return Response({"error": "You do not have permission to perform this action."}, status=403)


def money_value(request, value):
    return decimal_value(value) if can_view_money(request) else None


def money_ratio_value(request, numerator, denominator):
    return ratio_money(numerator, denominator) if can_view_money(request) else None


def money_rows_for_request(request, *args, **kwargs):
    return money_rows(*args, **kwargs) if can_view_money(request) else []


def date_money_rows_for_request(request, *args, **kwargs):
    return date_money_rows(*args, **kwargs) if can_view_money(request) else []


def weekday_money_rows_for_request(request, *args, **kwargs):
    return weekday_money_rows(*args, **kwargs) if can_view_money(request) else []


def item_money_rows_for_request(request, queryset):
    return item_money_rows(queryset) if can_view_money(request) else []


def mask_membership_money_rows(request, rows):
    if can_view_money(request):
        return rows
    money_fields = {
        "total_amount",
        "lifetime_membership_value",
        "post_expiration_revenue",
    }
    return [
        {
            **row,
            **{field: None for field in money_fields if field in row},
        }
        for row in rows
    ]


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


def item_money_rows(queryset, limit=20):
    rows = (
        queryset.values("item_name")
        .annotate(
            total=money_annotation("paid_total"),
            count=Count("id"),
            units=Coalesce(Sum("quantity"), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)),
        )
        .order_by("-total")[:limit]
    )
    return [
        {
            "name": row["item_name"] or "N/A",
            "total": decimal_value(row["total"]),
            "count": row["count"],
            "units": decimal_value(row["units"]),
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


def attendance_status_date_rows(queryset):
    rows = {}
    for visit_date, no_show, late_cancel in queryset.values_list("visit_date", "no_show", "late_cancel"):
        if not visit_date:
            continue
        key = visit_date.isoformat()
        row = rows.setdefault(key, {
            "date": key,
            "total": 0,
            "attended": 0,
            "no_shows": 0,
            "late_cancels": 0,
        })
        row["total"] += 1
        if no_show:
            row["no_shows"] += 1
        elif late_cancel:
            row["late_cancels"] += 1
        else:
            row["attended"] += 1
    return [rows[key] for key in sorted(rows)]


def trial_status_date_rows(queryset):
    rows = {}
    for visit_date, no_show, late_cancel in queryset.values_list("visit_date", "no_show", "late_cancel"):
        if not visit_date:
            continue
        key = visit_date.isoformat()
        row = rows.setdefault(key, {
            "date": key,
            "total": 0,
            "attended": 0,
            "no_shows": 0,
            "late_cancels": 0,
        })
        row["total"] += 1
        if no_show:
            row["no_shows"] += 1
        elif late_cancel:
            row["late_cancels"] += 1
        else:
            row["attended"] += 1
    return [rows[key] for key in sorted(rows)]


def attendance_hour_rows(queryset):
    counts = {}
    for value in queryset.values_list("visit_time_raw", flat=True):
        parsed_time = parse_time_value(value)
        if not parsed_time:
            continue
        counts[parsed_time.hour] = counts.get(parsed_time.hour, 0) + 1
    return [{"hour": f"{hour:02d}:00", "total": counts[hour]} for hour in sorted(counts)]


def scheduled_attendance_hour_rows(request, start, end, attended_only=False):
    scheduled_classes = filtered_schedule(
        ScheduledClass.objects.filter(
            class_date__range=(start, end),
            status=ScheduledClass.STATUS_SCHEDULED,
        ),
        request,
    )
    scheduled_hours = sorted(set(scheduled_classes.values_list("start_time__hour", flat=True)))
    counts = {hour: 0 for hour in scheduled_hours if hour is not None}
    if not counts:
        return []

    class_ids = list(scheduled_classes.values_list("id", flat=True))
    matches = AttendanceClassMatch.objects.filter(scheduled_class_id__in=class_ids)
    if attended_only:
        matches = matches.filter(attendance_visit__no_show=False, attendance_visit__late_cancel=False)
    matches = matches.values("scheduled_class__start_time__hour").annotate(total=Count("id"))
    for row in matches:
        hour = row["scheduled_class__start_time__hour"]
        if hour is not None:
            counts[hour] = row["total"]

    return [{"hour": f"{hour:02d}:00", "total": counts.get(hour, 0)} for hour in sorted(counts)]


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
        ServicePurchase.objects.select_related("client", "pricing_option", "studio")
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
            source_purchase = row["source_purchase"]
            if source_purchase.studio_id:
                studio_id = source_purchase.studio_id
                method = MembershipMonthStatus.STUDIO_METHOD_PURCHASE
            else:
                studio_id, method = infer_membership_studio(site_id, client_id, target_month)
            members[client_id] = {
                "days": days,
                "value": row["value"],
                "source_purchase": source_purchase,
                "studio_id": studio_id,
                "studio_method": method,
            }
    return members


def historical_member_ids(site_id, before_month):
    purchases = (
        ServicePurchase.objects.filter(
            site_id=site_id,
            pricing_option__track_retention=True,
        )
        .filter(
            Q(activation_date__lt=before_month)
            | Q(activation_date__isnull=True, sale_date__lt=before_month)
        )
        .order_by("client_id", "sale_date", "id")
    )
    intervals_by_client = {}
    for purchase in purchases:
        active_start = purchase.activation_date or purchase.sale_date
        if not active_start or active_start >= before_month:
            continue
        active_end = purchase.expiration_date or before_month - timedelta(days=1)
        active_end = min(active_end, before_month - timedelta(days=1))
        if active_start <= active_end:
            intervals_by_client.setdefault(purchase.client_id, []).append((active_start, active_end))

    historical_members = set()
    for client_id, intervals in intervals_by_client.items():
        first_month = min(month_start(start) for start, _ in intervals)
        for target_month in months_between(first_month, add_months(before_month, -1)):
            target_end = month_end(target_month)
            covered_intervals = [
                (max(start, target_month), min(end, target_end))
                for start, end in intervals
                if start <= target_end and end >= target_month
            ]
            if union_days(covered_intervals) >= 15:
                historical_members.add(client_id)
                break
    return historical_members


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
            studio_method = current["studio_method"] if current["studio_id"] else previous["studio_method"]
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
            studio_method = previous["studio_method"]

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
    from analytics.client_metrics import rebuild_client_studio_monthly_metrics

    rebuild_client_studio_monthly_metrics(site_id, target_month)
    return len(rows)


def rebuild_membership_months_after_import(site_id, report_import_id):
    purchases = ServicePurchase.objects.filter(
        site_id=site_id,
        last_seen_import_id=report_import_id,
        pricing_option__track_retention=True,
    ).values("sale_date", "activation_date", "expiration_date")
    coverage_ranges = [
        (
            purchase["activation_date"] or purchase["sale_date"],
            purchase["expiration_date"] or purchase["activation_date"] or purchase["sale_date"],
        )
        for purchase in purchases
        if purchase["activation_date"] or purchase["sale_date"]
    ]
    if not coverage_ranges:
        return {
            "skipped": True,
            "reason": "The report did not contain tracked retention purchases.",
            "rebuilt": [],
            "total_rows": 0,
        }

    first_month = min(month_start(start) for start, _ in coverage_ranges)
    last_coverage_month = max(month_start(end) for _, end in coverage_ranges)
    last_required_month = add_months(last_coverage_month, 1)
    latest_snapshot = (
        MembershipMonthStatus.objects.filter(site_id=site_id)
        .aggregate(latest=Max("month"))
        .get("latest")
    )
    if latest_snapshot:
        last_required_month = max(last_required_month, latest_snapshot)

    rebuilt = [
        {
            "month": target_month.isoformat(),
            "rows": rebuild_membership_month(site_id, target_month),
        }
        for target_month in months_between(first_month, last_required_month)
    ]
    return {
        "skipped": False,
        "rebuilt": rebuilt,
        "total_rows": sum(row["rows"] for row in rebuilt),
    }


def membership_status_queryset(request, start=None, end=None):
    start, end = date_bounds(request, start=start, end=end)
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
    purchases = (
        ServicePurchase.objects.filter(
            site_id__in=site_ids,
            client_id__in=client_ids,
            pricing_option__track_retention=True,
        )
        .values("id", "site_id", "client_id", "sale_date")
        .order_by("site_id", "client_id", "sale_date", "id")
    )
    for purchase in purchases:
        history.setdefault(
            (purchase["site_id"], purchase["client_id"]),
            {},
        ).setdefault("_purchases", []).append(purchase)
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
    previous_sale_date = None
    if purchase and purchase.sale_date:
        source_key = (purchase.sale_date, purchase.id)
        previous_purchases = [
            item
            for item in history.get("_purchases", [])
            if item["sale_date"] and (item["sale_date"], item["id"]) < source_key
        ]
        if previous_purchases:
            previous_sale_date = previous_purchases[-1]["sale_date"]
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
        "previous_membership_purchase_date": previous_sale_date.isoformat() if previous_sale_date else None,
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


NOT_RENEWED_ACTIVITY_ORDER = {
    "attending_unpaid": 0,
    "attending_paid": 1,
    "inactive": 2,
}


def sort_not_renewed_rows(rows):
    return sorted(rows, key=lambda row: (
        NOT_RENEWED_ACTIVITY_ORDER.get(row.get("not_renewed_activity_status"), 99),
        str(row.get("client") or "").casefold(),
        row.get("month") or "",
    ))


def new_non_member_purchase_rows(request, start, end, exclude_client_months=None):
    first_non_trial_sale_date = (
        ServicePurchase.objects.filter(
            client_id=OuterRef("client_id"),
            pricing_option__is_trial_class=False,
        )
        .order_by("sale_date", "id")
        .values("sale_date")[:1]
    )
    purchases = (
        filtered_by_site(
            ServicePurchase.objects.select_related(
                "client",
                "pricing_option",
                "studio",
            ).exclude(pricing_option__is_trial_class=True),
            request,
        )
        .annotate(first_non_trial_sale_date=Subquery(first_non_trial_sale_date))
        .filter(
            sale_date=F("first_non_trial_sale_date"),
            sale_date__gte=start,
            sale_date__lte=end,
        )
        .order_by("client_id", "sale_date", "id")
    )
    first_date_purchases = {}
    for purchase in purchases:
        client_rows = first_date_purchases.get(purchase.client_id)
        if client_rows is None:
            first_date_purchases[purchase.client_id] = [purchase]
        elif purchase.sale_date == client_rows[0].sale_date:
            client_rows.append(purchase)

    excluded = set(exclude_client_months or [])
    selected_studio = str(request.query_params.get("studio") or "")
    rows = []
    for client_id, first_purchases in first_date_purchases.items():
        first_purchase = first_purchases[0]
        if (
            (client_id, month_start(first_purchase.sale_date)) in excluded
            or any(purchase.pricing_option.track_retention for purchase in first_purchases)
        ):
            continue
        source_purchase = first_purchase
        if selected_studio and str(source_purchase.studio_id or "") != selected_studio:
            continue
        rows.append({
            "id": f"purchase-{source_purchase.id}",
            "purchase_id": source_purchase.id,
            "history_client_id": source_purchase.client_id,
            "month": month_start(source_purchase.sale_date).isoformat(),
            "status": "new_non_member",
            "client": source_purchase.client.name,
            "client_mindbody_id": source_purchase.client.mindbody_id,
            "client_email": source_purchase.client.email,
            "client_phone": source_purchase.client.phone,
            "client_id": source_purchase.client_id,
            "studio": source_purchase.studio.name if source_purchase.studio else "Unknown",
            "studio_id": source_purchase.studio_id,
            "service": service_label(source_purchase),
            "sale_date": source_purchase.sale_date.isoformat(),
            "activation_date": (
                source_purchase.activation_date.isoformat()
                if source_purchase.activation_date
                else None
            ),
            "expiration_date": (
                source_purchase.expiration_date.isoformat()
                if source_purchase.expiration_date
                else None
            ),
            "membership_days": 0,
            "previous_membership_days": 0,
            "total_amount": money_value(request, source_purchase.total_amount),
            "tracked_membership_purchase_count": 0,
            "lifetime_membership_value": None,
            "not_renewed_activity_status": None,
        })
    return sorted(rows, key=lambda row: (row["sale_date"], row["client"]))


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


def base_querysets(request, start=None, end=None):
    start, end = date_bounds(request, start=start, end=end)
    attendance = filtered_attendance(AttendanceVisit.objects.filter(visit_date__range=(start, end)), request)
    sales = filtered_sales(SaleLine.objects.filter(sale_date__range=(start, end)), request)
    services = filtered_services(ServicePurchase.objects.filter(sale_date__range=(start, end)), request)
    return start, end, attendance, sales, services


def summary_payload(request, start=None, end=None):
    start, end, attendance, sales, services = base_querysets(request, start=start, end=end)
    attendance_count = attendance.count()
    no_shows = attendance.filter(no_show=True).count()
    late_cancels = attendance.filter(late_cancel=True).count()
    attended = attendance.filter(no_show=False, late_cancel=False).count()
    active_clients = attendance.values("client_id").distinct().count()
    sales_revenue = money_sum(sales, "paid_total")
    service_revenue = money_sum(services, "total_amount")
    visit_revenue = money_sum(attendance, "revenue")
    sale_count = sales.values("sale_number").distinct().count()

    return {
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
            "sales_revenue": money_value(request, sales_revenue),
            "service_revenue": money_value(request, service_revenue),
            "visit_revenue": money_value(request, visit_revenue),
            "average_ticket": money_ratio_value(request, sales_revenue, sale_count),
            "average_revenue_per_attended_visit": money_ratio_value(request, visit_revenue, attended),
            "sales_count": sale_count,
            "sale_lines": sales.count(),
            "service_purchases": services.count(),
        },
        "site_count": Site.objects.count(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary_view(request):
    return Response(summary_payload(request))


def revenue_payload(request, start=None, end=None):
    _, _, attendance, sales, services = base_querysets(request, start=start, end=end)
    sales_revenue = money_sum(sales, "paid_total")
    sale_count = sales.values("sale_number").distinct().count()
    return {
        "studio_filter_limited": bool(request.query_params.get("studio")),
        "sales_revenue": money_value(request, sales_revenue),
        "service_revenue": money_value(request, money_sum(services, "total_amount")),
        "visit_revenue": money_value(request, money_sum(attendance, "revenue")),
        "discounts": money_value(request, money_sum(sales, "discount_amount")),
        "taxes": money_value(request, money_sum(sales, "tax")),
        "sale_count": sale_count,
        "average_ticket": money_ratio_value(request, sales_revenue, sale_count),
        "sales_by_date": date_money_rows_for_request(request, sales, "sale_date", "paid_total"),
        "sales_by_weekday": weekday_money_rows_for_request(request, sales, "sale_date", "paid_total"),
        "services_by_date": date_money_rows_for_request(request, services, "sale_date", "total_amount"),
        "services_by_weekday": weekday_money_rows_for_request(request, services, "sale_date", "total_amount"),
        "visits_by_date": date_money_rows_for_request(request, attendance, "visit_date", "revenue"),
        "visits_by_weekday": weekday_money_rows_for_request(request, attendance, "visit_date", "revenue"),
        "by_payment_method": money_rows_for_request(request, sales, "payment_method__name", "paid_total"),
        "by_studio": money_rows_for_request(request, sales, "studio__name", "paid_total"),
        "by_item": item_money_rows_for_request(request, sales),
        "by_service": money_rows_for_request(request, services, "pricing_option__name", "total_amount"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revenue_view(request):
    return Response(revenue_payload(request))


def trial_conversion_payload(request, start=None, end=None, conversion_window_days=30, row_limit=200):
    start, end = date_bounds(request, start=start, end=end)
    trial_visits = filtered_attendance(
        AttendanceVisit.objects.select_related(
            "site",
            "client",
            "visit_studio",
            "staff_member",
            "pricing_option",
        ).filter(
            visit_date__range=(start, end),
            pricing_option__is_trial_class=True,
        ),
        request,
    )
    attended_trials = trial_visits.filter(no_show=False, late_cancel=False)
    tracked_trial_options = filtered_by_site(PricingOption.objects.filter(is_trial_class=True), request).count()
    unique_trial_clients = attended_trials.values("client_id").distinct().count()

    first_trials = {}
    for visit in attended_trials.order_by("visit_date", "visit_time_raw", "id"):
        if visit.client_id not in first_trials:
            first_trials[visit.client_id] = visit

    client_ids = list(first_trials)
    purchase_rows = (
        filtered_services(
            ServicePurchase.objects.select_related("client", "pricing_option", "site").filter(
                client_id__in=client_ids,
                sale_date__gte=start,
                sale_date__lte=end + timedelta(days=conversion_window_days),
                total_amount__gt=0,
            ).exclude(pricing_option__is_trial_class=True),
            request,
        )
        .order_by("sale_date", "id")
    )

    purchases_by_client = {}
    for purchase in purchase_rows:
        purchases_by_client.setdefault(purchase.client_id, []).append(purchase)

    converted_clients = 0
    converted_members = 0
    days_to_conversion = []
    rows = []
    by_instructor = {}
    by_studio = {}

    for client_id, trial in first_trials.items():
        window_end = trial.visit_date + timedelta(days=conversion_window_days)
        candidate_purchases = [
            purchase
            for purchase in purchases_by_client.get(client_id, [])
            if trial.visit_date <= purchase.sale_date <= window_end
        ]
        first_paid_purchase = candidate_purchases[0] if candidate_purchases else None
        first_member_purchase = next(
            (purchase for purchase in candidate_purchases if purchase.pricing_option and purchase.pricing_option.track_retention),
            None,
        )
        if first_paid_purchase:
            converted_clients += 1
            days_to_conversion.append((first_paid_purchase.sale_date - trial.visit_date).days)
        if first_member_purchase:
            converted_members += 1

        instructor_name = trial.staff_member.name if trial.staff_member else "N/A"
        instructor_row = by_instructor.setdefault(instructor_name, {
            "name": instructor_name,
            "trial_clients": 0,
            "converted_clients": 0,
            "converted_members": 0,
        })
        instructor_row["trial_clients"] += 1
        if first_paid_purchase:
            instructor_row["converted_clients"] += 1
        if first_member_purchase:
            instructor_row["converted_members"] += 1

        studio_name = trial.visit_studio.name if trial.visit_studio else "N/A"
        studio_row = by_studio.setdefault(studio_name, {
            "name": studio_name,
            "trial_clients": 0,
            "converted_clients": 0,
            "converted_members": 0,
        })
        studio_row["trial_clients"] += 1
        if first_paid_purchase:
            studio_row["converted_clients"] += 1
        if first_member_purchase:
            studio_row["converted_members"] += 1

        rows.append({
            "client": trial.client.name,
            "client_id": trial.client_id,
            "trial_date": trial.visit_date.isoformat() if trial.visit_date else None,
            "studio": studio_name,
            "instructor": instructor_name,
            "trial_service": trial.pricing_option.name if trial.pricing_option else "N/A",
            "converted_to_client": bool(first_paid_purchase),
            "converted_to_member": bool(first_member_purchase),
            "conversion_date": first_paid_purchase.sale_date.isoformat() if first_paid_purchase else None,
            "conversion_service": first_paid_purchase.pricing_option.name if first_paid_purchase and first_paid_purchase.pricing_option else None,
            "membership_conversion_date": first_member_purchase.sale_date.isoformat() if first_member_purchase else None,
            "membership_service": first_member_purchase.pricing_option.name if first_member_purchase and first_member_purchase.pricing_option else None,
            "days_to_conversion": (first_paid_purchase.sale_date - trial.visit_date).days if first_paid_purchase else None,
        })

    for row in by_instructor.values():
        row["converted_non_members"] = max(0, row["converted_clients"] - row["converted_members"])
        row["not_converted_clients"] = max(0, row["trial_clients"] - row["converted_clients"])
        row["client_conversion_rate"] = percentage(row["converted_clients"], row["trial_clients"])
        row["member_conversion_rate"] = percentage(row["converted_members"], row["trial_clients"])
        row["non_member_conversion_rate"] = percentage(row["converted_non_members"], row["trial_clients"])
    for row in by_studio.values():
        row["converted_non_members"] = max(0, row["converted_clients"] - row["converted_members"])
        row["not_converted_clients"] = max(0, row["trial_clients"] - row["converted_clients"])
        row["client_conversion_rate"] = percentage(row["converted_clients"], row["trial_clients"])
        row["member_conversion_rate"] = percentage(row["converted_members"], row["trial_clients"])
        row["non_member_conversion_rate"] = percentage(row["converted_non_members"], row["trial_clients"])

    return {
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "conversion_window_days": conversion_window_days,
        "tracked_trial_options": tracked_trial_options,
        "trial_bookings": trial_visits.count(),
        "attended_trials": attended_trials.count(),
        "trial_no_shows": trial_visits.filter(no_show=True).count(),
        "trial_late_cancels": trial_visits.filter(late_cancel=True).count(),
        "unique_trial_clients": unique_trial_clients,
        "converted_clients": converted_clients,
        "converted_members": converted_members,
        "converted_non_members": max(0, converted_clients - converted_members),
        "not_converted_clients": max(0, unique_trial_clients - converted_clients),
        "client_conversion_rate": percentage(converted_clients, unique_trial_clients),
        "member_conversion_rate": percentage(converted_members, unique_trial_clients),
        "non_member_conversion_rate": percentage(max(0, converted_clients - converted_members), unique_trial_clients),
        "not_converted_rate": percentage(max(0, unique_trial_clients - converted_clients), unique_trial_clients),
        "average_days_to_conversion": (
            sum(days_to_conversion) / len(days_to_conversion)
            if days_to_conversion else 0
        ),
        "by_date": trial_status_date_rows(trial_visits),
        "by_instructor": sorted(by_instructor.values(), key=lambda row: row["trial_clients"], reverse=True)[:20],
        "by_studio": sorted(by_studio.values(), key=lambda row: row["trial_clients"], reverse=True)[:20],
        "rows": sorted(rows, key=lambda row: (row["trial_date"] or "", row["client"]))[:row_limit],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def trial_conversion_view(request):
    return Response(trial_conversion_payload(request))


def attendance_payload(request, start=None, end=None):
    start, end, attendance, _, _ = base_querysets(request, start=start, end=end)
    total = attendance.count()
    attended_attendance = attendance.filter(no_show=False, late_cancel=False)
    attended = attended_attendance.count()
    visit_revenue = money_sum(attendance, "revenue")
    return {
        "total": total,
        "attended": attended,
        "no_shows": attendance.filter(no_show=True).count(),
        "late_cancels": attendance.filter(late_cancel=True).count(),
        "zero_revenue": attendance.filter(revenue=0).count(),
        "visit_revenue": money_value(request, visit_revenue),
        "average_revenue_per_attended_visit": money_ratio_value(request, visit_revenue, attended),
        "by_date": date_count_rows(attendance, "visit_date"),
        "attended_by_date": date_count_rows(attended_attendance, "visit_date"),
        "booking_quality_by_date": attendance_status_date_rows(attendance),
        "by_weekday": weekday_count_rows(attendance, "visit_date"),
        "by_studio": count_rows(attendance, "visit_studio__name"),
        "attended_by_studio": count_rows(attended_attendance, "visit_studio__name"),
        "by_instructor": count_rows(attendance, "staff_member__name"),
        "attended_by_instructor": count_rows(attended_attendance, "staff_member__name"),
        "instructor_quality": instructor_quality_rows(attendance),
        "by_service": count_rows(attendance, "pricing_option__name"),
        "attended_by_service": count_rows(attended_attendance, "pricing_option__name"),
        "by_hour": scheduled_attendance_hour_rows(request, start, end),
        "attended_by_hour": scheduled_attendance_hour_rows(request, start, end, attended_only=True),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_view(request):
    return Response(attendance_payload(request))


def retention_payload(request, start=None, end=None, sample_limit=25):
    start, end, months, statuses = membership_status_queryset(request, start=start, end=end)
    previous_members = statuses.filter(previous_month_member=True).count()
    current_members = statuses.filter(current_month_member=True).count()
    retained = statuses.filter(status=MembershipMonthStatus.STATUS_RETAINED).count()
    new_members = statuses.filter(status=MembershipMonthStatus.STATUS_NEW).count()
    new_non_member_rows = new_non_member_purchase_rows(
        request,
        start,
        end,
        exclude_client_months=statuses.filter(
            status=MembershipMonthStatus.STATUS_NEW,
        ).values_list("client_id", "month"),
    )
    reactivated = statuses.filter(status=MembershipMonthStatus.STATUS_REACTIVATED).count()
    not_renewed = statuses.filter(status=MembershipMonthStatus.STATUS_NOT_RENEWED)
    not_renewed_count = not_renewed.count()
    not_renewed_unassigned_studio = not_renewed.filter(studio__isnull=True).count()
    not_renewed_activity = not_renewed_activity_summary(not_renewed)
    tracked_products = filtered_by_site(PricingOption.objects.filter(track_retention=True), request).count()
    current_members_by_month = {
        row["month"].isoformat(): row["total"]
        for row in statuses.filter(current_month_member=True).values("month").annotate(total=Count("id"))
    }
    not_renewed_members_by_month = {
        row["month"].isoformat(): row["total"]
        for row in statuses.filter(status=MembershipMonthStatus.STATUS_NOT_RENEWED).values("month").annotate(total=Count("id"))
    }
    not_renewed_unassigned_studio_by_month = {
        row["month"].isoformat(): row["total"]
        for row in statuses.filter(
            status=MembershipMonthStatus.STATUS_NOT_RENEWED,
            studio__isnull=True,
        ).values("month").annotate(total=Count("id"))
    }
    current_member_mix = [
        {
            "name": row["source_purchase__pricing_option__name"] or "N/A",
            "total": row["total"],
        }
        for row in statuses.filter(current_month_member=True)
        .values("source_purchase__pricing_option__name")
        .annotate(total=Count("id"))
        .order_by("-total")
    ]
    renewal_rate_by_month = {}
    for month in months:
        month_statuses = statuses.filter(month=month)
        month_previous = month_statuses.filter(previous_month_member=True).count()
        month_retained = month_statuses.filter(status=MembershipMonthStatus.STATUS_RETAINED).count()
        renewal_rate_by_month[month.isoformat()] = percentage(month_retained, month_previous)
    not_renewed_sample_rows = []
    if sample_limit:
        not_renewed_sample_rows = sort_not_renewed_rows(
            serialize_membership_status_rows(not_renewed.order_by("client__name"))
        )[:sample_limit]

    return {
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "months": [month.isoformat() for month in months],
        "snapshot_rows": statuses.count(),
        "tracked_pricing_options": tracked_products,
        "previous_month_members": previous_members,
        "current_month_members": current_members,
        "retained_members": retained,
        "new_members": new_members,
        "new_non_members": len(new_non_member_rows),
        "reactivated_members": reactivated,
        "not_renewed_services": not_renewed_count,
        "not_renewed_members": not_renewed_count,
        "not_renewed_unassigned_studio": not_renewed_unassigned_studio,
        "not_renewed_inactive": not_renewed_activity["inactive"],
        "not_renewed_attending_unpaid": not_renewed_activity["attending_unpaid"],
        "not_renewed_attending_paid": not_renewed_activity["attending_paid"],
        "not_renewed_post_expiration_attendance": not_renewed_activity["attendance_count"],
        "not_renewed_post_expiration_unpaid_attendance": not_renewed_activity["unpaid_attendance_count"],
        "not_renewed_post_expiration_paid_attendance": not_renewed_activity["paid_attendance_count"],
        "not_renewed_post_expiration_revenue": not_renewed_activity["revenue"] if can_view_money(request) else None,
        "renewal_rate": percentage(retained, previous_members),
        "churn_rate": percentage(not_renewed_count, previous_members),
        "not_renewed_value": money_value(request, money_sum(not_renewed, "membership_value")),
        "current_month_members_by_month": current_members_by_month,
        "current_member_mix": current_member_mix,
        "not_renewed_members_by_month": not_renewed_members_by_month,
        "not_renewed_unassigned_studio_by_month": not_renewed_unassigned_studio_by_month,
        "renewal_rate_by_month": renewal_rate_by_month,
        "not_renewed_clients": mask_membership_money_rows(request, not_renewed_sample_rows),
        "retained_samples": mask_membership_money_rows(request, serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_RETAINED).order_by("month", "client__name")[:sample_limit]
        )),
        "new_member_samples": mask_membership_money_rows(request, serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_NEW).order_by("month", "client__name")[:sample_limit]
        )),
        "new_non_member_samples": new_non_member_rows[:sample_limit],
        "reactivated_samples": mask_membership_money_rows(request, serialize_membership_status_rows(
            statuses.filter(status=MembershipMonthStatus.STATUS_REACTIVATED).order_by("month", "client__name")[:sample_limit]
        )),
        "definition": (
            "La retencion mensual usa snapshots. Un cliente cuenta como miembro de un mes si tuvo al menos "
            "15 dias cubiertos por productos marcados con track_retention. Not renewed se cuenta en el mes "
            "en que el cliente deja de ser miembro, no en el mes en que expiro el servicio anterior."
        ),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_view(request):
    return Response(retention_payload(request))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_followup_view(request):
    start, end, _, statuses = membership_status_queryset(request)
    status_value = request.query_params.get("status", "not_renewed")
    search = str(request.query_params.get("search") or "").strip().casefold()
    activity_filter = str(request.query_params.get("activity") or "all").strip()
    status_map = {
        "retained": MembershipMonthStatus.STATUS_RETAINED,
        "renewed": MembershipMonthStatus.STATUS_RETAINED,
        "new": MembershipMonthStatus.STATUS_NEW,
        "reactivated": MembershipMonthStatus.STATUS_REACTIVATED,
        "not_renewed": MembershipMonthStatus.STATUS_NOT_RENEWED,
    }
    if status_value == "new_non_members":
        rows = new_non_member_purchase_rows(
            request,
            start,
            end,
            exclude_client_months=statuses.filter(
                status=MembershipMonthStatus.STATUS_NEW,
            ).values_list("client_id", "month"),
        )
    else:
        queryset = statuses.filter(status=status_map.get(status_value, MembershipMonthStatus.STATUS_NOT_RENEWED))
        rows = mask_membership_money_rows(
            request,
            serialize_membership_status_rows(queryset.order_by("month", "client__name")),
        )

    if search:
        rows = [
            row for row in rows
            if search in str(row.get("client") or "").casefold()
            or search in str(row.get("client_mindbody_id") or "").casefold()
            or search in str(row.get("service") or "").casefold()
            or search in str(row.get("studio") or "").casefold()
        ]

    activity_counts = {
        "all": len(rows),
        "attending_unpaid": 0,
        "attending_paid": 0,
        "inactive": 0,
    }
    if status_value == "not_renewed":
        for row in rows:
            activity_status = row.get("not_renewed_activity_status") or "inactive"
            if activity_status in activity_counts:
                activity_counts[activity_status] += 1
        if activity_filter in NOT_RENEWED_ACTIVITY_ORDER:
            rows = [
                row for row in rows
                if row.get("not_renewed_activity_status") == activity_filter
            ]

    if status_value == "not_renewed":
        rows = sort_not_renewed_rows(rows)
    else:
        rows.sort(key=lambda row: (row.get("month") or "", row.get("client") or ""))
    return Response({
        "status": status_value,
        "activity": activity_filter,
        "activity_counts": activity_counts,
        "count": len(rows),
        "rows": rows,
    })


def serialize_retention_activity_visit(request, visit):
    return {
        "id": visit.id,
        "date": visit.visit_date.isoformat(),
        "time": visit.visit_time_raw,
        "studio": visit.visit_studio.name,
        "studio_id": visit.visit_studio_id,
        "pricing_option": visit.pricing_option.name if visit.pricing_option else "N/A",
        "payment_status": "paid" if (visit.revenue or Decimal("0.00")) > 0 else "unpaid",
        "revenue": money_value(request, visit.revenue),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_followup_activity_view(request, snapshot_id):
    statuses = scoped_queryset_for_user(
        MembershipMonthStatus.objects.select_related(
            "client",
            "site",
            "studio",
            "source_purchase",
        ),
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    status = statuses.filter(pk=snapshot_id).first()
    if not status:
        return Response({"detail": "Retention snapshot not found."}, status=404)
    if status.status != MembershipMonthStatus.STATUS_NOT_RENEWED:
        return Response(
            {"detail": "Activity details are available only for not renewed snapshots."},
            status=400,
        )
    if not status.source_purchase or not status.source_purchase.expiration_date:
        return Response(
            {"detail": "The membership expiration date is unavailable for this snapshot."},
            status=400,
        )

    followup_start = status.source_purchase.expiration_date + timedelta(days=1)
    followup_end = month_end(status.month)
    later_start = followup_end + timedelta(days=1)
    later_end = timezone.localdate()
    visits = (
        scoped_queryset_for_user(
            AttendanceVisit.objects.all(),
            request.user,
            site_field="site_id",
            studio_field="visit_studio_id",
        )
        .filter(
            site_id=status.site_id,
            client_id=status.client_id,
            visit_date__gte=followup_start,
            visit_date__lte=later_end,
            no_show=False,
            late_cancel=False,
        )
        .select_related("visit_studio", "pricing_option")
        .order_by("visit_date", "visit_time_raw", "id")
    )
    followup_visits = [
        serialize_retention_activity_visit(request, visit)
        for visit in visits
        if visit.visit_date <= followup_end
    ]
    later_visits = [
        serialize_retention_activity_visit(request, visit)
        for visit in visits
        if later_start <= visit.visit_date <= later_end
    ]
    return Response({
        "snapshot_id": status.id,
        "client": status.client.name,
        "client_id": status.client_id,
        "snapshot_month": status.month.isoformat(),
        "last_tracked_purchase": {
            "service": service_label(status.source_purchase),
            "studio": (
                status.source_purchase.studio.name
                if status.source_purchase.studio
                else status.studio.name
                if status.studio
                else "Unknown"
            ),
            "sale_date": status.source_purchase.sale_date.isoformat(),
            "activation_date": (
                status.source_purchase.activation_date.isoformat()
                if status.source_purchase.activation_date
                else None
            ),
            "expiration_date": status.source_purchase.expiration_date.isoformat(),
        },
        "activity_status": (
            "attending_paid"
            if any(visit["payment_status"] == "paid" for visit in followup_visits)
            else "attending_unpaid"
            if followup_visits
            else "inactive"
        ),
        "followup_period": {
            "from": followup_start.isoformat(),
            "to": followup_end.isoformat(),
            "visits": followup_visits,
        },
        "later_period": {
            "from": later_start.isoformat(),
            "to": later_end.isoformat(),
            "visits": later_visits,
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_purchase_history_view(request, snapshot_id):
    statuses = scoped_queryset_for_user(
        MembershipMonthStatus.objects.select_related("client", "site"),
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    status = statuses.filter(pk=snapshot_id).first()
    if not status:
        return Response({"detail": "Retention snapshot not found."}, status=404)

    purchases = (
        scoped_queryset_for_user(
            ServicePurchase.objects.all(),
            request.user,
            site_field="site_id",
            studio_field="studio_id",
            include_null_studio=True,
        )
        .filter(
            site_id=status.site_id,
            client_id=status.client_id,
        )
        .select_related("pricing_option", "studio")
        .order_by("-sale_date", "-id")
    )
    return Response({
        "snapshot_id": status.id,
        "client": status.client.name,
        "client_id": status.client_id,
        "count": purchases.count(),
        "purchases": [
            {
                "id": purchase.id,
                "service": service_label(purchase),
                "studio": purchase.studio.name if purchase.studio else "Unknown",
                "studio_id": purchase.studio_id,
                "sale_date": purchase.sale_date.isoformat(),
                "activation_date": (
                    purchase.activation_date.isoformat()
                    if purchase.activation_date
                    else None
                ),
                "expiration_date": (
                    purchase.expiration_date.isoformat()
                    if purchase.expiration_date
                    else None
                ),
                "amount": money_value(request, purchase.total_amount),
            }
            for purchase in purchases
        ],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_client_purchase_history_view(request, client_id):
    purchases = (
        scoped_queryset_for_user(
            ServicePurchase.objects.select_related("client", "pricing_option", "studio"),
            request.user,
            site_field="site_id",
            studio_field="studio_id",
            include_null_studio=True,
        )
        .filter(client_id=client_id)
        .order_by("-sale_date", "-id")
    )
    first_purchase = purchases.first()
    if not first_purchase:
        return Response({"detail": "Client purchase history not found."}, status=404)
    return Response({
        "client": first_purchase.client.name,
        "client_id": first_purchase.client_id,
        "count": purchases.count(),
        "purchases": [
            {
                "id": purchase.id,
                "service": service_label(purchase),
                "studio": purchase.studio.name if purchase.studio else "Unknown",
                "studio_id": purchase.studio_id,
                "sale_date": purchase.sale_date.isoformat(),
                "activation_date": (
                    purchase.activation_date.isoformat()
                    if purchase.activation_date
                    else None
                ),
                "expiration_date": (
                    purchase.expiration_date.isoformat()
                    if purchase.expiration_date
                    else None
                ),
                "amount": money_value(request, purchase.total_amount),
            }
            for purchase in purchases
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_membership_months_view(request):
    denied = capability_error(request, "can_edit_data")
    if denied:
        return denied

    start = parse_date(request.data.get("date_from") or request.query_params.get("date_from"))
    end = parse_date(request.data.get("date_to") or request.query_params.get("date_to"))
    month_value = request.data.get("month") or request.query_params.get("month")
    if month_value and not start:
        start = parse_date(f"{month_value}-01")
        end = month_end(start) if start else None
    if not start or not end:
        start, end = date_bounds(request)

    site_id = request.data.get("site") or request.query_params.get("site")
    sites = scoped_queryset_for_user(Site.objects.all(), request.user, site_field="id")
    if site_id:
        sites = sites.filter(id=site_id)
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_client_metrics_view(request):
    denied = capability_error(request, "can_reset_data")
    if denied:
        return denied

    start = parse_date(request.data.get("date_from") or request.query_params.get("date_from"))
    end = parse_date(request.data.get("date_to") or request.query_params.get("date_to"))
    month_value = request.data.get("month") or request.query_params.get("month")
    if month_value and not start:
        start = parse_date(f"{month_value}-01")
        end = month_end(start) if start else None
    if not start or not end:
        return Response(
            {"detail": "date_from and date_to, or month, are required."},
            status=400,
        )
    if start > end:
        return Response(
            {"detail": "date_from cannot be after date_to."},
            status=400,
        )

    site_id = request.data.get("site") or request.query_params.get("site")
    sites = scoped_queryset_for_user(Site.objects.all(), request.user, site_field="id")
    if site_id:
        sites = sites.filter(id=site_id)
    if not sites.exists():
        return Response({"detail": "No accessible sites found."}, status=404)

    from analytics.client_metrics import (
        rebuild_client_metrics_for_periods,
        weeks_between,
    )

    results = []
    for site in sites:
        retention = [
            {
                "month": target_month.isoformat(),
                "rows": rebuild_membership_month(site.id, target_month),
            }
            for target_month in months_between(start, end)
        ]
        monthly = [
            {
                "month": row["month"],
                "rows": ClientStudioMonthlyMetric.objects.filter(
                    site_id=site.id,
                    month=parse_date(row["month"]),
                ).count(),
            }
            for row in retention
        ]
        result = rebuild_client_metrics_for_periods(
            site.id,
            weeks=weeks_between(start, end),
        )
        result["monthly"] = monthly
        result["total_monthly_rows"] = sum(row["rows"] for row in monthly)
        results.append({
            "site": site.name,
            "site_id": site.id,
            "retention": retention,
            **result,
        })
    return Response({
        "date_range": {
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
        "sites": results,
        "total_monthly_rows": sum(row["total_monthly_rows"] for row in results),
        "total_weekly_rows": sum(row["total_weekly_rows"] for row in results),
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
    denied = capability_error(request, "can_edit_data")
    if denied:
        return denied

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


def serialize_candidate_class(scheduled_class):
    return {
        "id": scheduled_class.id,
        "name": scheduled_class.name,
        "site": scheduled_class.site.name,
        "studio": scheduled_class.studio.name,
        "room": scheduled_class.room.name if scheduled_class.room else "N/A",
        "staff_member": scheduled_class.staff_member.name if scheduled_class.staff_member else "N/A",
        "date": scheduled_class.class_date.isoformat(),
        "start_time": scheduled_class.start_time.strftime("%H:%M"),
        "end_time": scheduled_class.end_time.strftime("%H:%M"),
        "capacity": scheduled_class.capacity,
        "source": scheduled_class.source,
        "status": scheduled_class.status,
    }


def candidate_classes_for_match(match):
    visit = match.attendance_visit
    candidate_ids = list(match.candidate_class_ids or [])
    candidates = ScheduledClass.objects.select_related("site", "studio", "room", "staff_member").filter(
        site_id=visit.site_id,
        studio_id=visit.visit_studio_id,
        class_date=visit.visit_date,
    ).exclude(status__in=[ScheduledClass.STATUS_CANCELLED, ScheduledClass.STATUS_UNAVAILABLE])
    if candidate_ids:
        candidates = candidates.filter(Q(id__in=candidate_ids) | Q(start_time=parse_time_value(visit.visit_time_raw)))
    else:
        visit_time = parse_time_value(visit.visit_time_raw)
        if visit_time:
            candidates = candidates.filter(start_time=visit_time)
    return sorted(candidates, key=lambda item: (item.start_time, item.room.name if item.room else "", item.name))


def serialize_unresolved_match(match, request=None):
    visit = match.attendance_visit
    candidates = candidate_classes_for_match(match)
    return {
        "id": match.id,
        "match_method": match.match_method,
        "confidence": decimal_value(match.confidence),
        "notes": match.notes,
        "candidate_class_ids": match.candidate_class_ids or [],
        "attendance_visit": {
            "id": visit.id,
            "site": visit.site.name,
            "site_id": visit.site_id,
            "studio": visit.visit_studio.name,
            "studio_id": visit.visit_studio_id,
            "date": visit.visit_date.isoformat(),
            "time": visit.visit_time_raw,
            "client": visit.client.name,
            "client_mindbody_id": visit.client.mindbody_id,
            "instructor": visit.staff_member.name if visit.staff_member else "N/A",
            "service": visit.pricing_option.name if visit.pricing_option else "N/A",
            "revenue": money_value(request, visit.revenue) if request else decimal_value(visit.revenue),
        },
        "candidates": [serialize_candidate_class(candidate) for candidate in candidates],
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def unresolved_attendance_matches_view(request):
    if request.method == "POST":
        denied = capability_error(request, "can_edit_data")
        if denied:
            return denied

        match_id = request.data.get("match")
        scheduled_class_id = request.data.get("scheduled_class")
        if not match_id or not scheduled_class_id:
            return Response({"error": "match and scheduled_class are required."}, status=400)

        try:
            match_queryset = scoped_queryset_for_user(
                AttendanceClassMatch.objects.select_related("attendance_visit"),
                request.user,
                site_field="attendance_visit__site_id",
                studio_field="attendance_visit__visit_studio_id",
            )
            scheduled_queryset = scoped_queryset_for_user(
                ScheduledClass.objects.all(),
                request.user,
                site_field="site_id",
                studio_field="studio_id",
            )
            match = match_queryset.get(id=match_id)
            scheduled_class = scheduled_queryset.get(id=scheduled_class_id)
        except (AttendanceClassMatch.DoesNotExist, ScheduledClass.DoesNotExist):
            return Response({"error": "Match or scheduled class not found."}, status=404)

        visit = match.attendance_visit
        if (
            scheduled_class.site_id != visit.site_id
            or scheduled_class.studio_id != visit.visit_studio_id
            or scheduled_class.class_date != visit.visit_date
        ):
            return Response({"error": "Scheduled class must match the attendance site, studio and date."}, status=400)
        if scheduled_class.status in [ScheduledClass.STATUS_CANCELLED, ScheduledClass.STATUS_UNAVAILABLE]:
            return Response({"error": "Cannot match attendance to a cancelled or unavailable class."}, status=400)

        match.scheduled_class = scheduled_class
        match.match_method = AttendanceClassMatch.METHOD_MANUAL
        match.confidence = Decimal("1.00")
        match.notes = "Manually matched from unresolved attendance review."
        match.save()
        return Response({"matched": serialize_unresolved_match(match, request)})

    start, end = date_bounds(request)
    queryset = AttendanceClassMatch.objects.select_related(
        "attendance_visit",
        "attendance_visit__site",
        "attendance_visit__client",
        "attendance_visit__staff_member",
        "attendance_visit__visit_studio",
        "attendance_visit__pricing_option",
    ).filter(
        attendance_visit__visit_date__range=(start, end),
        attendance_visit__no_show=False,
        attendance_visit__late_cancel=False,
        match_method__in=[
            AttendanceClassMatch.METHOD_AMBIGUOUS,
            AttendanceClassMatch.METHOD_UNMATCHED,
        ],
    )
    queryset = scoped_queryset_for_user(
        queryset,
        request.user,
        site_field="attendance_visit__site_id",
        studio_field="attendance_visit__visit_studio_id",
    )
    site_id = request.query_params.get("site")
    studio_id = request.query_params.get("studio")
    match_method = request.query_params.get("match_method")
    search = str(request.query_params.get("search") or "").strip()
    if site_id:
        queryset = queryset.filter(attendance_visit__site_id=site_id)
    if studio_id:
        queryset = queryset.filter(attendance_visit__visit_studio_id=studio_id)
    if match_method in [AttendanceClassMatch.METHOD_AMBIGUOUS, AttendanceClassMatch.METHOD_UNMATCHED]:
        queryset = queryset.filter(match_method=match_method)
    if search:
        queryset = queryset.filter(
            Q(attendance_visit__client__name__icontains=search)
            | Q(attendance_visit__client__mindbody_id__icontains=search)
            | Q(attendance_visit__staff_member__name__icontains=search)
            | Q(attendance_visit__pricing_option__name__icontains=search)
        )

    rows = list(queryset.order_by("attendance_visit__visit_date", "attendance_visit__visit_time_raw")[:200])
    return Response({
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "count": queryset.count(),
        "rows": [serialize_unresolved_match(match, request) for match in rows],
    })


def occupation_payload(request, start=None, end=None):
    start, end, attendance, _, _ = base_querysets(request, start=start, end=end)
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

    return {
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
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def occupation_view(request):
    return Response(occupation_payload(request))


def previous_month_range(start):
    previous = add_months(month_start(start), -1)
    return previous, month_end(previous)


def previous_week_range(start, end):
    return start - timedelta(days=7), end - timedelta(days=7)


def month_trend_ranges(start, months=6):
    end_month = month_start(start)
    return [
        (target_month, month_end(target_month))
        for target_month in (add_months(end_month, offset) for offset in range(-(months - 1), 1))
    ]


def week_trend_ranges(start, end, weeks=6):
    duration_days = (end - start).days
    return [
        (week_start, week_start + timedelta(days=duration_days))
        for week_start in (start + timedelta(days=7 * offset) for offset in range(-(weeks - 1), 1))
    ]


def occupancy_hour_matrix_for_dates(request, target_dates):
    target_dates = sorted(set(target_dates))
    if not target_dates:
        return {"days": [], "hours": [], "cells": []}

    scheduled_classes = filtered_schedule(
        ScheduledClass.objects.filter(
            class_date__in=target_dates,
            status=ScheduledClass.STATUS_SCHEDULED,
        ),
        request,
    )
    scheduled_by_class = {}
    cells = {}
    hours = set()
    active_dates = set()

    for scheduled_class in scheduled_classes:
        if not scheduled_class.start_time:
            continue
        hour = scheduled_class.start_time.replace(minute=0, second=0, microsecond=0)
        key = (scheduled_class.class_date, hour)
        cell = cells.setdefault(key, {
            "date": scheduled_class.class_date.isoformat(),
            "weekday": weekday_name(scheduled_class.class_date),
            "hour": hour.strftime("%H:%M"),
            "scheduled_capacity": 0,
            "attended": 0,
            "scheduled_classes": 0,
        })
        cell["scheduled_capacity"] += scheduled_class.capacity
        cell["scheduled_classes"] += 1
        scheduled_by_class[scheduled_class.id] = key
        hours.add(hour)
        active_dates.add(scheduled_class.class_date)

    if scheduled_by_class:
        class_match_rows = (
            AttendanceClassMatch.objects.filter(
                scheduled_class_id__in=scheduled_by_class,
                attendance_visit__no_show=False,
                attendance_visit__late_cancel=False,
            )
            .values("scheduled_class_id")
            .annotate(total=Count("id"))
        )
        for row in class_match_rows:
            key = scheduled_by_class.get(row["scheduled_class_id"])
            if key in cells:
                cells[key]["attended"] += row["total"]

    for cell in cells.values():
        cell["unused_capacity"] = max(0, cell["scheduled_capacity"] - cell["attended"])
        cell["occupation_rate"] = percentage(cell["attended"], cell["scheduled_capacity"])

    days = [
        {
            "date": item_date.isoformat(),
            "weekday": weekday_name(item_date),
            "label": f"{weekday_name(item_date)} {item_date.strftime('%d-%m')}",
        }
        for item_date in target_dates
        if item_date in active_dates
    ]

    return {
        "days": days,
        "hours": [hour.strftime("%H:%M") for hour in sorted(hours)],
        "cells": sorted(cells.values(), key=lambda row: (row["date"], row["hour"])),
    }


def occupancy_hour_matrix_payload(request, start=None, end=None):
    start, end = date_bounds(request, start=start, end=end)
    weeks = int(request.query_params.get("weeks") or 6)
    weeks = min(max(weeks, 2), 8)
    current_week_dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    history_dates = []
    for weekday_index in range(7):
        selected_week_date = start + timedelta(days=(weekday_index - start.weekday()) % 7)
        for offset in range(-(weeks - 1), 1):
            history_dates.append(selected_week_date + timedelta(days=offset * 7))

    return {
        "mode": "weekly",
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "weeks": weeks,
        "current_week": occupancy_hour_matrix_for_dates(request, current_week_dates),
        "weekday_history": occupancy_hour_matrix_for_dates(request, history_dates),
    }


def weekly_trend_row(request, start, end):
    summary = summary_payload(request, start=start, end=end)
    occupation = occupation_payload(request, start=start, end=end)
    conversion = trial_conversion_payload(request, start=start, end=end, row_limit=0)
    totals = summary["totals"]
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_bookings": totals["attendance_visits"],
        "completed_visits": totals["attended_visits"],
        "no_show_rate": totals["no_show_rate"],
        "late_cancel_rate": totals["late_cancel_rate"],
        "average_revenue_per_attended_visit": totals["average_revenue_per_attended_visit"],
        "active_clients": totals["active_clients"],
        "scheduled_capacity": occupation["scheduled_capacity"],
        "attendance_used": occupation["matched_attended_visits"],
        "scheduled_classes": occupation["available_classes"],
        "closed_or_unavailable_classes": occupation["closed_or_unavailable_classes"],
        "occupation_rate": occupation["occupation_rate"],
        "trial_bookings": conversion["trial_bookings"],
        "attended_trials": conversion["attended_trials"],
        "unique_trial_clients": conversion["unique_trial_clients"],
        "converted_members": conversion["converted_members"],
        "converted_non_members": conversion["converted_non_members"],
        "not_converted_clients": conversion["not_converted_clients"],
        "member_conversion_rate": conversion["member_conversion_rate"],
        "non_member_conversion_rate": conversion["non_member_conversion_rate"],
    }


def weekly_weekday_rows(request, start, end):
    attendance = attendance_payload(request, start=start, end=end)
    occupation = occupation_payload(request, start=start, end=end)
    booking_by_date = {row["date"]: row for row in attendance["booking_quality_by_date"]}
    occupancy_by_date = {row["date"]: row for row in occupation["by_day"]}
    rows = []
    for offset in range((end - start).days + 1):
        target_date = start + timedelta(days=offset)
        date_key = target_date.isoformat()
        booking = booking_by_date.get(date_key, {})
        occupancy = occupancy_by_date.get(date_key, {})
        rows.append({
            "week_start": start.isoformat(),
            "date": date_key,
            "weekday": weekday_name(target_date),
            "total_bookings": booking.get("total", 0),
            "completed_visits": booking.get("attended", 0),
            "no_shows": booking.get("no_shows", 0),
            "late_cancels": booking.get("late_cancels", 0),
            "scheduled_capacity": occupancy.get("capacity", 0),
            "attendance_used": occupancy.get("attended", 0),
            "scheduled_classes": occupancy.get("scheduled_classes", 0),
            "occupation_rate": occupancy.get("occupation_rate", 0),
        })
    return rows


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_monthly_view(request):
    start, end = date_bounds(request)
    previous_start, previous_end = previous_month_range(start)
    return Response({
        "mode": "monthly",
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "current": {
            "summary": summary_payload(request, start=start, end=end),
            "revenue": revenue_payload(request, start=start, end=end),
            "retention": retention_payload(request, start=start, end=end),
            "conversion": trial_conversion_payload(request, start=start, end=end),
        },
        "comparison": {
            "date_range": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
            "summary": summary_payload(request, start=previous_start, end=previous_end),
            "retention": retention_payload(request, start=previous_start, end=previous_end),
            "conversion": trial_conversion_payload(request, start=previous_start, end=previous_end),
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_monthly_trends_view(request):
    start, _ = date_bounds(request)
    rows = []
    for month_start_value, month_end_value in month_trend_ranges(start):
        summary = summary_payload(request, start=month_start_value, end=month_end_value)
        retention = retention_payload(request, start=month_start_value, end=month_end_value, sample_limit=0)
        conversion = trial_conversion_payload(request, start=month_start_value, end=month_end_value, row_limit=0)
        totals = summary["totals"]
        rows.append({
            "month": month_start_value.isoformat(),
            "sales_revenue": totals["sales_revenue"],
            "visit_revenue": totals["visit_revenue"],
            "average_ticket": totals["average_ticket"],
            "previous_members": retention["previous_month_members"],
            "current_members": retention["current_month_members"],
            "current_member_mix": retention["current_member_mix"],
            "retained_members": retention["retained_members"],
            "new_members": retention["new_members"],
            "reactivated_members": retention["reactivated_members"],
            "not_renewed_members": retention["not_renewed_members"],
            "not_renewed_unassigned_studio": retention["not_renewed_unassigned_studio"],
            "renewal_rate": retention["renewal_rate"],
            "churn_rate": retention["churn_rate"],
            "not_renewed_value": retention["not_renewed_value"],
            "trial_bookings": conversion["trial_bookings"],
            "attended_trials": conversion["attended_trials"],
            "unique_trial_clients": conversion["unique_trial_clients"],
            "converted_members": conversion["converted_members"],
            "converted_non_members": conversion["converted_non_members"],
            "not_converted_clients": conversion["not_converted_clients"],
            "member_conversion_rate": conversion["member_conversion_rate"],
            "non_member_conversion_rate": conversion["non_member_conversion_rate"],
        })
    return Response({
        "mode": "monthly",
        "months": rows,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_monthly_retention_tables_view(request):
    start, end, _, statuses = membership_status_queryset(request)
    limit_value = request.query_params.get("limit")
    limit = int(limit_value) if limit_value else None
    status_filters = {
        "not_renewed": MembershipMonthStatus.STATUS_NOT_RENEWED,
        "retained": MembershipMonthStatus.STATUS_RETAINED,
        "new_members": MembershipMonthStatus.STATUS_NEW,
        "reactivated": MembershipMonthStatus.STATUS_REACTIVATED,
    }
    tables = {}
    for key, status_value in status_filters.items():
        queryset = statuses.filter(status=status_value).order_by("month", "client__name")
        rows = serialize_membership_status_rows(queryset)
        if key == "not_renewed":
            rows = sort_not_renewed_rows(rows)
        tables[key] = {
            "count": queryset.count(),
            "rows": mask_membership_money_rows(
                request,
                rows[:limit] if limit is not None else rows,
            ),
        }
    new_non_member_rows = new_non_member_purchase_rows(
        request,
        start,
        end,
        exclude_client_months=statuses.filter(
            status=MembershipMonthStatus.STATUS_NEW,
        ).values_list("client_id", "month"),
    )
    tables["new_non_members"] = {
        "count": len(new_non_member_rows),
        "rows": (
            new_non_member_rows[:limit]
            if limit is not None
            else new_non_member_rows
        ),
    }
    return Response({
        "mode": "monthly",
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "limit": limit,
        "tables": tables,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_weekly_view(request):
    start, end = date_bounds(request)
    previous_start, previous_end = previous_week_range(start, end)
    return Response({
        "mode": "weekly",
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "current": {
            "summary": summary_payload(request, start=start, end=end),
            "attendance": attendance_payload(request, start=start, end=end),
            "occupation": occupation_payload(request, start=start, end=end),
            "conversion": trial_conversion_payload(request, start=start, end=end),
        },
        "comparison": {
            "date_range": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
            "summary": summary_payload(request, start=previous_start, end=previous_end),
            "attendance": attendance_payload(request, start=previous_start, end=previous_end),
            "occupation": occupation_payload(request, start=previous_start, end=previous_end),
            "conversion": trial_conversion_payload(request, start=previous_start, end=previous_end),
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_weekly_trends_view(request):
    start, end = date_bounds(request)
    weeks = week_trend_ranges(start, end)
    week_rows = [weekly_trend_row(request, week_start, week_end) for week_start, week_end in weeks]
    weekday_rows = []
    for week_start, week_end in weeks:
        weekday_rows.extend(weekly_weekday_rows(request, week_start, week_end))
    return Response({
        "mode": "weekly",
        "weeks": week_rows,
        "weekday_rows": weekday_rows,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_weekly_occupancy_hour_matrix_view(request):
    return Response(occupancy_hour_matrix_payload(request))
