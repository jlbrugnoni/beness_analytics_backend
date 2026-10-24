from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import Account, Company, Terminal, validate_account_studios


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
            if key not in {"expected_revision", "studios"}:
                setattr(candidate, key, value)
        if isinstance(candidate, Account) and candidate.company_id:
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
        fields = ["id", "name", "site", "country_code", "default_currency", "active", "revision", "expected_revision"]
        read_only_fields = ["revision"]


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
