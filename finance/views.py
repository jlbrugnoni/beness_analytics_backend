from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core_data.access import get_or_create_user_access_profile, resolve_access_payload, user_has_global_access
from core_data.models import Studio
from .access import can_manage_category, can_view_full_account, can_view_sensitive_detail, configuration_sites, scoped_companies
from .configuration import ConfigurationConflict, ConfigurationViewSet
from .models import Account, Category, Company, ConfigurationChange, Terminal
from .permissions import FinancePermission
from .serializers import AccountSerializer, CategorySerializer, CompanySerializer, TerminalSerializer


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

    @action(detail=True, methods=["post"], url_path="initialize-categories")
    def initialize_categories(self, request, pk=None):
        from .catalog import CATALOG_VERSION, create_starting_catalog
        self.check_write_access()
        with transaction.atomic():
            company = self.get_write_instance()
            if not configuration_sites(request.user).filter(pk=company.site_id).exists() or not can_view_sensitive_detail(request.user):
                raise PermissionDenied("Starting catalog setup requires company-wide settings and sensitive-detail access.")
            if company.category_catalog_version:
                return Response({"company": self.get_serializer(company).data, "created": 0})
            if request.data.get("expected_revision") != company.revision:
                raise ConfigurationConflict()
            if company.categories.exists():
                raise ConfigurationConflict("The starting catalog can only be added to a company with no categories. Existing categories were preserved.")
            if not company.active:
                raise serializers.ValidationError({"company": "Activate the company before initializing categories."})
            before = dict(self.get_serializer(company).data)
            created = create_starting_catalog(company, request.user)
            company.category_catalog_version = CATALOG_VERSION
            company.revision += 1
            company.save(update_fields=["category_catalog_version", "revision", "updated_at"])
            after = dict(self.get_serializer(company).data)
            ConfigurationChange.objects.create(actor=request.user, target_type="company", target_id=company.pk,
                target_label=company.name, before=before, after=after)
            return Response({"company": after, "created": created})


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


class CategoryViewSet(ConfigurationViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        companies = scoped_companies(Company.objects.all(), self.request.user)
        queryset = Category.objects.filter(company__in=companies).select_related("company", "parent")
        company_id = self.request.query_params.get("company")
        if company_id:
            if not company_id.isdecimal():
                raise serializers.ValidationError({"company": "Use a company ID."})
            queryset = queryset.filter(company_id=company_id)
        return queryset

    def get_write_instance(self):
        obj = self.get_object()
        # Consistent company -> category locking also serializes parent/child writes.
        Company.objects.select_for_update().get(pk=obj.company_id)
        return Category.objects.select_for_update().get(pk=obj.pk)

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in {"POST", "PUT", "PATCH"}:
            serializer.fields["company"].queryset = scoped_companies(Company.objects.all(), self.request.user)
            serializer.fields["parent"].queryset = self.get_queryset().filter(parent__isnull=True)
        return serializer

    def authorize_values(self, serializer):
        values, previous = serializer.validated_data, serializer.instance
        company = values.get("company", previous.company if previous else None)
        if not configuration_sites(self.request.user).filter(pk=company.site_id).exists():
            raise PermissionDenied("Category configuration requires site-wide access.")
        parent = values.get("parent", previous.parent if previous else None)
        sensitive_change = values.get("sensitive", False) != (previous.sensitive if previous else False)
        protected = (previous and not can_manage_category(self.request.user, previous)) or (parent and parent.effective_sensitive)
        if (sensitive_change or protected) and not can_view_sensitive_detail(self.request.user):
            raise PermissionDenied("Sensitive-detail access is required to edit this category or its sensitivity.")
        if not previous and not company.active:
            raise serializers.ValidationError({"company": "Activate the company before adding categories."})
