from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from django.db.models.functions import Coalesce, TruncDate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core_data.models import AttendanceVisit, SaleLine, ServicePurchase, Site


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
    expired = filtered_by_site(ServicePurchase.objects.filter(expiration_date__range=(start, end)), request)
    future_window = date.today() + timedelta(days=30)
    upcoming = filtered_by_site(
        ServicePurchase.objects.filter(expiration_date__gte=date.today(), expiration_date__lte=future_window),
        request,
    )
    return Response({
        "services_sold": services.count(),
        "expired_services": expired.count(),
        "upcoming_expirations_30_days": upcoming.count(),
        "revenue_from_services_sold": decimal_value(money_sum(services, "total_amount")),
        "note": "La reactivacion requiere comparar compras futuras del mismo cliente despues de la fecha de expiracion. Se implementara en la siguiente fase.",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def occupation_view(request):
    return Response({
        "status": "pending_capacity_model",
        "formula": "ocupacion = asistencias reales / capacidad programada",
        "missing_data": [
            "salas por estudio",
            "tipo de sala",
            "capacidad de reformers o cupos",
            "horarios programados",
            "duracion de sesiones",
        ],
    })
