from calendar import monthrange
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from analytics.models import (
    ClientStudioMonthlyMetric,
    ClientStudioWeeklyMetric,
    MembershipMonthStatus,
)
from core_data.models import AttendanceVisit, SaleLine, ServicePurchase


ZERO = Decimal("0.00")


def month_start(value):
    return value.replace(day=1)


def month_end(value):
    return value.replace(day=monthrange(value.year, value.month)[1])


def week_start(value):
    return value - timedelta(days=value.weekday())


def date_strings(start, end):
    current = start
    values = []
    while current <= end:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def empty_metric():
    return {
        "total_bookings": 0,
        "attended_visits": 0,
        "no_shows": 0,
        "late_cancels": 0,
        "active_week_starts": set(),
        "attendance_revenue": ZERO,
        "service_purchase_count": 0,
        "service_spending": ZERO,
        "membership_spending": ZERO,
        "non_membership_spending": ZERO,
        "general_sales_spending": ZERO,
        "first_visit_date": None,
        "last_visit_date": None,
        "first_purchase_date": None,
        "last_purchase_date": None,
        "active_membership_dates": set(),
        "membership_status": None,
    }


def update_date_bounds(metric, prefix, value):
    first_key = f"first_{prefix}_date"
    last_key = f"last_{prefix}_date"
    if metric[first_key] is None or value < metric[first_key]:
        metric[first_key] = value
    if metric[last_key] is None or value > metric[last_key]:
        metric[last_key] = value


def rebuild_client_studio_monthly_metrics(site_id, target_month):
    target_month = month_start(target_month)
    end = month_end(target_month)
    metrics = defaultdict(empty_metric)

    attendance = AttendanceVisit.objects.filter(
        site_id=site_id,
        visit_date__range=(target_month, end),
    ).iterator()
    for visit in attendance:
        metric = metrics[(visit.client_id, visit.visit_studio_id)]
        metric["total_bookings"] += 1
        metric["no_shows"] += int(visit.no_show)
        metric["late_cancels"] += int(visit.late_cancel)
        metric["attendance_revenue"] += visit.revenue or ZERO
        update_date_bounds(metric, "visit", visit.visit_date)
        if not visit.no_show and not visit.late_cancel:
            metric["attended_visits"] += 1
            metric["active_week_starts"].add(week_start(visit.visit_date).isoformat())

    service_purchases = (
        ServicePurchase.objects.select_related("pricing_option")
        .filter(
            site_id=site_id,
            sale_date__range=(target_month, end),
        )
        .iterator()
    )
    for purchase in service_purchases:
        metric = metrics[(purchase.client_id, purchase.studio_id)]
        amount = purchase.total_amount or ZERO
        metric["service_purchase_count"] += 1
        metric["service_spending"] += amount
        if purchase.pricing_option.track_retention:
            metric["membership_spending"] += amount
        elif not purchase.pricing_option.is_trial_class:
            metric["non_membership_spending"] += amount
        update_date_bounds(metric, "purchase", purchase.sale_date)

    sale_lines = SaleLine.objects.filter(
        site_id=site_id,
        sale_date__range=(target_month, end),
    ).iterator()
    for sale_line in sale_lines:
        metric = metrics[(sale_line.client_id, sale_line.studio_id)]
        metric["general_sales_spending"] += sale_line.paid_total or ZERO
        update_date_bounds(metric, "purchase", sale_line.sale_date)

    tracked_coverage = (
        ServicePurchase.objects.select_related("pricing_option")
        .filter(
            site_id=site_id,
            pricing_option__track_retention=True,
            sale_date__lte=end,
        )
        .filter(Q(expiration_date__gte=target_month) | Q(expiration_date__isnull=True))
        .iterator()
    )
    for purchase in tracked_coverage:
        active_start = purchase.activation_date or purchase.sale_date
        active_end = purchase.expiration_date or end
        if not active_start:
            continue
        overlap_start = max(active_start, target_month)
        overlap_end = min(active_end, end)
        if overlap_start > overlap_end:
            continue
        metric = metrics[(purchase.client_id, purchase.studio_id)]
        metric["active_membership_dates"].update(date_strings(overlap_start, overlap_end))

    statuses = MembershipMonthStatus.objects.filter(
        site_id=site_id,
        month=target_month,
    ).iterator()
    for status in statuses:
        metric = metrics[(status.client_id, status.studio_id)]
        metric["membership_status"] = status.status

    rows = []
    for (client_id, studio_id), metric in metrics.items():
        active_week_starts = sorted(metric["active_week_starts"])
        active_membership_dates = sorted(metric["active_membership_dates"])
        rows.append(
            ClientStudioMonthlyMetric(
                site_id=site_id,
                studio_id=studio_id,
                client_id=client_id,
                month=target_month,
                total_bookings=metric["total_bookings"],
                attended_visits=metric["attended_visits"],
                no_shows=metric["no_shows"],
                late_cancels=metric["late_cancels"],
                active_weeks=len(active_week_starts),
                active_week_starts=active_week_starts,
                attendance_revenue=metric["attendance_revenue"],
                service_purchase_count=metric["service_purchase_count"],
                service_spending=metric["service_spending"],
                membership_spending=metric["membership_spending"],
                non_membership_spending=metric["non_membership_spending"],
                general_sales_spending=metric["general_sales_spending"],
                first_visit_date=metric["first_visit_date"],
                last_visit_date=metric["last_visit_date"],
                first_purchase_date=metric["first_purchase_date"],
                last_purchase_date=metric["last_purchase_date"],
                active_membership_days=len(active_membership_dates),
                active_membership_dates=active_membership_dates,
                membership_status=metric["membership_status"],
            )
        )

    with transaction.atomic():
        ClientStudioMonthlyMetric.objects.filter(
            site_id=site_id,
            month=target_month,
        ).delete()
        ClientStudioMonthlyMetric.objects.bulk_create(rows)
    return len(rows)


def aggregate_client_monthly_metrics(rows):
    totals = {
        "total_bookings": 0,
        "attended_visits": 0,
        "no_shows": 0,
        "late_cancels": 0,
        "attendance_revenue": ZERO,
        "service_purchase_count": 0,
        "service_spending": ZERO,
        "membership_spending": ZERO,
        "non_membership_spending": ZERO,
        "general_sales_spending": ZERO,
        "first_visit_date": None,
        "last_visit_date": None,
        "first_purchase_date": None,
        "last_purchase_date": None,
        "membership_status": None,
    }
    active_week_starts = set()
    active_membership_dates = set()

    for row in rows:
        for field in (
            "total_bookings",
            "attended_visits",
            "no_shows",
            "late_cancels",
            "service_purchase_count",
        ):
            totals[field] += getattr(row, field)
        for field in (
            "attendance_revenue",
            "service_spending",
            "membership_spending",
            "non_membership_spending",
            "general_sales_spending",
        ):
            totals[field] += getattr(row, field) or ZERO
        active_week_starts.update(row.active_week_starts)
        active_membership_dates.update(row.active_membership_dates)
        for prefix in ("visit", "purchase"):
            first_key = f"first_{prefix}_date"
            last_key = f"last_{prefix}_date"
            first_value = getattr(row, first_key)
            last_value = getattr(row, last_key)
            if first_value and (totals[first_key] is None or first_value < totals[first_key]):
                totals[first_key] = first_value
            if last_value and (totals[last_key] is None or last_value > totals[last_key]):
                totals[last_key] = last_value
        if row.membership_status:
            totals["membership_status"] = row.membership_status

    totals["active_weeks"] = len(active_week_starts)
    totals["active_week_starts"] = sorted(active_week_starts)
    totals["active_membership_days"] = len(active_membership_dates)
    totals["active_membership_dates"] = sorted(active_membership_dates)
    return totals


def empty_weekly_metric():
    return {
        "total_bookings": 0,
        "attended_visits": 0,
        "no_shows": 0,
        "late_cancels": 0,
        "attendance_revenue": ZERO,
        "active_membership_dates": set(),
    }


def rebuild_client_studio_weekly_metrics(site_id, target_week):
    start = week_start(target_week)
    end = start + timedelta(days=6)
    metrics = defaultdict(empty_weekly_metric)

    attendance = AttendanceVisit.objects.filter(
        site_id=site_id,
        visit_date__range=(start, end),
    ).iterator()
    for visit in attendance:
        metric = metrics[(visit.client_id, visit.visit_studio_id)]
        metric["total_bookings"] += 1
        metric["no_shows"] += int(visit.no_show)
        metric["late_cancels"] += int(visit.late_cancel)
        metric["attendance_revenue"] += visit.revenue or ZERO
        if not visit.no_show and not visit.late_cancel:
            metric["attended_visits"] += 1

    tracked_coverage = (
        ServicePurchase.objects.filter(
            site_id=site_id,
            pricing_option__track_retention=True,
            sale_date__lte=end,
        )
        .filter(Q(expiration_date__gte=start) | Q(expiration_date__isnull=True))
        .iterator()
    )
    for purchase in tracked_coverage:
        active_start = purchase.activation_date or purchase.sale_date
        active_end = purchase.expiration_date or end
        if not active_start:
            continue
        overlap_start = max(active_start, start)
        overlap_end = min(active_end, end)
        if overlap_start > overlap_end:
            continue
        metric = metrics[(purchase.client_id, purchase.studio_id)]
        metric["active_membership_dates"].update(date_strings(overlap_start, overlap_end))

    rows = []
    for (client_id, studio_id), metric in metrics.items():
        active_membership_dates = sorted(metric["active_membership_dates"])
        rows.append(
            ClientStudioWeeklyMetric(
                site_id=site_id,
                studio_id=studio_id,
                client_id=client_id,
                week_start=start,
                total_bookings=metric["total_bookings"],
                attended_visits=metric["attended_visits"],
                no_shows=metric["no_shows"],
                late_cancels=metric["late_cancels"],
                attendance_revenue=metric["attendance_revenue"],
                active_membership_days=len(active_membership_dates),
                active_membership_dates=active_membership_dates,
                had_active_membership=bool(active_membership_dates),
            )
        )

    with transaction.atomic():
        ClientStudioWeeklyMetric.objects.filter(
            site_id=site_id,
            week_start=start,
        ).delete()
        ClientStudioWeeklyMetric.objects.bulk_create(rows)
    return len(rows)


def aggregate_client_weekly_metrics(rows):
    totals = {
        "total_bookings": 0,
        "attended_visits": 0,
        "no_shows": 0,
        "late_cancels": 0,
        "attendance_revenue": ZERO,
    }
    active_week_starts = set()
    active_membership_dates = set()

    for row in rows:
        for field in (
            "total_bookings",
            "attended_visits",
            "no_shows",
            "late_cancels",
        ):
            totals[field] += getattr(row, field)
        totals["attendance_revenue"] += row.attendance_revenue or ZERO
        if row.attended_visits > 0:
            active_week_starts.add(row.week_start.isoformat())
        active_membership_dates.update(row.active_membership_dates)

    totals["active_weeks"] = len(active_week_starts)
    totals["active_week_starts"] = sorted(active_week_starts)
    totals["active_membership_days"] = len(active_membership_dates)
    totals["active_membership_dates"] = sorted(active_membership_dates)
    totals["had_active_membership"] = bool(active_membership_dates)
    return totals
