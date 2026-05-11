from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from django.db.models.functions import Coalesce, TruncDate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core_data.models import AttendanceVisit, PricingOption, SaleLine, ScheduledClass, ServicePurchase, Site, StudioClosure


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def date_bounds(request):
    today = date.today()
    start = parse_date(request.query_params.get("date_from")) or today - timedelta(days=30)
    end = parse_date(request.query_params.get("date_to")) or today
    return start, end


def filtered_by_site(queryset, request):
    site_id = request.query_params.get("site")
    if site_id:
        queryset = queryset.filter(site_id=site_id)
    return queryset


def money_sum(queryset, field):
    return queryset.aggregate(
        total=Coalesce(Sum(field), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
    )["total"]


def decimal_value(value):
    return float(value or Decimal("0.00"))


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
        raw = str(value or "").strip()
        if not raw:
            continue
        hour = raw.split(":")[0].strip()
        if hour.isdigit():
            hour_number = int(hour)
            counts[hour_number] = counts.get(hour_number, 0) + 1
    return [{"hour": hour, "total": counts[hour]} for hour in sorted(counts)]


def parse_time_value(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(raw.upper(), fmt).time().replace(second=0, microsecond=0)
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


def average(values):
    return round(sum(values) / len(values), 2) if values else None


def percentage(numerator, denominator):
    return round(numerator / denominator * 100, 2) if denominator else 0


def base_querysets(request):
    start, end = date_bounds(request)
    attendance = filtered_by_site(AttendanceVisit.objects.filter(visit_date__range=(start, end)), request)
    sales = filtered_by_site(SaleLine.objects.filter(sale_date__range=(start, end)), request)
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

    return Response({
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
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
            "sale_lines": sales.count(),
            "service_purchases": services.count(),
        },
        "site_count": Site.objects.count(),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revenue_view(request):
    _, _, attendance, sales, services = base_querysets(request)
    return Response({
        "sales_revenue": decimal_value(money_sum(sales, "paid_total")),
        "service_revenue": decimal_value(money_sum(services, "total_amount")),
        "visit_revenue": decimal_value(money_sum(attendance, "revenue")),
        "sales_by_date": date_money_rows(sales, "sale_date", "paid_total"),
        "services_by_date": date_money_rows(services, "sale_date", "total_amount"),
        "visits_by_date": date_money_rows(attendance, "visit_date", "revenue"),
        "by_payment_method": money_rows(sales, "payment_method__name", "paid_total"),
        "by_studio": money_rows(sales, "studio__name", "paid_total"),
        "by_service": money_rows(services, "pricing_option__name", "total_amount"),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_view(request):
    _, _, attendance, _, _ = base_querysets(request)
    return Response({
        "total": attendance.count(),
        "attended": attendance.filter(no_show=False, late_cancel=False).count(),
        "no_shows": attendance.filter(no_show=True).count(),
        "late_cancels": attendance.filter(late_cancel=True).count(),
        "zero_revenue": attendance.filter(revenue=0).count(),
        "by_date": date_count_rows(attendance, "visit_date"),
        "by_studio": count_rows(attendance, "visit_studio__name"),
        "by_instructor": count_rows(attendance, "staff_member__name"),
        "by_service": count_rows(attendance, "pricing_option__name"),
        "by_hour": attendance_hour_rows(attendance),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retention_view(request):
    start, end, _, _, services = base_querysets(request)
    today = date.today()
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
    future_window = today + timedelta(days=30)
    upcoming = (
        site_filtered_purchases.select_related("client", "pricing_option")
        .filter(expiration_date__gte=today, expiration_date__lte=future_window)
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

    expired_count = expired.count()
    renewed_count = len(renewed)
    not_renewed_count = len(not_renewed)

    return Response({
        "tracked_pricing_options": filtered_by_site(PricingOption.objects.filter(track_retention=True), request).count(),
        "services_sold": services.count(),
        "expired_services": expired_count,
        "renewed_or_reactivated_services": renewed_count,
        "not_renewed_services": not_renewed_count,
        "renewal_rate": round(renewed_count / expired_count * 100, 2) if expired_count else 0,
        "average_days_from_expiration_to_renewal": average(renewal_day_values),
        "upcoming_expirations_30_days": upcoming.count(),
        "revenue_from_services_sold": decimal_value(money_sum(services, "total_amount")),
        "expired_value": decimal_value(money_sum(expired, "total_amount")),
        "not_renewed_value": decimal_value(sum((purchase.total_amount or Decimal("0.00")) for purchase in not_renewed)),
        "not_renewed_clients": [serialize_purchase(purchase, today=today) for purchase in not_renewed[:25]],
        "upcoming_expirations": [serialize_purchase(purchase, today=today) for purchase in upcoming[:25]],
        "renewed_samples": [
            serialize_purchase(purchase, today=today, renewal=renewal)
            for purchase, renewal in renewed[:25]
        ],
        "definition": (
            "La retencion solo analiza productos marcados con track_retention. Un servicio se considera "
            "renovado/reactivado si el mismo cliente tiene una compra posterior a la venta original que "
            "extiende o mantiene una expiracion igual o posterior."
        ),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def occupation_view(request):
    start, end, attendance, _, _ = base_querysets(request)
    scheduled_classes = filtered_by_site(
        ScheduledClass.objects.select_related("site", "studio", "room").filter(class_date__range=(start, end)),
        request,
    )
    closures = list(
        filtered_by_site(
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
    attended_visits = attendance.filter(no_show=False, late_cancel=False)

    attended_by_slot = {}
    for visit in attended_visits.values("site_id", "visit_studio_id", "visit_date", "visit_time_raw"):
        visit_time = parse_time_value(visit["visit_time_raw"])
        if not visit_time:
            continue
        key = (visit["site_id"], visit["visit_studio_id"], visit["visit_date"], visit_time)
        attended_by_slot[key] = attended_by_slot.get(key, 0) + 1

    slots = {}
    by_studio = {}
    by_day = {}
    by_room = {}

    for scheduled_class in available_classes:
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
            "attended": attended_by_slot.get(key, 0),
        })
        slot["capacity"] += scheduled_class.capacity
        slot["scheduled_classes"] += 1

        studio_row = by_studio.setdefault(scheduled_class.studio_id, {
            "name": scheduled_class.studio.name,
            "capacity": 0,
            "attended": 0,
            "scheduled_classes": 0,
        })
        studio_row["capacity"] += scheduled_class.capacity
        studio_row["scheduled_classes"] += 1

        day_key = scheduled_class.class_date.isoformat()
        day_row = by_day.setdefault(day_key, {"date": day_key, "capacity": 0, "attended": 0, "scheduled_classes": 0})
        day_row["capacity"] += scheduled_class.capacity
        day_row["scheduled_classes"] += 1

        room_name = scheduled_class.room.name if scheduled_class.room else "N/A"
        room_key = scheduled_class.room_id or f"none-{scheduled_class.studio_id}"
        room_row = by_room.setdefault(room_key, {
            "name": room_name,
            "studio": scheduled_class.studio.name,
            "capacity": 0,
            "scheduled_classes": 0,
        })
        room_row["capacity"] += scheduled_class.capacity
        room_row["scheduled_classes"] += 1

    total_capacity = 0
    matched_attended = 0
    for key, slot in slots.items():
        total_capacity += slot["capacity"]
        matched_attended += slot["attended"]
        slot["occupation_rate"] = percentage(slot["attended"], slot["capacity"])
        _, studio_id, class_date, _ = key
        by_studio[studio_id]["attended"] += slot["attended"]
        by_day[class_date.isoformat()]["attended"] += slot["attended"]

    for row in by_studio.values():
        row["occupation_rate"] = percentage(row["attended"], row["capacity"])
    for row in by_day.values():
        row["occupation_rate"] = percentage(row["attended"], row["capacity"])

    scheduled_slot_keys = set(slots.keys())
    unscheduled_attended = sum(
        count for key, count in attended_by_slot.items()
        if key not in scheduled_slot_keys
    )

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
        "occupation_rate": percentage(matched_attended, total_capacity),
        "by_studio": sorted(by_studio.values(), key=lambda row: row["name"]),
        "by_day": sorted(by_day.values(), key=lambda row: row["date"]),
        "by_room_capacity": sorted(by_room.values(), key=lambda row: (row["studio"], row["name"])),
        "by_slot": sorted(slots.values(), key=lambda row: (row["date"], row["start_time"], row["studio"]))[:100],
        "note": (
            "La asistencia se empareja por site, estudio, fecha y hora de inicio. Si dos salas del mismo estudio "
            "funcionan a la misma hora, la ocupacion es mas confiable a nivel estudio/franja que a nivel sala "
            "hasta que tengamos una fuente con sala exacta por visita."
        ),
    })
