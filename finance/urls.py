from django.urls import include, path
from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework.permissions import IsAuthenticated
from .permissions import FinancePermission
from .views import AccountViewSet, CompanyViewSet, FinanceOverview

class FinanceAPIRoot(APIRootView):
    permission_classes = [IsAuthenticated, FinancePermission]


router = DefaultRouter()
router.APIRootView = FinanceAPIRoot
router.register("companies", CompanyViewSet, basename="finance-company")
router.register("accounts", AccountViewSet, basename="finance-account")
urlpatterns = [path("overview/", FinanceOverview.as_view(), name="finance-overview"), path("", include(router.urls))]
