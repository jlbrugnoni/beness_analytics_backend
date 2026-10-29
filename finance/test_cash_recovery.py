from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_money_ledger as fixtures
from .models import BankMovement,ClosureCheck


@override_settings(FINANCE_ENABLED=True)
class CashRecoveryTests(APITestCase):
    setUp=fixtures.MoneyLedgerTests.setUp
    upload=fixtures.MoneyLedgerTests.upload
    cash_workbook=fixtures.MoneyLedgerTests.cash_workbook
    cash_plan=fixtures.MoneyLedgerTests.cash_plan
    import_cash=fixtures.MoneyLedgerTests.import_cash
    payload=fixtures.MoneyLedgerTests.payload
    create=fixtures.MoneyLedgerTests.create
    def imported(self):
        b=self.upload(self.cash_workbook()).data['id'];r=self.import_cash(b);self.assertEqual(r.status_code,200,r.data);return b
    def plan(self,b,mode='undo'):
        r=self.client.get(f'/api/finance/migration-imports/{b}/cash-recovery/',{'account':self.cash.pk,'mode':mode});self.assertEqual(r.status_code,200,r.data);return r.data
    def recover(self,b,mode='undo',**changes):
        return self.client.post(f'/api/finance/migration-imports/{b}/cash-recovery/',{'account':self.cash.pk,'mode':mode,'expected_plan':self.plan(b,mode)['token'],'note':'Review original migration',**changes},format='json')

    def test_undo_restore_preserve_ids_sources_and_cash_occurrences(self):
        b=self.imported();original=list(BankMovement.objects.order_by('pk').values_list('pk','source'))
        self.assertEqual(len(self.plan(b)['eligible']),2);r=self.recover(b);self.assertEqual(r.data['changed'],2)
        self.assertFalse(BankMovement.objects.filter(active=True).exists());self.assertEqual(BankMovement.objects.count(),2)
        self.assertEqual(self.cash_plan(b)['pending'],2)
        self.assertEqual(len(self.plan(b,'restore')['eligible']),2);r=self.recover(b,'restore');self.assertEqual(r.data['changed'],2)
        self.assertEqual(list(BankMovement.objects.order_by('pk').values_list('pk','source')),original)
        self.assertEqual(self.cash_plan(b)['already_imported'],2)
        self.assertEqual(self.recover(b).data['changed'],2) # A restored import can be undone again.

    def test_edits_checked_receipts_and_stale_recovery_are_protected(self):
        b=self.imported();old=self.plan(b)['token'];items=list(BankMovement.objects.all());items[0].classification.description='Later classified';items[0].classification.save()
        ClosureCheck.objects.create(company=self.company,day='2026-09-01',channel='cash',state='checked',snapshot={'records':[{'side':'actual','id':items[1].pk}]})
        plan=self.plan(b);self.assertEqual(len(plan['protected']),2);self.assertFalse(plan['eligible'])
        self.assertEqual(self.recover(b,expected_plan=old).status_code,409)
        self.assertEqual(BankMovement.objects.filter(active=True).count(),2)

    def test_restore_detects_manual_overlap_and_permission_is_rechecked(self):
        b=self.imported();self.recover(b);self.create(amount='40.00')
        self.assertEqual({p['reason'] for p in self.plan(b,'restore')['protected']},{'possible_overlap'})
        self.profile.can_edit_finance=False;self.profile.save();self.assertEqual(self.recover(b,'restore').status_code,403)
        self.assertEqual(BankMovement.objects.filter(active=True).count(),1)
