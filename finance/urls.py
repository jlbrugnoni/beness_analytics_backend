from django.urls import include, path
from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework.permissions import IsAuthenticated
from .permissions import FinancePermission
from .views import AccountViewSet, CategoryViewSet, CompanyViewSet, ConfigurationOptions, FinanceOverview, MappingPreview, SourceMappingViewSet, TerminalViewSet

from .policy_views import FeePolicyViewSet, SettlementPolicyViewSet, TaxProfileViewSet, PolicyPreview, PolicySetup

from .sales_import_views import SalesImportViewSet
from .posting_views import BankPostingImportViewSet, BankMovementViewSet

class FinanceAPIRoot(APIRootView):
    permission_classes = [IsAuthenticated, FinancePermission]


router = DefaultRouter()
router.APIRootView = FinanceAPIRoot
router.register("companies", CompanyViewSet, basename="finance-company")
router.register("accounts", AccountViewSet, basename="finance-account")
router.register("terminals", TerminalViewSet, basename="finance-terminal")
router.register("categories", CategoryViewSet, basename="finance-category")
router.register("source-mappings", SourceMappingViewSet, basename="finance-source-mapping")
router.register("fee-policies", FeePolicyViewSet, basename="finance-fee-policy")
router.register("settlement-policies", SettlementPolicyViewSet, basename="finance-settlement-policy")
router.register("tax-profiles", TaxProfileViewSet, basename="finance-tax-profile")
router.register("sales-imports", SalesImportViewSet, basename="finance-sales-import")
router.register("bank-imports", BankPostingImportViewSet, basename="finance-bank-import")
router.register("bank-movements", BankMovementViewSet, basename="finance-bank-movement")
urlpatterns = [path("policy-preview/", PolicyPreview.as_view(), name="finance-policy-preview"),
               path("policy-setup/", PolicySetup.as_view(), name="finance-policy-setup"),path("overview/", FinanceOverview.as_view(), name="finance-overview"),
               path("configuration-options/", ConfigurationOptions.as_view(), name="finance-configuration-options"),
               path("mapping-preview/", MappingPreview.as_view(), name="finance-mapping-preview"),
               path("", include(router.urls))]
