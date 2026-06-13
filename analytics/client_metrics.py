from calendar import monthrange
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from analytics.models import (
    ClientStudioMonthlyMetric,
    ClientStudioWeeklyMetric,
    MembershipMonthStatus,
)
from core_data.models import (
    AttendanceVisit,
    PricingOption,
    ReportImport,
    SaleLine,
    ServicePurchase,
    ServicePurchaseVersion,
)


ZERO = Decimal("0.00")


def month_start(value):
    return value.replace(day=1)


def month_end(value):
    return value.replace(day=monthrange(value.year, value.month)[1])


def week_start(value):
    return value - timedelta(days=value.weekday())


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def months_between(start, end):
    current = month_start(start)
    final = month_start(end)
    values = []
    while current <= final:
        values.append(current)
        current = add_months(current, 1)
    return values


def weeks_between(start, end):
    current = week_start(start)
    final = week_start(end)
    values = []
    while current <= final:
        values.append(current)
        current += timedelta(days=7)
    return values


def metric_date(value):
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    return parse_date(str(value))


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
    membership_status_month = None

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
        if (
            row.membership_status
            and (membership_status_month is None or row.month > membership_status_month)
        ):
            totals["membership_status"] = row.membership_status
            membership_status_month = row.month

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


def client_metric_periods_for_import(report_import):
    months = set()
    weeks = set()

    if report_import.report_type == "attendance_with_revenue":
        dates = AttendanceVisit.objects.filter(
            last_seen_import=report_import,
        ).values_list("visit_date", flat=True)
        for value in dates:
            months.add(month_start(value))
            weeks.add(week_start(value))

    elif report_import.report_type == "sales":
        for value in SaleLine.objects.filter(
            last_seen_import=report_import,
        ).values_list("sale_date", flat=True):
            months.add(month_start(value))

    elif report_import.report_type == "sales_by_service":
        purchases = ServicePurchase.objects.filter(
            last_seen_import=report_import,
        ).select_related("pricing_option")
        for purchase in purchases:
            months.add(month_start(purchase.sale_date))
            if purchase.pricing_option.track_retention:
                start = purchase.activation_date or purchase.sale_date
                end = purchase.expiration_date or start
                months.update(months_between(start, end))
                weeks.update(weeks_between(start, end))

        current_version_ids = set(
            report_import.service_purchase_versions.values_list("id", flat=True)
        )
        affected_purchase_ids = set(
            report_import.service_purchase_versions.values_list(
                "service_purchase_id",
                flat=True,
            )
        )
        previous_snapshots = []
        previous_snapshot_by_purchase = {}
        version_history = (
            ServicePurchaseVersion.objects.filter(
                service_purchase_id__in=affected_purchase_ids,
            )
            .order_by("service_purchase_id", "created_at", "id")
            .values("id", "service_purchase_id", "snapshot")
        )
        for version in version_history:
            purchase_id = version["service_purchase_id"]
            if version["id"] in current_version_ids:
                previous_snapshot = previous_snapshot_by_purchase.get(purchase_id)
                if previous_snapshot:
                    previous_snapshots.append(previous_snapshot)
            previous_snapshot_by_purchase[purchase_id] = version["snapshot"]

        option_ids = {
            snapshot["pricing_option_id"]
            for snapshot in previous_snapshots
            if snapshot.get("pricing_option_id")
        }

        tracked_option_ids = set(
            PricingOption.objects.filter(
                id__in=option_ids,
                track_retention=True,
            ).values_list("id", flat=True)
        )
        for snapshot in previous_snapshots:
            sale_date = metric_date(snapshot.get("sale_date"))
            if sale_date:
                months.add(month_start(sale_date))
            if snapshot.get("pricing_option_id") not in tracked_option_ids:
                continue
            start = metric_date(snapshot.get("activation_date")) or sale_date
            end = metric_date(snapshot.get("expiration_date")) or start
            if start and end:
                months.update(months_between(start, end))
                weeks.update(weeks_between(start, end))

    return {
        "months": sorted(months),
        "weeks": sorted(weeks),
    }


def rebuild_client_metrics_for_periods(site_id, months=None, weeks=None):
    monthly = [
        {
            "month": target_month.isoformat(),
            "rows": rebuild_client_studio_monthly_metrics(site_id, target_month),
        }
        for target_month in sorted(set(months or []))
    ]
    weekly = [
        {
            "week_start": target_week.isoformat(),
            "rows": rebuild_client_studio_weekly_metrics(site_id, target_week),
        }
        for target_week in sorted(set(weeks or []))
    ]
    return {
        "monthly": monthly,
        "weekly": weekly,
        "total_monthly_rows": sum(row["rows"] for row in monthly),
        "total_weekly_rows": sum(row["rows"] for row in weekly),
    }


def rebuild_client_metrics_after_import(site_id, report_import_id, exclude_months=None):
    report_import = ReportImport.objects.get(id=report_import_id)
    periods = client_metric_periods_for_import(report_import)
    excluded = set(exclude_months or [])
    months = [value for value in periods["months"] if value not in excluded]
    result = rebuild_client_metrics_for_periods(
        site_id,
        months=months,
        weeks=periods["weeks"],
    )
    result["skipped"] = not months and not periods["weeks"]
    return result


def rebuild_client_metrics_for_range(site_id, start, end):
    return rebuild_client_metrics_for_periods(
        site_id,
        months=months_between(start, end),
        weeks=weeks_between(start, end),
    )
