from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"report-imports", views.ReportImportViewSet, basename="report-import")
router.register(r"login-logs", views.LoginLogViewSet, basename="login-log")


urlpatterns = [
    path("", include(router.urls)),
    path("login", views.login_view, name="login"),
    path("validate-token", views.validate_token_view, name="validate-token"),
    path("logout", views.logout_view, name="logout"),
    path("all_users/", views.all_users, name="all-users"),
    path("groups/", views.list_groups, name="list-groups"),
    path("health/", views.health_check, name="health-check"),
]
