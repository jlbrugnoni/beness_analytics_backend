"""Comparison-only whitespace and strong historical evidence regressions."""
from copy import deepcopy
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from . import test_migration_bank as fixtures
workbook=fixtures.workbook
from .test_bank_imports import POPULAR
from .models import BankMovement,BankMovementClassification


@override_settings(FINANCE_ENABLED=True)
class BankIdentityTests(APITestCase):
    setUp=fixtures.HistoricalBankTests.setUp
    migration=fixtures.HistoricalBankTests.migration
    prepare=fixtures.HistoricalBankTests.prepare
    plan=fixtures.HistoricalBankTests.plan
    commit=fixtures.HistoricalBankTests.commit

    def raw(self,rows):
        source='\n'.join(POPULAR.splitlines()[:3])+'\n'+'\n'.join(rows)+'\n'
        r=self.client.post('/api/finance/bank-imports/',{'account':self.account.pk,'provider':'popular',
            'file':SimpleUploadedFile('overlap.csv',source.encode())},format='multipart')
        self.assertEqual(r.status_code,201,r.data);return r.data['id']

    def history(self,rows):
        batch=self.migration(workbook(debits=[],credits=rows));prepared=self.prepare(batch)
        self.assertEqual(prepared.status_code,201,prepared.data);self.commit(prepared.data['id'])

    def test_whitespace_is_only_comparison_and_unique_balance_beats_reused_terminal(self):
        self.history([{'bank_date':'2026-09-01','amount':100,'balance':1000,'original_description':'39618800002   - AZUL CR',
            'manual_description':'Retain edited concept','location':'Studio QA','payment_method':'Cierre'},
            {'bank_date':'2026-09-02','amount':80,'balance':1080,'original_description':'39618800002 - AZUL CR'}])
        before=list(BankMovement.objects.order_by('pk').values());classifications=list(BankMovementClassification.objects.order_by('pk').values())
        # Reused serials must not drown the same-day amount/balance identity.
        from .models import BankMovement as Movement
        other=Movement.objects.get(source__bank_date='2026-09-02');other.source['serial']='REUSED';other.save()
        before=list(BankMovement.objects.order_by('pk').values())
        batch=self.raw(['01/09/2026,Crédito Transferencia,100.00,1000.00,,REUSED,39618800002 - AZUL CR'])
        plan=self.plan(batch);self.assertEqual(plan['counts'],{'unchanged':1})
        self.commit(batch);self.assertEqual(list(BankMovement.objects.order_by('pk').values()),before)
        self.assertEqual(list(BankMovementClassification.objects.order_by('pk').values()),classifications)

    def test_historical_overlap_without_balance_cannot_be_confirmed_by_terminal_serial_alone(self):
        self.history([{'bank_date':'2026-09-01','amount':100,'original_description':'AZUL'}])
        movement=BankMovement.objects.get();movement.source['serial']='TERMINAL';movement.save()
        batch=self.raw(['01/09/2026,Crédito Transferencia,100.00,,,TERMINAL,AZUL'])
        self.assertEqual(self.plan(batch)['counts'],{'correction':1})

    def test_equal_amount_occurrences_use_distinct_balances_and_substantive_changes_stay_reviewable(self):
        self.history([{'bank_date':'2026-09-01','amount':6800,'balance':10000,'original_description':'Client transfer'},
            {'bank_date':'2026-09-01','amount':6800,'balance':16800,'original_description':'Client transfer'}])
        batch=self.raw(['01/09/2026,Crédito Transferencia,6800.00,10000.00,,,Client  transfer',
            '01/09/2026,Crédito Transferencia,6800.00,16800.00,,,Client transfer'])
        p=self.plan(batch);self.assertEqual(p['counts'],{'unchanged':2})
        self.assertEqual(len({r['target'] for r in p['rows']['results']}),2)
        self.commit(batch);self.assertEqual(BankMovement.objects.count(),2)
        changed=self.raw(['01/09/2026,Crédito Transferencia,6800.00,16800.00,,,Different client'])
        self.assertNotIn('unchanged',self.plan(changed)['counts'])

    def test_native_whitespace_repeat_links_and_equal_new_occurrences_remain_pending(self):
        first=self.raw(['01/09/2026,Crédito Transferencia,100.00,1000.00,,ID-1,Terminal  settlement'])
        self.commit(first);original=deepcopy(BankMovement.objects.get().source)
        second=self.raw(['01/09/2026,Crédito Transferencia,100.00,1000.00,,ID-1,Terminal settlement'])
        self.assertEqual(self.plan(second)['counts'],{'unchanged':1});self.commit(second)
        self.assertEqual(BankMovement.objects.get().source,original)
        repeated=self.raw(['01/09/2026,Crédito Transferencia,100.00,1000.00,,ID-1,Terminal settlement',
            '01/09/2026,Crédito Transferencia,100.00,1000.00,,ID-1,Terminal  settlement'])
        self.assertEqual(self.plan(repeated)['counts'],{'ambiguous':2})
