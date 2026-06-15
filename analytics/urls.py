from django.urls import path

from . import views


urlpatterns = [
    path("summary/", views.summary_view, name="analytics-summary"),
    path("clients/", views.client_directory_view, name="analytics-client-directory"),
    path("clients/<int:client_id>/", views.client_profile_view, name="analytics-client-profile"),
    path("clients/<int:client_id>/history/", views.client_history_view, name="analytics-client-history"),
    path("revenue/", views.revenue_view, name="analytics-revenue"),
    path("attendance/", views.attendance_view, name="analytics-attendance"),
    path("retention/", views.retention_view, name="analytics-retention"),
    path("trial-conversions/", views.trial_conversion_view, name="analytics-trial-conversions"),
    path("dashboard/monthly/", views.dashboard_monthly_view, name="analytics-dashboard-monthly"),
    path("dashboard/monthly/trends/", views.dashboard_monthly_trends_view, name="analytics-dashboard-monthly-trends"),
    path("dashboard/monthly/retention-tables/", views.dashboard_monthly_retention_tables_view, name="analytics-dashboard-monthly-retention-tables"),
    path("dashboard/weekly/", views.dashboard_weekly_view, name="analytics-dashboard-weekly"),
    path("dashboard/weekly/trends/", views.dashboard_weekly_trends_view, name="analytics-dashboard-weekly-trends"),
    path("dashboard/weekly/occupancy-hour-matrix/", views.dashboard_weekly_occupancy_hour_matrix_view, name="analytics-dashboard-weekly-occupancy-hour-matrix"),
    path("retention-followup/", views.retention_followup_view, name="analytics-retention-followup"),
    path(
        "retention-followup/<int:snapshot_id>/activity/",
        views.retention_followup_activity_view,
        name="analytics-retention-followup-activity",
    ),
    path(
        "retention-followup/<int:snapshot_id>/purchase-history/",
        views.retention_purchase_history_view,
        name="analytics-retention-purchase-history",
    ),
    path(
        "retention-clients/<int:client_id>/purchase-history/",
        views.retention_client_purchase_history_view,
        name="analytics-retention-client-purchase-history",
    ),
    path("membership-months/rebuild/", views.rebuild_membership_months_view, name="analytics-membership-months-rebuild"),
    path("client-metrics/rebuild/", views.rebuild_client_metrics_view, name="analytics-client-metrics-rebuild"),
    path("class-matches/rebuild/", views.rebuild_attendance_class_matches_view, name="analytics-class-matches-rebuild"),
    path("class-matches/unresolved/", views.unresolved_attendance_matches_view, name="analytics-class-matches-unresolved"),
    path("occupation/", views.occupation_view, name="analytics-occupation"),
]
