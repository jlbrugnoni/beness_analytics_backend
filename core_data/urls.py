from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"sites", views.SiteViewSet, basename="site")
router.register(r"studios", views.StudioViewSet, basename="studio")
router.register(r"clients", views.ClientViewSet, basename="client")
router.register(r"staff-members", views.StaffMemberViewSet, basename="staff-member")
router.register(r"service-categories", views.ServiceCategoryViewSet, basename="service-category")
router.register(r"pricing-options", views.PricingOptionViewSet, basename="pricing-option")
router.register(r"payment-methods", views.PaymentMethodViewSet, basename="payment-method")
router.register(r"report-imports", views.ReportImportViewSet, basename="report-import")
router.register(r"attendance-visits", views.AttendanceVisitViewSet, basename="attendance-visit")
router.register(r"sale-lines", views.SaleLineViewSet, basename="sale-line")
router.register(r"service-purchases", views.ServicePurchaseViewSet, basename="service-purchase")
router.register(r"attendance-raw-rows", views.AttendanceRawRowViewSet, basename="attendance-raw-row")
router.register(r"sale-raw-rows", views.SaleRawRowViewSet, basename="sale-raw-row")
router.register(r"service-purchase-raw-rows", views.ServicePurchaseRawRowViewSet, basename="service-purchase-raw-row")
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
