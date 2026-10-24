from rest_framework import serializers
from .models import Account, Company


class CompanySerializer(serializers.ModelSerializer):
    country_code = serializers.CharField(source="site.country_code", read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "site", "country_code", "default_currency", "active"]


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "company", "name", "kind", "currency", "bank_name", "studios", "active"]
