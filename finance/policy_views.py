from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .access import configuration_sites, scoped_companies
from .configuration import ConfigurationConflict, ConfigurationViewSet
from .models import Company, ConfigurationChange, FeePolicy, SettlementPolicy, TaxProfile
from .permissions import FinancePermission
from .serializers import CompanySerializer, FeePolicySerializer, SettlementPolicySerializer, TaxProfileSerializer, PolicyPreviewSerializer


def require_company_settings(user, company):
    if not configuration_sites(user).filter(pk=company.site_id).exists():
        raise PermissionDenied('Policy changes and tests require company-wide settings access.')


class PolicyViewSet(ConfigurationViewSet):
    def get_queryset(self):
        queryset = self.serializer_class.Meta.model.objects.filter(
            company__in=scoped_companies(Company.objects.all(), self.request.user)).select_related('company')
        company_id = self.request.query_params.get('company')
        if company_id:
            if not company_id.isdecimal():
                raise serializers.ValidationError({'company': 'Use a company ID.'})
            queryset = queryset.filter(company_id=company_id)
        return queryset

    def get_write_instance(self):
        obj = self.get_object()
        Company.objects.select_for_update().get(pk=obj.company_id)
        return type(obj).objects.select_for_update().get(pk=obj.pk)

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in {'POST', 'PUT', 'PATCH'}:
            serializer.fields['company'].queryset = scoped_companies(Company.objects.all(), self.request.user)
        return serializer

    def authorize_values(self, serializer):
        company = serializer.validated_data.get('company', serializer.instance.company if serializer.instance else None)
        require_company_settings(self.request.user, company)
        if not serializer.instance and not company.active:
            raise serializers.ValidationError({'company': 'Activate the company before adding policies.'})


class FeePolicyViewSet(PolicyViewSet):
    serializer_class = FeePolicySerializer


class SettlementPolicyViewSet(PolicyViewSet):
    serializer_class = SettlementPolicySerializer


class TaxProfileViewSet(PolicyViewSet):
    serializer_class = TaxProfileSerializer


class PolicyPreview(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]
    required_finance_capability = 'can_manage_finance_settings'

    def post(self, request):
        from .policies import preview_policies
        serializer = PolicyPreviewSerializer(data=request.data)
        serializer.fields['company'].queryset = scoped_companies(Company.objects.all(), request.user)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=data['company'].pk)
            require_company_settings(request.user, company)
            if not company.active:
                raise serializers.ValidationError('Activate the company before testing policies.')
            return Response(preview_policies(company, data['date'], data['channel'], data['amount']))


class PolicySetup(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]
    required_finance_capability = 'can_manage_finance_settings'

    def post(self, request):
        class Input(serializers.Serializer):
            company = serializers.PrimaryKeyRelatedField(queryset=scoped_companies(Company.objects.all(), request.user))
            expected_revision = serializers.IntegerField(min_value=1)
        serializer = Input(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            company = Company.objects.select_for_update().select_related('site').get(pk=serializer.validated_data['company'].pk)
            require_company_settings(request.user, company)
            if not company.active or company.site.country_code not in ('DO', 'ES'):
                raise serializers.ValidationError('Use an active Dominican or Spanish company for this setup.')
            defaults = []
            if company.site.country_code == 'DO':
                for channel, rate in [('card_terminal', '3.5'), ('recurring', '3.5'), ('payment_link', '5')]:
                    defaults.append((FeePolicy, {'channel': channel}, {'deposit_mode': 'net', 'percentage': rate,
                        'notes': 'Client-confirmed historical withholding baseline; contract start date unspecified.'}))
                    defaults.append((SettlementPolicy, {'channel': channel}, {'minimum_hours': 24, 'maximum_hours': 48,
                        'weekend_delays': True, 'notes': 'Typical elapsed hours; may take longer over weekends. Suggestion only; no holiday calendar.'}))
                defaults.append((TaxProfile, {}, {'treatment': 'no_tax', 'notes': 'Client-provided activity sales-tax default.'}))
            else:
                defaults.append((FeePolicy, {'channel': 'card_terminal'}, {'deposit_mode': 'full', 'reimbursement_expected': True,
                    'notes': 'Client reports a separate fee around EUR 36, reimbursed under an offer ending in 2027. Exact amount, frequency and offer dates unconfirmed; structured values remain unknown.'}))
                defaults.append((TaxProfile, {}, {'treatment': 'inclusive', 'rate': '21', 'notes': 'Client-provided inclusive sales-tax default; historical default, not a verified legal effective date.'}))
            missing = [(model, key, values) for model, key, values in defaults if not model.objects.filter(company=company, **key).exists()]
            if missing and serializer.validated_data['expected_revision'] != company.revision:
                raise ConfigurationConflict()
            before = dict(CompanySerializer(company).data)
            for model, key, values in missing:
                obj = model(company=company, **key, **values)
                obj.full_clean()
                obj.save()
                output = {FeePolicy: FeePolicySerializer, SettlementPolicy: SettlementPolicySerializer, TaxProfile: TaxProfileSerializer}[model](obj).data
                ConfigurationChange.objects.create(actor=request.user, target_type=obj._meta.model_name,
                    target_id=obj.pk, target_label=str(obj)[:180], before={}, after=dict(output))
            if missing:
                company.revision += 1
                company.save(update_fields=['revision', 'updated_at'])
                ConfigurationChange.objects.create(actor=request.user, target_type='company', target_id=company.pk,
                    target_label=str(company)[:180], before=before, after=dict(CompanySerializer(company).data))
            return Response({'created': len(missing), 'preserved': len(defaults) - len(missing), 'company': CompanySerializer(company).data})
