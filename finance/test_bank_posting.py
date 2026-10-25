from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from . import test_bank_imports as fixtures
POPULAR = fixtures.POPULAR
from .models import BankDecision, BankEvent, BankImportBatch, BankMovement, BankPosting

SINGLE = '\n'.join(POPULAR.splitlines()[:4]) + '\n'
BASE = SINGLE + '02/09/2026,Débito Cuenta,20.00,180.00,,456,Expense\n'


@override_settings(FINANCE_ENABLED=True)
class BankPostingTests(APITestCase):
    upload = fixtures.BankPreviewAPITests.upload

    def setUp(self):
        fixtures.BankPreviewAPITests.setUp(self)
        self.profile.can_edit_finance = True; self.profile.save()

    def preview(self, source=BASE, **fields):
        response = self.upload(source, **fields)
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def processing(self, batch):
        response = self.client.get(f'/api/finance/bank-imports/{batch}/processing/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def commit(self, batch, expected=None):
        return self.client.post(f'/api/finance/bank-imports/{batch}/commit/',
            {'expected_plan': expected or self.processing(batch)['token']}, format='json')

    def post(self, source=BASE, **fields):
        batch = self.preview(source, **fields)
        response = self.commit(batch)
        self.assertEqual(response.status_code, 200, response.data)
        return batch

    def resolve(self, batch, row, action='create', target=None, **fields):
        body = {'expected_plan': self.processing(batch)['token'], 'decision_id': row['decision_id'], 'expected_revision': row['revision'], 'action': action, 'note': 'Reviewed bank evidence'}
        if target: body.update(movement_id=target.pk, expected_movement_revision=target.revision)
        return self.client.post(f'/api/finance/bank-imports/{batch}/resolve/', {**body, **fields}, format='json')

    def undo(self, batch, expected=None):
        if expected is None:
            response = self.client.get(f'/api/finance/bank-imports/{batch}/undo-preview/')
            self.assertEqual(response.status_code, 200, response.data)
            expected = response.data['token']
        return self.client.post(f'/api/finance/bank-imports/{batch}/undo/', {'expected_plan': expected, 'note': 'Wrong upload'}, format='json')

    def test_first_commit_and_same_batch_retry_are_audited_and_idempotent(self):
        batch = self.preview()
        current = self.processing(batch)
        self.assertEqual(current['counts'], {'new': 2})
        self.assertTrue(current['can_commit'])
        self.assertEqual(self.commit(batch, current['token']).status_code, 200)
        self.assertEqual(BankMovement.objects.filter(active=True).count(), 2)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{batch}/').data['processing_status'], 'active')
        events = BankEvent.objects.count()
        self.assertEqual(self.commit(batch, current['token']).status_code, 200)
        self.assertEqual(BankEvent.objects.count(), events)
        self.assertEqual(BankImportBatch.objects.get(pk=batch).summary['financial_records_created'], 0)
        self.assertEqual(self.client.patch('/api/finance/bank-movements/1/', {}, format='json').status_code, 405)

    def test_identical_file_occurrence_links_preserve_genuine_duplicates(self):
        self.post(POPULAR)
        batch = self.preview(POPULAR)
        self.assertEqual(self.processing(batch)['counts'], {'unchanged': 3})
        self.assertEqual(self.commit(batch).status_code, 200)
        self.assertEqual(BankMovement.objects.count(), 3)
        self.assertEqual(BankDecision.objects.filter(posting__batch_id=batch, resolution='linked').count(), 3)

    def test_reordered_unique_overlapping_files_link_without_new_movements(self):
        self.post()
        lines = BASE.splitlines()
        reordered = '\n'.join(lines[:3] + list(reversed(lines[3:]))) + '\n'
        batch = self.preview(reordered)
        self.assertEqual(self.processing(batch)['counts'], {'unchanged': 2})
        self.assertEqual(self.commit(batch).status_code, 200)
        self.assertEqual(BankMovement.objects.count(), 2)

    def test_ambiguous_repeated_groups_wait_but_independent_rows_import(self):
        self.post(SINGLE)
        batch = self.post(POPULAR)
        state = self.processing(batch)
        self.assertEqual(state['counts'], {'ambiguous': 2, 'created': 1})
        target = BankMovement.objects.get(source__serial='123')
        rows = [r for r in state['rows']['results'] if r['outcome'] == 'ambiguous']
        self.assertEqual(self.resolve(batch, rows[0], 'link', target).status_code, 200)
        self.assertEqual(self.resolve(batch, rows[1], 'link', target).status_code, 400)
        self.assertEqual(self.resolve(batch, rows[1], 'create').status_code, 200)
        self.assertEqual(BankMovement.objects.count(), 3)

    def test_source_correction_requires_explicit_approval_and_retains_old_evidence(self):
        first = self.post()
        source = BASE.replace('100.00', '110.00') + '03/09/2026,Crédito Transferencia,50.00,230.00,,789,New sale\n'
        batch = self.post(source)
        target = BankMovement.objects.get(source__serial='123')
        self.assertEqual(target.source['amount'], '100.00')
        self.assertEqual(BankMovement.objects.count(), 3)
        state = self.processing(batch)
        row = next(r for r in state['rows']['results'] if r['outcome'] == 'correction')
        self.assertEqual(self.resolve(batch, row, 'correct', target, expected_movement_revision=99).status_code, 409)
        self.assertEqual(self.resolve(batch, row, 'correct', target).status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.source['amount'], '110.00')
        audit = target.events.get(action='correct')
        self.assertEqual(audit.before['source']['amount'], '100.00')
        self.assertEqual(audit.after['source']['amount'], '110.00')
        self.assertEqual(self.resolve(batch, row, 'correct', target).status_code, 409)
        # Old identical source evidence must not silently revert an approved correction.
        old = self.preview(BASE)
        self.assertEqual(self.processing(old)['counts'].get('correction'), 1)

    def test_keep_existing_or_ignore_is_a_recorded_decision(self):
        self.post()
        batch = self.post(BASE.replace('100.00', '110.00'))
        row = next(r for r in self.processing(batch)['rows']['results'] if r['outcome'] == 'correction')
        self.assertEqual(self.resolve(batch, row, 'ignore', note='').status_code, 400)
        self.assertEqual(self.resolve(batch, row, 'ignore').status_code, 200)
        self.assertEqual(BankMovement.objects.get(source__serial='123').source['amount'], '100.00')
        self.assertTrue(BankEvent.objects.filter(action='ignore', note='Reviewed bank evidence').exists())

    def test_stale_account_plan_cannot_commit_and_failed_files_cannot_post(self):
        a = self.preview(); b = self.preview()
        old = self.processing(b)['token']
        self.commit(a)
        self.assertEqual(self.commit(b, old).status_code, 409)
        self.assertEqual(BankPosting.objects.count(), 1)
        bad = self.preview('bad bank layout')
        self.assertEqual(self.commit(bad).status_code, 400)
        mixed = self.post(BASE + 'bad,row\n')
        self.assertEqual(self.processing(mixed)['counts']['invalid'], 1)

    def test_undo_untouched_rows_retains_raw_history_and_is_idempotent(self):
        batch = self.post()
        raw_count = BankImportBatch.objects.get(pk=batch).rows.count()
        token = self.client.get(f'/api/finance/bank-imports/{batch}/undo-preview/').data['token']
        self.assertEqual(self.undo(batch, token).data['status'], 'undone')
        self.assertEqual(BankMovement.objects.filter(active=True).count(), 0)
        event_count = BankEvent.objects.count()
        self.assertEqual(self.undo(batch, token).status_code, 200)
        self.assertEqual(BankEvent.objects.count(), event_count)
        self.assertEqual(BankImportBatch.objects.get(pk=batch).rows.count(), raw_count)
        self.assertEqual(self.commit(batch).status_code, 409)
        self.post()
        self.assertEqual(BankMovement.objects.filter(active=True).count(), 2)
        self.assertEqual(BankMovement.objects.count(), 4)

    def test_other_import_dependencies_protect_then_allow_fresh_undo(self):
        a = self.post(); b = self.post()
        result = self.undo(a)
        self.assertEqual(result.data['status'], 'partial_undo')
        self.assertEqual({x['reason'] for x in result.data['protected']}, {'other_import'})
        self.assertEqual(BankMovement.objects.filter(active=True).count(), 2)
        self.assertEqual(self.undo(b).data['reused_unchanged'], 2)
        self.assertEqual(self.undo(a).data['status'], 'undone')
        self.assertFalse(BankMovement.objects.filter(active=True).exists())

    def test_changed_reconciled_and_source_corrected_movements_are_protected(self):
        batch = self.post()
        first, second = list(BankMovement.objects.order_by('pk'))
        first.revision = 2; first.save()
        second.reconciled = True; second.save()
        result = self.undo(batch)
        self.assertEqual({r['reason'] for r in result.data['protected']}, {'changed', 'reconciled'})
        self.assertEqual(result.data['status'], 'partial_undo')
        self.assertEqual(BankMovement.objects.filter(active=True).count(), 2)

    def test_undo_authority_ownership_and_settings_do_not_bypass_guards(self):
        batch = self.post()
        other = get_user_model().objects.create_user('other-operator@example.test')
        profile = get_or_create_user_access_profile(other)
        for flag in ('can_view_money','can_view_finance','can_view_finance_bank_accounts','can_view_sensitive_finance','can_import_finance','can_edit_finance'):
            setattr(profile, flag, True)
        profile.save(); profile.allowed_sites.add(self.site)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{batch}/undo-preview/').status_code, 403)
        self.assertFalse(self.processing(batch)['can_undo'])
        profile.can_manage_finance_settings = True; profile.save()
        self.assertTrue(self.processing(batch)['can_undo'])
        self.assertEqual(self.undo(batch).status_code, 200)

    def test_scope_and_action_capabilities_cover_plan_ledger_and_history(self):
        batch = self.post()
        movement = BankMovement.objects.first()
        self.profile.can_edit_finance = False; self.profile.save()
        self.assertFalse(self.processing(batch)['can_undo'])
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{batch}/undo-preview/').status_code, 403)
        self.profile.can_import_finance = False; self.profile.save()
        self.assertEqual(self.commit(batch).status_code, 403)
        self.assertEqual(self.client.get('/api/finance/bank-movements/').status_code, 200)
        self.profile.allowed_sites.clear()
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{movement.pk}/history/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{batch}/processing/').status_code, 404)
        self.profile.allowed_sites.add(self.site)
        self.profile.can_view_sensitive_finance = False; self.profile.save()
        self.assertEqual(self.client.get('/api/finance/bank-movements/').status_code, 403)

    def test_history_and_reversed_filter_and_inactive_state(self):
        batch = self.post()
        movement = BankMovement.objects.first()
        history = self.client.get(f'/api/finance/bank-movements/{movement.pk}/history/')
        self.assertGreater(history.data['count'], 0)
        self.assertEqual(history.data['results'][0]['batch_id'], batch)
        self.assertGreater(self.client.get(f'/api/finance/bank-imports/{batch}/activity/').data['count'], 0)
        self.account.active = False; self.account.save()
        self.assertEqual(self.undo(batch).status_code, 400)
        self.account.active = True; self.account.save()
        self.undo(batch)
        self.assertEqual(self.client.get('/api/finance/bank-movements/').data['count'], 0)
        self.assertEqual(self.client.get('/api/finance/bank-movements/?state=reversed').data['count'], 2)
        self.assertEqual(self.client.get('/api/finance/bank-movements/?state=wrong').status_code, 400)

    def test_missing_identifiers_amount_or_date_change_is_proposed_for_review(self):
        initial = SINGLE.replace(',,123,', ',,,')
        self.post(initial)
        for changed in [initial.replace('100.00','110.00').replace('200.00','210.00'), initial.replace('01/09/2026,','02/09/2026,')]:
            batch = self.preview(changed)
            self.assertEqual(self.processing(batch)['counts'], {'correction': 1})

    def test_resolution_rejects_stale_plan_and_missing_edit_permission(self):
        self.post()
        batch = self.post(BASE.replace('100.00','110.00'))
        state = self.processing(batch)
        row = next(r for r in state['rows']['results'] if r['outcome'] == 'correction')
        self.post(BASE + '04/09/2026,Crédito Transferencia,5.00,185.00,,990,Other\n')
        response = self.resolve(batch, row, 'create', expected_plan=state['token'])
        self.assertEqual(response.status_code, 409)
        self.profile.can_edit_finance = False; self.profile.save()
        self.assertEqual(self.resolve(batch, row, 'create').status_code, 403)

    def test_approved_correction_is_protected_from_import_undo(self):
        self.post()
        batch = self.post(BASE.replace('100.00','110.00'))
        row = next(r for r in self.processing(batch)['rows']['results'] if r['outcome'] == 'correction')
        target = BankMovement.objects.get(source__serial='123')
        self.assertEqual(self.resolve(batch, row, 'correct', target).status_code, 200)
        result = self.undo(batch)
        self.assertEqual(result.data['protected'][0]['reason'], 'source_correction')
        self.assertEqual(BankMovement.objects.get(pk=target.pk).source['amount'], '110.00')

    def test_account_with_source_history_cannot_be_converted_to_cash(self):
        batch = self.preview()
        self.profile.can_manage_finance_settings = True; self.profile.save()
        response = self.client.patch(f'/api/finance/accounts/{self.account.pk}/',
            {'expected_revision': self.account.revision, 'kind': 'cash'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.account.kind = 'cash'; self.account.save()  # Simulate an unsupported external write.
        self.assertEqual(self.commit(batch).status_code, 400)


from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, close_old_connections
from rest_framework.test import APIClient, APITransactionTestCase


@skipUnless(connection.vendor == 'postgresql', 'Row-lock race checks require PostgreSQL.')
@override_settings(FINANCE_ENABLED=True)
class BankPostingRaceTests(APITransactionTestCase):
    def setUp(self):
        fixtures.BankPreviewAPITests.setUp(self)

    upload = fixtures.BankPreviewAPITests.upload

    def parallel_commit(self, requests):
        user_id = self.user.pk
        def run(item):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(get_user_model().objects.get(pk=user_id))
                response = client.post(f'/api/finance/bank-imports/{item[0]}/commit/', {'expected_plan': item[1]}, format='json')
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(run, requests))

    def test_two_distinct_stale_plans_cannot_double_post_overlapping_rows(self):
        a = self.upload(BASE).data['id']; b = self.upload(BASE).data['id']
        plans = [(batch, self.client.get(f'/api/finance/bank-imports/{batch}/processing/').data['token']) for batch in [a,b]]
        self.assertEqual(self.parallel_commit(plans), [200,409])
        self.assertEqual(BankMovement.objects.count(), 2)

    def test_two_same_batch_commits_return_one_posting(self):
        batch = self.upload(BASE).data['id']
        token = self.client.get(f'/api/finance/bank-imports/{batch}/processing/').data['token']
        self.assertEqual(self.parallel_commit([(batch,token),(batch,token)]), [200,200])
        self.assertEqual(BankPosting.objects.count(), 1)
        self.assertEqual(BankMovement.objects.count(), 2)
