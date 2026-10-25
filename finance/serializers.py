from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from core_data.models import Studio
from .models import Account, Category, Company, SourceMapping, Terminal, validate_account_studios


class ConfigurationSerializer(serializers.ModelSerializer):
    expected_revision = serializers.IntegerField(write_only=True, required=False, min_value=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Model validation covers cross-field integrity beyond DRF's individual fields.
        candidate = self.Meta.model()
        if self.instance:
            for field in self.Meta.model._meta.concrete_fields:
                setattr(candidate, field.attname, getattr(self.instance, field.attname))
        for key, value in attrs.items():
            if key not in {"expected_revision", "expected_parent_revision", "studios"}:
                setattr(candidate, key, value)
        if isinstance(candidate, Account) and candidate.company_id:
            candidate.company = Company.objects.select_for_update().get(pk=candidate.company_id)
        if isinstance(candidate, (Category, SourceMapping)) and candidate.company_id:
            candidate.company = Company.objects.select_for_update().get(pk=candidate.company_id)
        # Serialize terminal changes with participating-studio/account edits.
        if isinstance(candidate, Terminal) and candidate.account_id:
            candidate.account = Account.objects.select_for_update().get(pk=candidate.account_id)
        try:
            candidate.full_clean(exclude=["created_at", "updated_at"], validate_unique=False, validate_constraints=False)
            if isinstance(candidate, Account):
                studios = attrs.get("studios", self.instance.studios.all() if self.instance else [])
                validate_account_studios(candidate, studios)
        except DjangoValidationError as error:
            raise serializers.ValidationError(getattr(error, "message_dict", {"non_field_errors": error.messages}))
        return attrs


class CompanySerializer(ConfigurationSerializer):
    country_code = serializers.CharField(source="site.country_code", read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "site", "country_code", "default_currency", "active", "revision", "expected_revision", "category_catalog_version"]
        read_only_fields = ["revision", "category_catalog_version"]


class AccountSerializer(ConfigurationSerializer):
    class Meta:
        model = Account
        fields = ["id", "company", "name", "kind", "currency", "bank_name", "studios", "active",
                  "statement_imports_expected", "opening_balance", "opening_balance_date", "revision", "expected_revision"]
        read_only_fields = ["revision"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and self.instance.terminals.exists() and attrs.get("kind", self.instance.kind) != "bank":
            raise serializers.ValidationError({"kind": "An account with terminal mappings must remain a bank account."})
        return attrs


class TerminalSerializer(ConfigurationSerializer):
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = Terminal
        fields = ["id", "account", "account_name", "identifier", "studio", "studio_name", "channel", "active",
                  "revision", "expected_revision"]
        read_only_fields = ["revision"]


class CategorySerializer(ConfigurationSerializer):
    effective_sensitive = serializers.BooleanField(read_only=True)
    effective_active = serializers.BooleanField(read_only=True)
    effective_treatment = serializers.CharField(read_only=True)
    effective_allocation = serializers.CharField(read_only=True)
    parent_revision = serializers.IntegerField(source="parent.revision", read_only=True, allow_null=True)
    expected_parent_revision = serializers.IntegerField(write_only=True, required=False, min_value=1)
    can_edit = serializers.SerializerMethodField()
    can_add_child = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "company", "parent", "name", "catalog_code", "default_treatment", "default_allocation",
                  "sensitive", "active", "effective_sensitive", "effective_active", "effective_treatment",
                  "effective_allocation", "revision", "expected_revision", "parent_revision",
                  "expected_parent_revision", "can_edit", "can_add_child"]
        read_only_fields = ["revision", "catalog_code"]

    def get_can_edit(self, obj):
        from .access import can_manage_category
        request = self.context.get("request")
        return bool(request and can_manage_category(request.user, obj))

    def get_can_add_child(self, obj):
        from .access import can_use_finance, configuration_sites
        request = self.context.get("request")
        return bool(request and not obj.parent_id and obj.effective_active and obj.company.active
                    and configuration_sites(request.user).filter(pk=obj.company.site_id).exists()
                    and (not obj.effective_sensitive or can_use_finance(request.user, "can_view_sensitive_finance")))

    def validate(self, attrs):
        from .configuration import ConfigurationConflict
        company = attrs.get("company", getattr(self.instance, "company", None))
        if company:
            attrs["company"] = Company.objects.select_for_update().get(pk=company.pk)
        parent = attrs.get("parent", self.instance.parent if self.instance else None)
        if parent:
            parent = Category.objects.select_for_update().get(pk=parent.pk)
            if attrs.get("expected_parent_revision") != parent.revision:
                raise ConfigurationConflict("The parent category changed. Reload before saving.")
            if "parent" in attrs:
                attrs["parent"] = parent
            if not self.instance and not parent.effective_active:
                raise serializers.ValidationError({"parent": "Activate the parent before adding subcategories."})
        attrs.pop("expected_parent_revision", None)
        return super().validate(attrs)


class SourceMappingSerializer(ConfigurationSerializer):
    studio_name = serializers.CharField(source="studio.name", read_only=True, allow_null=True)

    class Meta:
        model = SourceMapping
        fields = ["id", "company", "source_field", "source_value", "behavior", "studio", "studio_name", "channel",
                  "requires_review", "active", "revision", "expected_revision"]
        read_only_fields = ["revision"]

    def validate(self, attrs):
        # Reject reassignment before acquiring another company's lock.
        if self.instance and any(key in attrs and attrs[key] != getattr(self.instance, key)
                                 for key in ("company", "source_field", "source_value")):
            raise serializers.ValidationError("Company and source identity cannot change. Add a new mapping instead.")
        company = attrs.get("company", self.instance.company if self.instance else None)
        if company:
            attrs["company"] = Company.objects.select_for_update().get(pk=company.pk)
        return super().validate(attrs)


class MappingPreviewSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    source = serializers.ChoiceField(choices=["alegra", "mindbody", "historical"])
    cost_center = serializers.CharField(max_length=180, allow_blank=True, default="", trim_whitespace=False)
    price_list = serializers.CharField(max_length=180, allow_blank=True, default="", trim_whitespace=False)
    payment_method = serializers.CharField(max_length=180, allow_blank=True, default="", trim_whitespace=False)
    studio_label = serializers.CharField(max_length=180, allow_blank=True, default="", trim_whitespace=False)
    manual_studio = serializers.PrimaryKeyRelatedField(queryset=Studio.objects.all(), allow_null=True, required=False)
    manual_channel = serializers.ChoiceField(choices=SourceMapping.CHANNELS, allow_null=True, required=False)

    def validate(self, attrs):
        if attrs["source"] != "alegra" and (attrs["cost_center"] or attrs["price_list"]):
            raise serializers.ValidationError("Cost center and price list apply to Alegra only.")
        if attrs["source"] == "alegra" and attrs["studio_label"]:
            raise serializers.ValidationError("Use the cost center for Alegra studio evidence.")
        if "manual_studio" in attrs and attrs["manual_studio"] and attrs["manual_studio"].site_id != attrs["company"].site_id:
            raise serializers.ValidationError({"manual_studio": "Use a studio from this company's site."})
        return attrs
