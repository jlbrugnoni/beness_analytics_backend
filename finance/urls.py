from django.urls import include, path
from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework.permissions import IsAuthenticated
from .permissions import FinancePermission
from .views import AccountViewSet, CategoryViewSet, CompanyViewSet, ConfigurationOptions, FinanceOverview, MappingPreview, SourceMappingViewSet, TerminalViewSet

class FinanceAPIRoot(APIRootView):
    permission_classes = [IsAuthenticated, FinancePermission]


router = DefaultRouter()
router.APIRootView = FinanceAPIRoot
router.register("companies", CompanyViewSet, basename="finance-company")
router.register("accounts", AccountViewSet, basename="finance-account")
router.register("terminals", TerminalViewSet, basename="finance-terminal")
router.register("categories", CategoryViewSet, basename="finance-category")
router.register("source-mappings", SourceMappingViewSet, basename="finance-source-mapping")
urlpatterns = [path("overview/", FinanceOverview.as_view(), name="finance-overview"),
               path("configuration-options/", ConfigurationOptions.as_view(), name="finance-configuration-options"),
               path("mapping-preview/", MappingPreview.as_view(), name="finance-mapping-preview"),
               path("", include(router.urls))]
