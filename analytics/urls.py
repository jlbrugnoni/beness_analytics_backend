from django.urls import path

from . import views


urlpatterns = [
    path("summary/", views.summary_view, name="analytics-summary"),
    path("revenue/", views.revenue_view, name="analytics-revenue"),
    path("attendance/", views.attendance_view, name="analytics-attendance"),
    path("retention/", views.retention_view, name="analytics-retention"),
    path("occupation/", views.occupation_view, name="analytics-occupation"),
]

