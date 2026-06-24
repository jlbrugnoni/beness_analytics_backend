from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Max, Min

from analytics.client_metrics import (
    aggregate_client_monthly_metrics,
    aggregate_client_weekly_metrics,
    week_start,
)
from analytics.models import (
    ClientStudioMonthlyMetric,
    ClientStudioWeeklyMetric,
    MembershipMonthStatus,
)
from core_data.access import scoped_queryset_for_user
from core_data.models import AttendanceVisit


CHURN_RESEARCH_FIELDS = [
    "site_id",
    "site",
    "studio_id",
    "studio",
    "client_id",
    "client",
    "mindbody_id",
    "observation_month",
    "status",
    "next_month_status",
    "target_churned_next_month",
    "target_renewed_next_month",
    "membership_days",
    "previous_membership_days",
    "membership_value",
    "membership_sale_date",
    "membership_activation_date",
    "membership_expiration_date",
    "days_to_expiration_from_month_end",
    "days_since_last_visit_to_month_end",
    "days_last_visit_to_expiration",
    "current_month_bookings",
    "current_month_attended_visits",
    "current_month_active_weeks",
    "current_month_no_shows",
    "current_month_late_cancels",
    "current_month_attendance_rate",
    "current_month_no_show_rate",
    "current_month_late_cancel_rate",
    "current_month_tracked_purchases",
    "current_month_service_purchases",
    "current_month_spending",
    "last_4_weeks_bookings",
    "last_4_weeks_attended_visits",
    "last_4_weeks_active_weeks",
    "last_4_weeks_attendance_rate",
    "last_4_weeks_no_shows",
    "last_4_weeks_late_cancels",
    "previous_4_weeks_attended_visits",
    "attendance_change_last4_vs_previous4",
    "last_8_weeks_bookings",
    "last_8_weeks_attended_visits",
    "last_8_weeks_active_weeks",
    "last_8_weeks_attendance_rate",
    "last_12_weeks_attended_visits",
    "last_12_weeks_active_weeks",
    "last_3_months_attended_visits",
    "last_3_months_active_weeks",
    "last_3_months_tracked_purchases",
    "last_3_months_spending",
    "lifetime_to_month_attended_visits",
    "lifetime_to_month_active_weeks",
    "lifetime_to_month_tracked_purchases",
    "lifetime_to_month_membership_months",
    "lifetime_to_month_spending",
    "client_since",
    "first_visit_date",
    "last_visit_date",
    "latest_imported_visit_date",
]


ACTIVE_STATUSES = {
    MembershipMonthStatus.STATUS_NEW,
    MembershipMonthStatus.STATUS_RETAINED,
    MembershipMonthStatus.STATUS_REACTIVATED,
}


def parse_month(value):
    if not value:
        return None
    try:
        year, month = [int(part) for part in str(value).split("-")[:2]]
        return date(year, month, 1)
    except (TypeError, ValueError):
        return None


def month_end(value):
    return value.replace(day=monthrange(value.year, value.month)[1])


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def decimal_value(value):
    if value is None:
        return None
    return float(value)


def percentage(numerator, denominator):
    if not denominator:
        return None
    return round((numerator / denominator) * 100, 2)


def date_value(value):
    return value.isoformat() if value else None


def int_or_none(value):
    if value is None:
        return None
    return int(value)


def latest_visit_date():
    return AttendanceVisit.objects.aggregate(latest=Max("visit_date"))["latest"]


def window_months(end_month, count):
    start_month = add_months(end_month, -(count - 1))
    return start_month, end_month


def weekly_window_metrics(weekly_by_client, client_id, end_date, weeks):
    end_week = week_start(end_date)
    start_week = end_week - timedelta(days=7 * (weeks - 1))
    return aggregate_client_weekly_metrics([
        row
        for row in weekly_by_client.get(client_id, [])
        if start_week <= row.week_start <= end_week
    ])


def monthly_window_metrics(monthly_by_client, client_id, start_month, end_month):
    return aggregate_client_monthly_metrics([
        row
        for row in monthly_by_client.get(client_id, [])
        if start_month <= row.month <= end_month
    ])


def month_status_lookup(statuses):
    return {
        (status.client_id, status.month): status
        for status in statuses
    }


def row_target(next_status):
    if next_status is None:
        return None, None
    if next_status.status == MembershipMonthStatus.STATUS_NOT_RENEWED:
        return True, False
    if next_status.status in ACTIVE_STATUSES or next_status.current_month_member:
        return False, True
    return None, None


def build_churn_research_dataset(
    request,
    site_id=None,
    studio_id=None,
    month_from=None,
    month_to=None,
    include_unknown=False,
    include_money=True,
):
    statuses = (
        MembershipMonthStatus.objects.select_related(
            "site",
            "studio",
            "client",
            "source_purchase",
            "source_purchase__pricing_option",
        )
        .filter(status__in=ACTIVE_STATUSES)
        .order_by("month", "client__name")
    )
    statuses = scoped_queryset_for_user(
        statuses,
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    if site_id:
        statuses = statuses.filter(site_id=site_id)
    if studio_id:
        statuses = statuses.filter(studio_id=studio_id)

    bounds = statuses.aggregate(min_month=Min("month"), max_month=Max("month"))
    start_month = month_from or bounds["min_month"]
    end_month = month_to or bounds["max_month"]
    if not start_month or not end_month:
        return []

    statuses = list(statuses.filter(month__range=(start_month, end_month)))
    if not statuses:
        return []

    status_client_ids = {status.client_id for status in statuses}
    status_site_ids = {status.site_id for status in statuses}
    status_lookup_qs = MembershipMonthStatus.objects.filter(
        client_id__in=status_client_ids,
        month__lte=add_months(end_month, 1),
    )
    status_lookup_qs = scoped_queryset_for_user(
        status_lookup_qs,
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    status_by_client_month = month_status_lookup(status_lookup_qs)

    monthly_metrics = ClientStudioMonthlyMetric.objects.filter(
        site_id__in=status_site_ids,
        client_id__in=status_client_ids,
        month__lte=end_month,
    )
    weekly_metrics = ClientStudioWeeklyMetric.objects.filter(
        site_id__in=status_site_ids,
        client_id__in=status_client_ids,
        week_start__range=(week_start(add_months(start_month, -3)), week_start(month_end(end_month))),
    )
    monthly_metrics = scoped_queryset_for_user(
        monthly_metrics,
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    weekly_metrics = scoped_queryset_for_user(
        weekly_metrics,
        request.user,
        site_field="site_id",
        studio_field="studio_id",
        include_null_studio=True,
    )
    if studio_id:
        monthly_metrics = monthly_metrics.filter(studio_id=studio_id)
        weekly_metrics = weekly_metrics.filter(studio_id=studio_id)

    monthly_by_client = defaultdict(list)
    for metric in monthly_metrics:
        monthly_by_client[metric.client_id].append(metric)

    weekly_by_client = defaultdict(list)
    for metric in weekly_metrics:
        weekly_by_client[metric.client_id].append(metric)

    latest_imported_visit = latest_visit_date()
    rows = []
    for status in statuses:
        observation_end = month_end(status.month)
        next_status = status_by_client_month.get((status.client_id, add_months(status.month, 1)))
        churned_next_month, renewed_next_month = row_target(next_status)
        if churned_next_month is None and not include_unknown:
            continue

        current_month = monthly_window_metrics(
            monthly_by_client,
            status.client_id,
            status.month,
            status.month,
        )
        last_3_start, last_3_end = window_months(status.month, 3)
        last_3_months = monthly_window_metrics(
            monthly_by_client,
            status.client_id,
            last_3_start,
            last_3_end,
        )
        lifetime_to_month = monthly_window_metrics(
            monthly_by_client,
            status.client_id,
            date(1900, 1, 1),
            status.month,
        )
        last_4_weeks = weekly_window_metrics(
            weekly_by_client,
            status.client_id,
            observation_end,
            4,
        )
        previous_4_end = week_start(observation_end) - timedelta(days=7)
        previous_4_weeks = aggregate_client_weekly_metrics([
            row
            for row in weekly_by_client.get(status.client_id, [])
            if previous_4_end - timedelta(days=21) <= row.week_start <= previous_4_end
        ])
        last_8_weeks = weekly_window_metrics(
            weekly_by_client,
            status.client_id,
            observation_end,
            8,
        )
        last_12_weeks = weekly_window_metrics(
            weekly_by_client,
            status.client_id,
            observation_end,
            12,
        )

        source_purchase = status.source_purchase
        expiration_date = source_purchase.expiration_date if source_purchase else None
        last_visit = lifetime_to_month["last_visit_date"]
        days_to_expiration = (
            (expiration_date - observation_end).days
            if expiration_date
            else None
        )
        days_since_last_visit = (
            (observation_end - last_visit).days
            if last_visit
            else None
        )
        days_last_visit_to_expiration = (
            (expiration_date - last_visit).days
            if expiration_date and last_visit
            else None
        )

        spending_current = current_month["general_sales_spending"] if include_money else None
        spending_last_3 = last_3_months["general_sales_spending"] if include_money else None
        spending_lifetime = lifetime_to_month["general_sales_spending"] if include_money else None

        rows.append({
            "site_id": status.site_id,
            "site": status.site.name,
            "studio_id": status.studio_id,
            "studio": status.studio.name if status.studio else None,
            "client_id": status.client_id,
            "client": status.client.name,
            "mindbody_id": status.client.mindbody_id,
            "observation_month": status.month.isoformat(),
            "status": status.status,
            "next_month_status": next_status.status if next_status else None,
            "target_churned_next_month": churned_next_month,
            "target_renewed_next_month": renewed_next_month,
            "membership_days": status.membership_days,
            "previous_membership_days": status.previous_membership_days,
            "membership_value": decimal_value(status.membership_value) if include_money else None,
            "membership_sale_date": date_value(source_purchase.sale_date if source_purchase else None),
            "membership_activation_date": date_value(source_purchase.activation_date if source_purchase else None),
            "membership_expiration_date": date_value(expiration_date),
            "days_to_expiration_from_month_end": int_or_none(days_to_expiration),
            "days_since_last_visit_to_month_end": int_or_none(days_since_last_visit),
            "days_last_visit_to_expiration": int_or_none(days_last_visit_to_expiration),
            "current_month_bookings": current_month["total_bookings"],
            "current_month_attended_visits": current_month["attended_visits"],
            "current_month_active_weeks": current_month["active_weeks"],
            "current_month_no_shows": current_month["no_shows"],
            "current_month_late_cancels": current_month["late_cancels"],
            "current_month_attendance_rate": percentage(
                current_month["attended_visits"],
                current_month["total_bookings"],
            ),
            "current_month_no_show_rate": percentage(
                current_month["no_shows"],
                current_month["total_bookings"],
            ),
            "current_month_late_cancel_rate": percentage(
                current_month["late_cancels"],
                current_month["total_bookings"],
            ),
            "current_month_tracked_purchases": current_month["tracked_purchase_count"],
            "current_month_service_purchases": current_month["service_purchase_count"],
            "current_month_spending": decimal_value(spending_current),
            "last_4_weeks_bookings": last_4_weeks["total_bookings"],
            "last_4_weeks_attended_visits": last_4_weeks["attended_visits"],
            "last_4_weeks_active_weeks": last_4_weeks["active_weeks"],
            "last_4_weeks_attendance_rate": percentage(
                last_4_weeks["attended_visits"],
                last_4_weeks["total_bookings"],
            ),
            "last_4_weeks_no_shows": last_4_weeks["no_shows"],
            "last_4_weeks_late_cancels": last_4_weeks["late_cancels"],
            "previous_4_weeks_attended_visits": previous_4_weeks["attended_visits"],
            "attendance_change_last4_vs_previous4": (
                last_4_weeks["attended_visits"] - previous_4_weeks["attended_visits"]
            ),
            "last_8_weeks_bookings": last_8_weeks["total_bookings"],
            "last_8_weeks_attended_visits": last_8_weeks["attended_visits"],
            "last_8_weeks_active_weeks": last_8_weeks["active_weeks"],
            "last_8_weeks_attendance_rate": percentage(
                last_8_weeks["attended_visits"],
                last_8_weeks["total_bookings"],
            ),
            "last_12_weeks_attended_visits": last_12_weeks["attended_visits"],
            "last_12_weeks_active_weeks": last_12_weeks["active_weeks"],
            "last_3_months_attended_visits": last_3_months["attended_visits"],
            "last_3_months_active_weeks": last_3_months["active_weeks"],
            "last_3_months_tracked_purchases": last_3_months["tracked_purchase_count"],
            "last_3_months_spending": decimal_value(spending_last_3),
            "lifetime_to_month_attended_visits": lifetime_to_month["attended_visits"],
            "lifetime_to_month_active_weeks": lifetime_to_month["active_weeks"],
            "lifetime_to_month_tracked_purchases": lifetime_to_month["tracked_purchase_count"],
            "lifetime_to_month_membership_months": sum(
                1
                for month_status in status_by_client_month.values()
                if (
                    month_status.client_id == status.client_id
                    and month_status.month <= status.month
                    and month_status.status in ACTIVE_STATUSES
                )
            ),
            "lifetime_to_month_spending": decimal_value(spending_lifetime),
            "client_since": date_value(lifetime_to_month["first_non_trial_purchase_date"]),
            "first_visit_date": date_value(lifetime_to_month["first_visit_date"]),
            "last_visit_date": date_value(last_visit),
            "latest_imported_visit_date": date_value(latest_imported_visit),
        })

    return rows
