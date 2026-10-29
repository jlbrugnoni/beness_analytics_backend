from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .models import Account, Company, ConfigurationChange, Terminal


@override_settings(FINANCE_ENABLED=True)
class ConfigurationTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('configuration@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for key in ('can_view_money', 'can_view_finance', 'can_manage_finance_settings', 'can_view_finance_bank_accounts'):
            setattr(self.profile, key, True)
        self.profile.save()
        self.site = Site.objects.create(name='DO', country_code='DO')
        self.foreign = Site.objects.create(name='ES', country_code='ES')
        self.studio = Studio.objects.create(name='Bella Vista', site=self.site)
        self.two = Studio.objects.create(name='Piantini', site=self.site)
        self.foreign_studio = Studio.objects.create(name='Estepona', site=self.foreign)
        self.profile.allowed_sites.add(self.site)
        self.company = Company.objects.create(name='Test company', site=self.site, default_currency='DOP')
        self.account = Account.objects.create(company=self.company, name='Operativa', currency='DOP')
        self.client.force_authenticate(self.user)

    def terminal(self, **overrides):
        return self.client.post('/api/finance/terminals/', {
            'account': self.account.pk, 'identifier': '39618800002', 'studio': self.studio.pk,
            'channel': 'card_terminal', **overrides}, format='json')

    def test_company_create_update_and_no_hard_delete(self):
        response = self.client.post('/api/finance/companies/', {'name': 'Second company', 'site': self.site.pk, 'default_currency': 'DOP'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/finance/companies/{response.data['id']}/"
        response = self.client.patch(url, {'name': 'Renamed', 'expected_revision': 1}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['revision'], 2)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(ConfigurationChange.objects.count(), 2)
        self.assertEqual(ConfigurationChange.objects.first().before['name'], 'Second company')

    def test_savings_zero_is_distinct_from_unknown_and_no_statements(self):
        response = self.client.post('/api/finance/accounts/', {'company': self.company.pk, 'name': 'Ahorro', 'currency': 'DOP',
            'opening_balance': '0.00', 'opening_balance_date': '2026-01-01', 'statement_imports_expected': False}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['opening_balance'], '0.00')
        self.assertFalse(response.data['statement_imports_expected'])
        self.assertIsNone(self.client.get(f'/api/finance/accounts/{self.account.pk}/').data['opening_balance'])

    def test_opening_balance_requires_date_and_date_requires_balance(self):
        url = f'/api/finance/accounts/{self.account.pk}/'
        for payload in ({'opening_balance': '0'}, {'opening_balance_date': '2026-01-01'}):
            response = self.client.patch(url, {**payload, 'expected_revision': 1}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ConfigurationChange.objects.count(), 0)

    def test_stale_and_missing_revision_do_not_overwrite(self):
        url = f'/api/finance/accounts/{self.account.pk}/'
        self.assertEqual(self.client.patch(url, {'name': 'First', 'expected_revision': 1}).status_code, 200)
        for payload in ({'expected_revision': 1}, {}):
            self.assertEqual(self.client.patch(url, {'name': 'Stale', **payload}).status_code, 409)
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, 'First')
        self.assertEqual(ConfigurationChange.objects.count(), 1)

    def test_atomic_audit_failure_rolls_back(self):
        with patch('finance.configuration.ConfigurationChange.objects.create', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.client.patch(f'/api/finance/accounts/{self.account.pk}/', {'name': 'Must roll back', 'expected_revision': 1})
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, 'Operativa')
        self.assertEqual(self.account.revision, 1)

    def test_terminal_mapping_and_duplicate_guard(self):
        response = self.terminal()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['identifier'], '39618800002')
        self.assertEqual(response.data['studio_name'], 'Bella Vista')
        self.assertEqual(self.terminal().status_code, 400)
        response = self.client.patch(f"/api/finance/terminals/{response.data['id']}/", {'active': False, 'expected_revision': 1})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['active'])
        self.assertEqual(ConfigurationChange.objects.count(), 2)

    def test_terminal_cannot_use_foreign_or_nonparticipating_studio_or_cash(self):
        self.assertEqual(self.terminal(studio=self.foreign_studio.pk).status_code, 400)
        self.account.studios.set([self.two])
        self.assertEqual(self.terminal().status_code, 400)
        self.account.studios.clear()
        self.account.kind = 'cash'; self.account.save()
        self.assertEqual(self.terminal().status_code, 400)

    def test_ownership_currency_and_terminal_account_immutable(self):
        for payload in ({'company': 99999}, {'currency': 'EUR'}):
            self.assertEqual(self.client.patch(f'/api/finance/accounts/{self.account.pk}/', {**payload, 'expected_revision': 1}).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/finance/companies/{self.company.pk}/', {'default_currency': 'EUR', 'expected_revision': 1}).status_code, 400)
        terminal = self.terminal().data
        other = Account.objects.create(company=self.company, name='Other', currency='DOP')
        self.assertEqual(self.client.patch(f"/api/finance/terminals/{terminal['id']}/", {'account': other.pk, 'expected_revision': 1}).status_code, 400)

    def test_cannot_drop_mapped_studio_or_change_terminal_account_to_cash(self):
        self.terminal()
        url = f'/api/finance/accounts/{self.account.pk}/'
        self.assertEqual(self.client.patch(url, {'studios': [self.two.pk], 'expected_revision': 1}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'kind': 'cash', 'expected_revision': 1}).status_code, 400)

    def test_settings_and_account_view_are_separate_prerequisites(self):
        self.profile.can_manage_finance_settings = False; self.profile.save()
        self.assertEqual(self.terminal().status_code, 403)
        self.assertEqual(self.client.get('/api/finance/configuration-options/').status_code, 403)
        self.profile.can_manage_finance_settings = True
        self.profile.can_view_finance_bank_accounts = False; self.profile.save()
        self.assertEqual(self.terminal().status_code, 403)
        self.assertEqual(self.client.get('/api/finance/terminals/').status_code, 403)

    def test_foreign_and_studio_scopes_cannot_widen_access(self):
        self.assertEqual(self.client.post('/api/finance/companies/', {'name': 'Foreign', 'site': self.foreign.pk, 'default_currency': 'EUR'}).status_code, 400)
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.client.get('/api/finance/configuration-options/').data['sites'], [])
        self.assertEqual(self.client.patch(f'/api/finance/companies/{self.company.pk}/', {'name': 'No', 'expected_revision': 1}).status_code, 403)
        self.assertEqual(self.client.post('/api/finance/accounts/', {'company': self.company.pk, 'name': 'No', 'currency': 'DOP'}).status_code, 403)
        self.account.studios.add(self.studio)
        self.assertEqual(self.client.patch(f'/api/finance/accounts/{self.account.pk}/', {'studios': [], 'expected_revision': 1}, format='json').status_code, 403)
        self.assertEqual(self.terminal(studio=self.two.pk).status_code, 400)

    def test_archived_account_blocks_terminal_changes(self):
        self.account.active = False; self.account.save()
        self.assertEqual(self.terminal().status_code, 403)
        self.assertEqual(Terminal.objects.count(), 0)

    @override_settings(FINANCE_ENABLED=False)
    def test_feature_flag_also_blocks_writes(self):
        self.assertEqual(self.terminal().status_code, 403)
        self.assertEqual(self.client.get('/api/finance/configuration-options/').status_code, 403)
