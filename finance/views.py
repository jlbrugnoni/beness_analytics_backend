from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core_data.access import get_or_create_user_access_profile, resolve_access_payload, user_has_global_access
from core_data.models import Studio
from .access import can_view_full_account, configuration_sites, scoped_companies
from .configuration import ConfigurationViewSet
from .models import Account, Company, Terminal
from .permissions import FinancePermission
from .serializers import AccountSerializer, CompanySerializer, TerminalSerializer


def visible_accounts(user):
    companies = scoped_companies(Company.objects.all(), user)
    candidates = Account.objects.filter(company__in=companies).select_related("company").prefetch_related("studios")
    visible = [account.pk for account in candidates if can_view_full_account(user, account)]
    return Account.objects.filter(pk__in=visible).select_related("company").prefetch_related("studios")


def visible_studios(user):
    profile = get_or_create_user_access_profile(user)
    if user_has_global_access(user):
        return Studio.objects.all()
    if profile.allowed_studios.exists():
        return profile.allowed_studios.all()
    return Studio.objects.filter(site__in=profile.allowed_sites.all())


class FinanceOverview(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]

    def get(self, request):
        companies = scoped_companies(Company.objects.select_related("site"), request.user)
        return Response({"stage": "configuration", "companies": CompanySerializer(companies, many=True).data,
                         "capabilities": resolve_access_payload(request.user)["capabilities"]})


class ConfigurationOptions(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]
    required_finance_capability = "can_manage_finance_settings"

    def get(self, request):
        return Response({
            "sites": list(configuration_sites(request.user).order_by("name").values("id", "name", "country_code")),
            "studios": list(visible_studios(request.user).order_by("name").values("id", "name", "site_id")),
        })


class CompanyViewSet(ConfigurationViewSet):
    serializer_class = CompanySerializer

    def get_queryset(self):
        return scoped_companies(Company.objects.select_related("site"), self.request.user)

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in {"POST", "PUT", "PATCH"}:
            serializer.fields["site"].queryset = configuration_sites(self.request.user)
        return serializer

    def authorize_values(self, serializer):
        site = serializer.validated_data.get("site", getattr(serializer.instance, "site", None))
        if not configuration_sites(self.request.user).filter(pk=site.pk).exists():
            raise PermissionDenied("Company configuration requires site-wide access.")


class AccountViewSet(ConfigurationViewSet):
    required_finance_capability = "can_view_finance_bank_accounts"
    serializer_class = AccountSerializer

    def get_queryset(self):
        return visible_accounts(self.request.user)

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in {"POST", "PUT", "PATCH"}:
            serializer.fields["company"].queryset = scoped_companies(Company.objects.all(), self.request.user)
            serializer.fields["studios"].child_relation.queryset = visible_studios(self.request.user)
        return serializer

    def authorize_values(self, serializer):
        company = serializer.validated_data.get("company", getattr(serializer.instance, "company", None))
        if not serializer.instance and not configuration_sites(self.request.user).filter(pk=company.site_id).exists():
            raise PermissionDenied("Creating accounts requires site-wide access.")
        if not user_has_global_access(self.request.user):
            profile = get_or_create_user_access_profile(self.request.user)
            if profile.allowed_studios.exists():
                studios = serializer.validated_data.get("studios", serializer.instance.studios.all() if serializer.instance else [])
                if not studios:
                    raise PermissionDenied("A studio-scoped manager cannot turn an account into a company-wide account.")


class TerminalViewSet(ConfigurationViewSet):
    required_finance_capability = "can_view_finance_bank_accounts"
    serializer_class = TerminalSerializer

    def get_queryset(self):
        return Terminal.objects.filter(account__in=visible_accounts(self.request.user)).select_related("account", "studio")

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in {"POST", "PUT", "PATCH"}:
            serializer.fields["account"].queryset = visible_accounts(self.request.user)
            serializer.fields["studio"].queryset = visible_studios(self.request.user)
        return serializer

    def authorize_values(self, serializer):
        account = serializer.validated_data.get("account", getattr(serializer.instance, "account", None))
        if not account.active or not account.company.active:
            raise PermissionDenied("Activate the company and account before editing terminal mappings.")
