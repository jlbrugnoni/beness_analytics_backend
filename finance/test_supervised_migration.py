"""Explicit supervised baselines approve assignments, never invalid facts or routine reports."""
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_migration_bank as bank
from . import test_migration_imports as migration
from . import test_migration_sales as sales
from .models import Account,BankMovement,FinancialSale,FinancialReceipt,SourceMapping,PaymentImportBatch


@override_settings(FINANCE_ENABLED=True)
class SupervisedBankTests(APITestCase):
    setUp=bank.HistoricalBankTests.setUp
    prepare=bank.HistoricalBankTests.prepare
    plan=bank.HistoricalBankTests.plan
    commit=bank.HistoricalBankTests.commit

    def load(self,supervised,source=None):
        response=migration.MigrationAPITests.upload(self,source,supervised=supervised)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['supervised'],supervised)
        prepared=self.prepare(response.data['id']);self.assertEqual(prepared.status_code,201,prepared.data)
        self.commit(prepared.data['id'])
        return response.data['id']

    def test_supervised_bank_credit_is_reviewed_without_legacy_checkbox(self):
        self.load(True)
        credit=BankMovement.objects.get(source__direction='credit')
        self.assertTrue(credit.classification.reviewed)
        self.assertFalse(credit.reconciled)
        self.assertEqual(credit.classification.operation_date.isoformat(),'2026-09-02')
        self.assertTrue(credit.created_from.batch.migration_batch.supervised)

    def test_unsupervised_keeps_original_checkbox_behavior(self):
        self.load(False)
        self.assertFalse(BankMovement.objects.get(source__direction='credit').classification.reviewed)
        self.assertTrue(BankMovement.objects.get(source__direction='debit').classification.reviewed)

    def test_supervised_does_not_approve_missing_classifications(self):
        self.load(True,migration.workbook(debits=[{'bank_date':'2026-09-09','amount':100,'location':'Unknown studio','expense_period':None}],credits=[]))
        self.assertFalse(BankMovement.objects.get().classification.reviewed)


    def test_supervised_cash_receipt_is_reviewed_and_keeps_cash_origin(self):
        cash=Account.objects.create(company=self.company,name='Cash',kind='cash',currency='DOP',statement_imports_expected=False)
        source=migration.workbook(debits=[],credits=[{'bank_date':'2026-09-04','amount':200,
            'operation_date':'2026-09-02','payment_method':'Efectivo','location':'Studio QA'}])
        response=migration.MigrationAPITests.upload(self,source,supervised=True)
        batch=response.data['id']
        plan=self.client.get(f'/api/finance/migration-imports/{batch}/cash-preview/',{'account':cash.pk})
        self.assertEqual(plan.status_code,200,plan.data)
        result=self.client.post(f'/api/finance/migration-imports/{batch}/import-cash/',
            {'account':cash.pk,'expected_plan':plan.data['token']},format='json')
        self.assertEqual(result.status_code,200,result.data)
        movement=BankMovement.objects.get()
        self.assertTrue(movement.classification.reviewed)
        self.assertEqual(movement.account_id,cash.pk)
        self.assertFalse(movement.reconciled)


@override_settings(FINANCE_ENABLED=True)
class SupervisedAlegraTests(APITestCase):
    setUp=migration.MigrationAPITests.setUp
    commit=sales.WorkbookAlegraAPITests.commit

    def load(self,supervised,conflict=False):
        studio=Studio.objects.create(site=self.site,name='Studio QA')
        SourceMapping.objects.create(company=self.company,source_field='alegra_cost_center',source_value='Studio QA',studio=studio)
        SourceMapping.objects.create(company=self.company,source_field='alegra_payment_method',source_value='Tarjeta crédito',channel='card_terminal',requires_review=True)
        if conflict:
            other=Studio.objects.create(site=self.site,name='Other')
            SourceMapping.objects.create(company=self.company,source_field='alegra_price_list',source_value='Other',studio=other)
        source=sales.combined([{'price_list':'Other'}] if conflict else None)
        response=migration.MigrationAPITests.upload(self,source,supervised=supervised)
        prepared=self.client.post(f"/api/finance/migration-imports/{response.data['id']}/prepare-alegra/",{},format='json')
        self.assertEqual(prepared.status_code,200,prepared.data)
        payment_batch=PaymentImportBatch.objects.get(pk=prepared.data['payment_batch']['id'])
        row=payment_batch.rows.get(source__number='101');row.source['method']='';row.save()
        self.commit('sales',prepared.data['sales_batch']['id']);self.commit('payment',payment_batch.pk)
        return FinancialSale.objects.get(),FinancialReceipt.objects.get(number='101')

    def test_supervised_clears_only_resolved_assignment_review_and_keeps_evidence(self):
        sale,receipt=self.load(True)
        self.assertFalse(sale.assignments['requires_review'])
        self.assertIn('channel_mapping_requires_review',sale.assignments['warnings'])
        self.assertFalse(receipt.assignments['channel_review'])
        self.assertEqual(receipt.assignments['review_basis'],'supervised_migration')
        self.assertEqual(receipt.source['original_method'],'Tarjeta crédito')
        self.assertEqual(receipt.sale_id,sale.pk)
        self.assertFalse(receipt.reconciled)

    def test_unsupervised_still_requires_ambiguous_card_method_review(self):
        sale,receipt=self.load(False)
        self.assertTrue(sale.assignments['requires_review'])
        self.assertTrue(receipt.assignments['channel_review'])
        self.assertNotIn('review_basis',receipt.assignments)

    def test_supervised_keeps_real_cost_center_price_list_conflict_for_review(self):
        sale,receipt=self.load(True,conflict=True)
        self.assertTrue(sale.assignments['requires_review'])
        self.assertIn('studio_conflict',sale.assignments['warnings'])
        self.assertFalse(receipt.assignments['channel_review'])
