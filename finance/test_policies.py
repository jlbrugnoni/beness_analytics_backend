from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .models import Company, ConfigurationChange, FeePolicy, SettlementPolicy, TaxProfile


@override_settings(FINANCE_ENABLED=True)
class PolicyTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('policies@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for key in ('can_view_money', 'can_view_finance', 'can_manage_finance_settings'):
            setattr(self.profile, key, True)
        self.profile.save()
        self.site = Site.objects.create(name='DO policies', country_code='DO')
        self.es = Site.objects.create(name='ES policies', country_code='ES')
        self.company = Company.objects.create(site=self.site, name='DO company', default_currency='DOP')
        self.spain = Company.objects.create(site=self.es, name='ES company', default_currency='EUR')
        self.profile.allowed_sites.add(self.site, self.es)
        self.client.force_authenticate(self.user)

    def setup_defaults(self, company=None, revision=None):
        company = company or self.company
        return self.client.post('/api/finance/policy-setup/', {'company': company.pk,
            'expected_revision': revision or company.revision}, format='json')

    def create(self, endpoint='fee-policies', **values):
        defaults = {'company': self.company.pk, 'channel': 'card_terminal', 'deposit_mode': 'net', 'percentage': '3.5'} if endpoint == 'fee-policies' else {'company': self.company.pk}
        return self.client.post(f'/api/finance/{endpoint}/', {**defaults, **values}, format='json')

    def update(self, obj, endpoint='fee-policies', **values):
        return self.client.patch(f'/api/finance/{endpoint}/{obj.pk}/', {'expected_revision': obj.revision, **values}, format='json')

    def preview(self, **values):
        return self.client.post('/api/finance/policy-preview/', {'company': self.company.pk, 'date': '2026-10-24',
            'channel': 'card_terminal', 'amount': '100.00', **values}, format='json')

    def test_dr_setup_and_channel_estimates(self):
        result = self.setup_defaults()
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['created'], 7)
        self.assertEqual(self.company.feepolicy_set.count(), 3)
        self.assertIsNone(FeePolicy.objects.first().valid_from)
        for channel, fee, net in [('card_terminal', '3.50', '96.50'), ('recurring', '3.50', '96.50'), ('payment_link', '5.00', '95.00')]:
            result = self.preview(channel=channel)
            self.assertEqual(result.data['estimated_withheld_fee'], fee)
            self.assertEqual(result.data['estimated_deposit'], net)
            self.assertEqual(result.data['included_tax'], '0.00')
            self.assertEqual(result.data['settlement']['maximum_hours'], 48)
            self.assertTrue(result.data['settlement']['weekend_delays'])
        result = self.preview(channel='transfer')
        self.assertIsNone(result.data['estimated_deposit'])
        self.assertTrue(result.data['requires_review'])

    def test_spain_full_deposit_unknown_separate_fee_and_inclusive_tax(self):
        self.assertEqual(self.setup_defaults(self.spain).data['created'], 2)
        fee = FeePolicy.objects.get(company=self.spain)
        self.assertIsNone(fee.separate_fee_amount)
        self.assertEqual(fee.separate_fee_frequency, 'unknown')
        self.assertTrue(fee.reimbursement_expected)
        self.assertIsNone(fee.reimbursement_until)
        self.assertIn('2027', fee.notes)
        result = self.preview(company=self.spain.pk, amount='121')
        self.assertEqual(result.data['estimated_deposit'], '121.00')
        self.assertEqual(result.data['estimated_withheld_fee'], '0.00')
        self.assertIsNone(result.data['separate_fee_amount'])
        self.assertEqual(result.data['included_tax'], '21.00')
        self.assertEqual(result.data['result_basis'], 'tax_inclusive')
        self.assertIsNone(result.data['settlement'])

    def test_setup_preserves_inactive_customized_rules_and_stale_complete_retry(self):
        self.setup_defaults()
        fee = FeePolicy.objects.get(company=self.company, channel='payment_link')
        self.assertEqual(self.update(fee, percentage='4', active=False).status_code, 200)
        count = ConfigurationChange.objects.count()
        result = self.setup_defaults(revision=1)
        self.assertEqual(result.data['created'], 0)
        self.assertEqual(result.data['preserved'], 7)
        self.assertEqual(ConfigurationChange.objects.count(), count)
        fee.refresh_from_db()
        self.assertEqual(fee.percentage, Decimal('4'))
        self.assertFalse(fee.active)

    def test_setup_rejects_stale_partial_without_writes(self):
        self.company.revision = 2; self.company.save()
        self.assertEqual(self.setup_defaults(revision=1).status_code, 409)
        self.assertFalse(FeePolicy.objects.exists())
        self.assertFalse(ConfigurationChange.objects.exists())

    def test_inclusive_dates_no_overlaps_and_dated_rate_selection(self):
        response = self.create(valid_until='2026-10-31')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.create(valid_from='2026-10-31').status_code, 400)
        self.assertEqual(self.create(valid_from='2026-11-01', percentage='4').status_code, 201)
        self.assertEqual(self.preview(date='2026-10-31').data['estimated_withheld_fee'], '3.50')
        self.assertEqual(self.preview(date='2026-11-01').data['estimated_withheld_fee'], '4.00')
        self.assertEqual(self.create(valid_from='2026-12-01', valid_until='2026-01-01').status_code, 400)
        self.assertEqual(self.create(channel='recurring').status_code, 201)

    def test_reactivation_overlap_and_stale_revision(self):
        self.create(active=False)
        obj = FeePolicy.objects.get()
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.update(obj, active=True).status_code, 400)
        self.assertEqual(self.update(obj, expected_revision=99, notes='stale').status_code, 409)
        self.assertEqual(self.client.delete(f'/api/finance/fee-policies/{obj.pk}/').status_code, 405)

    def test_fee_validation_unknown_zero_and_offer_dates(self):
        for values in [{'percentage': '-1'}, {'percentage': '101'}, {'deposit_mode': 'full'},
                       {'separate_fee_amount': '36'}, {'reimbursement_from': '2026-01-01'},
                       {'reimbursement_expected': True, 'reimbursement_from': '2027-01-01', 'reimbursement_until': '2026-01-01'}]:
            self.assertEqual(self.create(**values).status_code, 400, values)
        self.assertEqual(self.create(percentage=None).status_code, 201)
        self.assertIsNone(self.preview().data['estimated_deposit'])
        obj = FeePolicy.objects.get()
        self.assertEqual(self.update(obj, percentage='0').status_code, 200)
        self.assertEqual(self.preview().data['estimated_deposit'], '100.00')

    def test_tax_profiles_distinguish_unknown_exempt_and_explicit_zero(self):
        self.assertEqual(self.create('tax-profiles', treatment='inclusive').status_code, 400)
        self.assertEqual(self.create('tax-profiles', treatment='no_tax', rate='0').status_code, 400)
        self.assertEqual(self.create('tax-profiles', treatment='inclusive', rate='21').status_code, 201)
        self.assertEqual(self.preview(amount='121').data['included_tax'], '21.00')
        self.assertEqual(self.create('tax-profiles', treatment='exempt').status_code, 400)
        obj = TaxProfile.objects.get()
        self.assertEqual(self.update(obj, 'tax-profiles', treatment='unknown', rate=None).status_code, 200)
        self.assertIsNone(self.preview().data['included_tax'])
        obj.refresh_from_db()
        self.assertEqual(self.update(obj, 'tax-profiles', treatment='exempt').status_code, 200)
        self.assertEqual(self.preview().data['included_tax'], '0.00')

    def test_settlement_invalid_range_and_no_unconfigured_date_guesses(self):
        self.assertEqual(self.create('settlement-policies', channel='card_terminal', minimum_hours=48, maximum_hours=24).status_code, 400)
        self.assertIsNone(self.preview().data['settlement'])
        self.assertEqual(self.create('settlement-policies', channel='card_terminal', minimum_hours=24, maximum_hours=48, weekend_delays=True).status_code, 201)
        self.assertEqual(self.preview().data['settlement']['minimum_hours'], 24)

    def test_scope_capabilities_and_feature_gate(self):
        self.profile.allowed_sites.remove(self.es)
        self.assertEqual(self.preview(company=self.spain.pk).status_code, 400)
        self.assertEqual(self.create(company=self.spain.pk).status_code, 400)
        self.assertEqual(self.client.get('/api/finance/fee-policies/?company=oops').status_code, 400)
        studio = Studio.objects.create(name='Only studio', site=self.site)
        self.profile.allowed_studios.add(studio)
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(self.preview().status_code, 403)
        self.assertEqual(self.setup_defaults().status_code, 403)
        self.profile.allowed_studios.clear()
        self.profile.can_manage_finance_settings = False; self.profile.save()
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(self.preview().status_code, 403)
        with override_settings(FINANCE_ENABLED=False):
            self.assertEqual(self.client.get('/api/finance/tax-profiles/').status_code, 403)

    def test_policy_identity_and_company_currency_and_site_protected(self):
        self.create()
        obj = FeePolicy.objects.get()
        self.assertEqual(self.update(obj, company=self.spain.pk).status_code, 400)
        self.assertEqual(self.update(obj, channel='recurring').status_code, 400)
        response = self.client.patch(f'/api/finance/companies/{self.company.pk}/',
            {'expected_revision': 1, 'site': self.es.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/finance/companies/{self.company.pk}/',
            {'expected_revision': 1, 'default_currency': 'EUR'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_preview_is_readonly_and_rounds_withheld_once(self):
        self.setup_defaults()
        before = ConfigurationChange.objects.count()
        result = self.preview(amount='1.00')
        self.assertEqual(result.data['estimated_withheld_fee'], '0.04')
        self.assertEqual(result.data['estimated_deposit'], '0.96')
        self.assertEqual(ConfigurationChange.objects.count(), before)
        self.assertEqual(self.preview(amount='-1').status_code, 400)
        self.assertEqual(self.preview(amount='NaN').status_code, 400)

    def test_long_company_name_audits_and_scope_filtered_reads(self):
        self.company.name = 'A' * 180; self.company.save()
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        audit = ConfigurationChange.objects.get()
        self.assertLessEqual(len(audit.target_label), 180)
        self.profile.allowed_sites.remove(self.site)
        self.assertEqual(self.client.get(f'/api/finance/fee-policies/{response.data["id"]}/').status_code, 404)
        self.assertEqual(self.client.get('/api/finance/fee-policies/').data['count'], 0)

    def test_confirmed_separate_fee_is_not_subtracted_from_full_deposit(self):
        response = self.create(deposit_mode='full', percentage=None, separate_fee_amount='36.25',
            separate_fee_frequency='monthly', reimbursement_expected=True,
            reimbursement_from='2026-01-01', reimbursement_until='2027-01-01')
        self.assertEqual(response.status_code, 201, response.data)
        result = self.preview()
        self.assertEqual(result.data['estimated_deposit'], '100.00')
        self.assertEqual(result.data['separate_fee_amount'], '36.25')
        self.assertEqual(result.data['separate_fee_frequency'], 'monthly')
