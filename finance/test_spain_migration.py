from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_migration_imports as fixtures
from .models import Account,Category,BankMovement,BankMovementClassification,MigrationImportBatch,Terminal
from .spain_migration import read_spanish_migration


@override_settings(FINANCE_ENABLED=True)
class SpainMigrationTests(APITestCase):
    def setUp(self):
        fixtures.MigrationAPITests.setUp(self)
        self.company=self.spain
        self.profile.allowed_sites.add(self.es)
        self.profile.can_import_finance_migration=True;self.profile.can_edit_finance=True;self.profile.save()
        self.studio=Studio.objects.create(site=self.es,name='Estepona')
        self.bank=Account.objects.create(company=self.company,name='Caixa',currency='EUR')
        self.cash=Account.objects.create(company=self.company,name='Cash',kind='cash',currency='EUR')
        Terminal.objects.create(account=self.bank,identifier='369092994',studio=self.studio,channel='card_terminal')
        self.category=Category.objects.create(company=self.company,name='Services')
        self.sub=Category.objects.create(company=self.company,parent=self.category,name='Electricity')

    def upload(self,source=None,**values):
        return fixtures.MigrationAPITests.upload(self,source,supervised=True,**values)

    def preview(self,source):
        response=self.upload(source)
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']

    def prepare(self,batch):
        ids=self.client.get(f'/api/finance/migration-imports/{batch}/bank-candidates/').data['row_ids']
        response=self.client.post(f'/api/finance/migration-imports/{batch}/prepare-bank/',
            {'account':self.bank.pk,'row_ids':ids,'confirm_bank_origin':True},format='json')
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']

    def post(self,bank_batch):
        plan=self.client.get(f'/api/finance/bank-imports/{bank_batch}/processing/').data
        response=self.client.post(f'/api/finance/bank-imports/{bank_batch}/commit/',{'expected_plan':plan['token']},format='json')
        self.assertEqual(response.status_code,200,response.data)
        return plan

    def source(self):
        return fixtures.workbook(debits=[dict(bank_date='2026-09-09',amount=-100,original_description='Utility debit',
            manual_description='Electricity',expense_period='2026-08-01',category='Services',subcategory='Electricity')],
            credits=[dict(bank_date='2026-09-04',amount=200,operation_date='2026-09-02',balance=1000,
                original_description='ON 369092994 0209',payment_method='Cierre')])

    def test_supervised_eur_import_default_studio_categories_period_and_repeat(self):
        batch=self.preview(self.source());bank_batch=self.prepare(batch);self.post(bank_batch)
        debit=BankMovement.objects.get(source__direction='debit');credit=BankMovement.objects.get(source__direction='credit')
        self.assertEqual(debit.source['currency'],'EUR');self.assertEqual(debit.provider,'caixa')
        self.assertEqual(debit.classification.studio_id,self.studio.pk)
        self.assertEqual(debit.classification.category_id,self.category.pk)
        self.assertEqual(str(debit.classification.expense_period),'2026-08-01')
        self.assertTrue(debit.classification.reviewed)
        self.assertEqual(credit.classification.terminal.identifier,'369092994');self.assertTrue(credit.classification.reviewed)
        repeated=self.prepare(self.preview(self.source()));plan=self.post(repeated)
        self.assertEqual(plan['counts'],{'unchanged':2})
        self.assertEqual(BankMovement.objects.count(),2)

    def test_cash_deposits_stay_bank_internal_and_ambiguous_transfers_remain_pending(self):
        source=fixtures.workbook(debits=[],credits=[
            dict(bank_date='2026-09-04',amount=100,original_description='INGRESO CAJERO',payment_method='Efectivo'),
            dict(bank_date='2026-09-05',amount=9000,original_description='TRASPASO',payment_method='Efectivo')])
        batch=self.preview(source);self.post(self.prepare(batch))
        deposit=BankMovement.objects.get(source__amount='100.00');transfer=BankMovement.objects.get(source__amount='9000.00')
        self.assertEqual(deposit.account_id,self.bank.pk);self.assertEqual(deposit.classification.movement_kind,'internal_transfer')
        self.assertTrue(deposit.classification.reviewed)
        self.assertFalse(transfer.classification.reviewed);self.assertEqual(transfer.classification.channel,'')
        for suffix in ('cash-preview/?account='+str(self.cash.pk),'alegra/'):
            self.assertEqual(self.client.get(f'/api/finance/migration-imports/{batch}/{suffix}').status_code,400)
        self.assertEqual(self.client.post(f'/api/finance/migration-imports/{batch}/import-cash/',{'account':self.cash.pk,'expected_plan':'a'*64},format='json').status_code,400)
        self.assertFalse(BankMovement.objects.filter(account=self.cash).exists())

    def test_missing_classification_or_period_stays_pending_and_default_is_selectable(self):
        other=Studio.objects.create(site=self.es,name='Another studio')
        self.assertEqual(self.upload(self.source()).status_code,400)
        response=self.upload(self.source(),default_studio=other.pk)
        self.assertEqual(response.status_code,201,response.data)
        batch=response.data['id'];self.assertEqual(response.data['summary']['default_studio'],other.pk)
        self.post(self.prepare(batch))
        self.assertEqual(BankMovement.objects.get(source__direction='debit').classification.studio_id,other.pk)
        source=fixtures.workbook(debits=[dict(bank_date='2026-09-10',amount=-20,original_description='Pending')],credits=[])
        batch=self.preview_with_studio(source,other.pk)
        self.post(self.prepare(batch))
        self.assertFalse(BankMovement.objects.get(source__amount='-20.00').classification.reviewed)

    def preview_with_studio(self,source,studio):
        response=self.upload(source,default_studio=studio);self.assertEqual(response.status_code,201,response.data)
        return response.data['id']

    def test_approved_dates_are_corrected_only_for_exact_source_and_raw_cells_preserved(self):
        source=fixtures.workbook(debits=[],credits=[dict(bank_date='2026-09-05',operation_date='2026-05-08',amount=274.50,
            original_description='ON 369092994 0805',payment_method='Cierre')])
        parsed=read_spanish_migration(source,'2026-05',self.studio)
        row=parsed['rows'][0]
        self.assertEqual(row['bank_date'],'2026-05-09')
        self.assertEqual(row['parsed']['source_bank_date'],'2026-09-05')
        self.assertEqual(next(c['value'] for c in row['raw'] if c['cell']=='A2'),'2026-09-05')
        self.assertEqual(len(parsed['summary']['approved_date_corrections']),1)
        self.assertEqual(parsed['summary']['bank_date_months']['2026-05']['credit_total'],'274.50')

    def test_bank_report_overlap_without_workbook_balance_reuses_entry_and_preserves_review(self):
        existing=BankMovement.objects.create(account=self.bank,provider='caixa',fingerprint='test',
            source={'bank_date':'2026-09-09','amount':'-100.00','currency':'EUR','direction':'debit',
                'description':'Utility debit','balance':'500.00','reference':'','serial':'','short_description':''})
        BankMovementClassification.objects.create(movement=existing,description='Keep correction',studio=self.studio,
            category=self.category,subcategory=self.sub,expense_period='2026-08-01',movement_kind='expense',reviewed=True)
        source=fixtures.workbook(debits=[dict(bank_date='2026-09-09',amount=-100,original_description='Utility debit',
            manual_description='Keep correction',expense_period='2026-08-01',category='Services',subcategory='Electricity')],credits=[])
        plan=self.post(self.prepare(self.preview(source)))
        self.assertEqual(plan['counts'],{'unchanged':1})
        existing.refresh_from_db();self.assertEqual(existing.source['balance'],'500.00')
        self.assertEqual(existing.classification.description,'Keep correction');self.assertTrue(existing.classification.reviewed)
        self.assertEqual(BankMovement.objects.count(),1)

    def test_missing_migration_permission_does_not_post(self):
        self.profile.can_import_finance_migration=False;self.profile.save()
        self.assertEqual(self.upload(self.source()).status_code,403)
        self.assertFalse(MigrationImportBatch.objects.exists())

    def test_multiple_same_fact_bank_occurrences_require_review_without_creating_duplicates(self):
        for value,balance in (('-100.00','500.00'),('-100.00','400.00'),('-200.00','200.00')):
            movement=BankMovement.objects.create(account=self.bank,provider='caixa',fingerprint=balance,
                source={'bank_date':'2026-09-09','amount':value,'currency':'EUR','direction':'debit',
                    'description':'Utility debit','balance':balance,'reference':'','serial':'','short_description':''})
            BankMovementClassification.objects.create(movement=movement,movement_kind='expense')
        source=fixtures.workbook(debits=[dict(bank_date='2026-09-09',amount=-100,original_description='Utility debit')],credits=[])
        plan=self.post(self.prepare(self.preview(source)))
        self.assertEqual(plan['counts'],{'ambiguous':1})
        self.assertEqual(plan['rows']['results'][0]['candidate_count'],2)
        self.assertEqual(BankMovement.objects.count(),3)

    def test_legacy_local_category_uses_common_catalog_code(self):
        category=Category.objects.create(company=self.company,name='Local / Instalaciones',catalog_code='local')
        child=Category.objects.create(company=self.company,parent=category,name='Alquiler')
        source=fixtures.workbook(debits=[dict(bank_date='2026-09-09',amount=-100,original_description='Rent debit',
            expense_period='2026-09-01',category='Local',subcategory='Alquiler')],credits=[])
        self.post(self.prepare(self.preview(source)))
        item=BankMovement.objects.get().classification
        self.assertEqual(item.category_id,category.pk);self.assertEqual(item.subcategory_id,child.pk)
        self.assertTrue(item.reviewed)

    def test_same_day_description_with_different_amount_does_not_make_unique_match_ambiguous(self):
        for value,balance in (('-100.00','500.00'),('-200.00','300.00')):
            movement=BankMovement.objects.create(account=self.bank,provider='caixa',fingerprint=balance,
                source={'bank_date':'2026-09-09','amount':value,'currency':'EUR','direction':'debit',
                    'description':'Same bank concept','balance':balance,'reference':'','serial':'','short_description':''})
            BankMovementClassification.objects.create(movement=movement,movement_kind='expense')
        source=fixtures.workbook(debits=[dict(bank_date='2026-09-09',amount=-100,original_description='Same bank concept')],credits=[])
        plan=self.post(self.prepare(self.preview(source)))
        self.assertEqual(plan['counts'],{'unchanged':1})
        self.assertEqual(BankMovement.objects.count(),2)
