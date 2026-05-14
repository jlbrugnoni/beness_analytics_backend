from django.urls import path

from . import views


urlpatterns = [
    path("summary/", views.summary_view, name="analytics-summary"),
    path("revenue/", views.revenue_view, name="analytics-revenue"),
    path("attendance/", views.attendance_view, name="analytics-attendance"),
    path("retention/", views.retention_view, name="analytics-retention"),
    path("retention-followup/", views.retention_followup_view, name="analytics-retention-followup"),
    path("membership-months/rebuild/", views.rebuild_membership_months_view, name="analytics-membership-months-rebuild"),
    path("class-matches/rebuild/", views.rebuild_attendance_class_matches_view, name="analytics-class-matches-rebuild"),
    path("occupation/", views.occupation_view, name="analytics-occupation"),
]
