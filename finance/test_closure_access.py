"""Operational closure access boundaries, using disposable partner profiles only."""
from django.contrib.auth.models import Group
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import GroupAccessProfile
from . import test_operational_checks as fixtures
from .models import ClosureCheck, ClosureCheckEvent, Company


@override_settings(FINANCE_ENABLED=True)
class ClosureAccessTests(APITestCase):
    receipt = fixtures.OperationalCheckTests.receipt
    actual = fixtures.OperationalCheckTests.actual
    get = fixtures.OperationalCheckTests.get
    method = fixtures.OperationalCheckTests.method
    day = fixtures.OperationalCheckTests.day
    check = fixtures.OperationalCheckTests.check

    def setUp(self):
        fixtures.OperationalCheckTests.setUp(self)
        self.assertEqual(self.check(note='Original review').status_code, 200)
        day = self.day()
        self.filters = {'company': self.company.pk, 'month': '2026-09',
                        'day': day['date'], 'channel': 'card_terminal'}
        self.payload = {key: value for key, value in self.filters.items() if key != 'month'}
        self.payload.update(expected_revision=day['check']['revision'], expected_token=day['check_token'])

    def assert_denied(self, status):
        before = list(ClosureCheck.objects.values()), list(ClosureCheckEvent.objects.values())
        for endpoint in ('', 'evidence/', 'history/'):
            with self.subTest(endpoint=endpoint):
                response = self.client.get('/api/finance/closures/' + endpoint, self.filters)
                self.assertEqual(response.status_code, status, response.data)
                self.assertNotIn('Original review', str(response.data))
        for operation in ('check', 'reopen'):
            with self.subTest(operation=operation):
                response = self.client.post(f'/api/finance/closures/{operation}/', self.payload, format='json')
                self.assertEqual(response.status_code, status, response.data)
        self.assertEqual((list(ClosureCheck.objects.values()), list(ClosureCheckEvent.objects.values())), before)

    def test_each_required_visibility_capability_protects_history_and_writes(self):
        for capability in ('can_view_money', 'can_view_finance',
                           'can_view_finance_bank_accounts', 'can_view_sensitive_finance'):
            with self.subTest(capability=capability):
                setattr(self.profile, capability, False)
                self.profile.save()
                self.assert_denied(403)
                setattr(self.profile, capability, True)
                self.profile.save()

    def test_viewer_can_read_history_but_cannot_check_or_reopen(self):
        self.profile.can_reconcile_finance = False
        self.profile.save()
        response = self.client.get('/api/finance/closures/history/', self.filters)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['note'], 'Original review')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertFalse(self.get()['can_check'])
        before = list(ClosureCheckEvent.objects.values())
        for operation in ('check', 'reopen'):
            response = self.client.post(f'/api/finance/closures/{operation}/', self.payload, format='json')
            self.assertEqual(response.status_code, 403)
        self.assertEqual(list(ClosureCheckEvent.objects.values()), before)

    def test_revoked_site_and_partial_studio_grants_cannot_expose_company_history(self):
        self.profile.allowed_sites.clear()
        self.assert_denied(404)
        self.profile.allowed_sites.add(self.site)
        self.profile.allowed_studios.add(self.studio)
        self.bank.studios.add(self.studio)
        self.cash.studios.add(self.studio)
        self.assert_denied(404)

    def test_another_company_cannot_be_selected_by_changing_request_ids(self):
        other = Company.objects.create(name='Other partner', site=self.es, default_currency='DOP')
        self.filters['company'] = other.pk
        self.payload['company'] = other.pk
        self.assert_denied(404)

    def test_existing_group_capabilities_can_authorize_reopening_without_user_override(self):
        self.profile.can_reconcile_finance = False
        self.profile.save()
        group = Group.objects.create(name='Closure test partner')
        GroupAccessProfile.objects.update_or_create(group=group, defaults={'can_reconcile_finance': True})
        self.user.groups.add(group)
        self.assertTrue(self.get()['can_check'])
        response = self.client.post('/api/finance/closures/reopen/', self.payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ClosureCheckEvent.objects.first().actor_id, self.user.pk)
        self.assertEqual(ClosureCheckEvent.objects.first().action, 'reopen')

    def test_disabled_finance_and_inactive_user_deny_existing_history(self):
        with override_settings(FINANCE_ENABLED=False):
            self.assert_denied(403)
        self.user.is_active = False
        self.user.save()
        self.assert_denied(403)

    def test_inactive_company_preserves_history_but_rejects_check_changes(self):
        self.company.active = False
        self.company.save()
        self.assertFalse(self.get()['can_check'])
        response = self.client.get('/api/finance/closures/history/', self.filters)
        self.assertEqual(response.status_code, 200)
        for operation in ('check', 'reopen'):
            response = self.client.post(f'/api/finance/closures/{operation}/', self.payload, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(ClosureCheckEvent.objects.count(), 1)
