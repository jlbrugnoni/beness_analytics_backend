from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from .models import Account, BankMovement, BankMovementClassification, BankEvent, BankImportBatch, MigrationImportBatch, Category, Terminal
from . import test_migration_imports as migration_fixtures
workbook=migration_fixtures.workbook
from .test_bank_imports import POPULAR


@override_settings(FINANCE_ENABLED=True)
class HistoricalBankTests(APITestCase):
    def setUp(self):
        migration_fixtures.MigrationAPITests.setUp(self)
        self.profile.can_edit_finance=True;self.profile.save()
        self.account=Account.objects.create(company=self.company,name='Historical bank QA',currency='DOP')
        self.studio=Studio.objects.create(site=self.site,name='Studio QA')
        parent=Category.objects.create(company=self.company,name='Services')
        Category.objects.create(company=self.company,parent=parent,name='Electricity')
        Terminal.objects.create(account=self.account,identifier='39618800002',studio=self.studio,channel='card_terminal')

    def migration(self,source=None):
        result=self.client.post('/api/finance/migration-imports/',{'company':self.company.pk,
            'file':SimpleUploadedFile('historical-fixture.xlsx',source or workbook())},format='multipart')
        self.assertEqual(result.status_code,201,result.data)
        return result.data['id']

    def prepare(self,batch,**values):
        candidates=self.client.get(f'/api/finance/migration-imports/{batch}/bank-candidates/').data
        return self.client.post(f'/api/finance/migration-imports/{batch}/prepare-bank/',
            {'account':self.account.pk,'row_ids':candidates['row_ids'],'confirm_bank_origin':True,**values},format='json')

    def plan(self,batch):
        response=self.client.get(f'/api/finance/bank-imports/{batch}/processing/')
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def commit(self,batch):
        result=self.client.post(f'/api/finance/bank-imports/{batch}/commit/',{'expected_plan':self.plan(batch)['token']},format='json')
        self.assertEqual(result.status_code,200,result.data)

    def native(self,amount='200.00',balance='1000.00'):
        text='\n'.join(POPULAR.splitlines()[:3])+f'\n04/09/2026,Crédito Transferencia,{amount},{balance},,NEW-ID,Native settlement\n'
        response=self.client.post('/api/finance/bank-imports/',{'account':self.account.pk,'provider':'popular',
            'file':SimpleUploadedFile('native.csv',text.encode())},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']

    def test_full_workbook_default_month_optional_and_explicit_post(self):
        batch=self.migration()
        saved=MigrationImportBatch.objects.get(pk=batch)
        self.assertEqual(str(saved.selected_month),'2026-09-01')
        result=self.prepare(batch);self.assertEqual(result.status_code,201,result.data)
        self.assertEqual(BankMovement.objects.count(),0)
        self.assertEqual(result.data['migration_batch'],batch)
        prepared=result.data['id'];self.commit(prepared)
        self.assertEqual(BankMovement.objects.count(),2)
        debit=BankMovement.objects.get(source__direction='debit')
        self.assertEqual(str(debit.classification.expense_period),'2026-08-01')
        self.assertEqual(debit.classification.description,'Synthetic utility')
        self.assertEqual(debit.classification.category.name,'Services')
        self.assertEqual(debit.classification.subcategory.name,'Electricity')
        self.assertTrue(debit.classification.reviewed);self.assertFalse(debit.reconciled)
        self.assertEqual(debit.created_from.migration_row.sheet,'Debitos')
        self.assertEqual(BankEvent.objects.filter(action='create').count(),2)
        self.commit(prepared);self.assertEqual(BankMovement.objects.count(),2)
        repeat=self.prepare(batch);self.assertEqual(repeat.status_code,201,repeat.data)
        self.commit(repeat.data['id']);self.assertEqual(BankMovement.objects.count(),2)
        evidence=self.client.get(f'/api/finance/bank-movements/{debit.pk}/').data
        self.assertEqual(evidence['historical_source']['category'],'Services')
        original=self.client.get(f'/api/finance/bank-imports/{prepared}/original/')
        self.assertIn('spreadsheet',original['Content-Type'])

    def test_requires_bank_origin_confirmation_scope_and_valid_rows(self):
        batch=self.migration()
        self.assertEqual(self.prepare(batch,confirm_bank_origin=False).status_code,400)
        self.assertEqual(self.prepare(batch,row_ids=[999999]).status_code,400)
        self.assertEqual(self.prepare(batch,row_ids=[]).status_code,400)
        foreign=Account.objects.create(company=self.spain,name='Foreign',currency='EUR')
        self.assertEqual(self.prepare(batch,account=foreign.pk).status_code,400)
        self.profile.can_import_finance=False;self.profile.save()
        self.assertEqual(self.prepare(batch).status_code,403)
        self.assertFalse(BankImportBatch.objects.exists())

    def test_cash_and_invalid_rows_remain_in_preview(self):
        batch=self.migration(workbook(credits=[{'bank_date':'2026-09-04','amount':20,'payment_method':'Efectivo'},
            {'bank_date':'bad','amount':50,'payment_method':'Cierre'}]))
        choices=self.client.get(f'/api/finance/migration-imports/{batch}/bank-candidates/').data
        self.assertEqual(choices['cash_rows'],1);self.assertEqual(choices['invalid_rows'],1)
        self.assertEqual(len(choices['row_ids']),1)
        cash=MigrationImportBatch.objects.get(pk=batch).rows.get(kind='credit',amount=20)
        self.assertEqual(self.prepare(batch,row_ids=[cash.pk]).status_code,400)
        response=self.prepare(batch);self.commit(response.data['id'])
        self.assertEqual(BankMovement.objects.count(),1)
        self.assertEqual(MigrationImportBatch.objects.get(pk=batch).rows.count(),3)

    def test_later_raw_overlap_links_without_overwriting_manual_fields(self):
        batch=self.migration();prepared=self.prepare(batch);self.commit(prepared.data['id'])
        credit=BankMovement.objects.get(source__direction='credit')
        original=dict(credit.source)
        normal=self.native()
        self.assertEqual(self.plan(normal)['counts'],{'unchanged':1})
        self.commit(normal)
        self.assertEqual(BankMovement.objects.count(),2)
        credit.refresh_from_db();self.assertEqual(credit.source,original)
        self.assertEqual(str(credit.classification.operation_date),'2026-09-02')
        self.assertEqual(credit.classification.studio_id,self.studio.pk)
        self.assertEqual(credit.classification.channel,'card_terminal')
        changed=self.native(amount='201.00',balance='1001.00')
        self.assertEqual(self.plan(changed)['counts'],{'correction':1})
        self.commit(changed);self.assertEqual(BankMovement.objects.count(),2)

    def test_bank_first_fills_missing_assignments_and_conflicts_stay_pending(self):
        normal=self.native();self.commit(normal)
        batch=self.migration();prepared=self.prepare(batch);self.assertEqual(prepared.status_code,201,prepared.data)
        self.assertEqual(self.plan(prepared.data['id'])['counts'],{'new':1,'unchanged':1})
        self.commit(prepared.data['id'])
        credit=BankMovement.objects.get(source__direction='credit')
        self.assertEqual(str(credit.classification.operation_date),'2026-09-02')
        credit.classification.description='Existing manual description';credit.classification.save()
        another=self.prepare(batch)
        self.assertIn('assignment_conflict',self.plan(another.data['id'])['counts'])
        self.commit(another.data['id']);self.assertEqual(BankMovement.objects.count(),2)
        credit.refresh_from_db();self.assertEqual(credit.classification.description,'Existing manual description')

    def test_selection_includes_september_and_does_not_imply_pilot_month_cutoff(self):
        batch=self.migration(workbook(credits=[{'bank_date':'2026-08-31','amount':10,'balance':100},
            {'bank_date':'2026-09-01','amount':15,'balance':115}]))
        saved=MigrationImportBatch.objects.get(pk=batch)
        self.assertEqual(str(saved.selected_month),'2026-08-01')
        september=saved.rows.get(bank_date='2026-09-01')
        result=self.prepare(batch,row_ids=[september.pk]);self.assertEqual(result.status_code,201,result.data)
        self.commit(result.data['id'])
        self.assertEqual(BankMovement.objects.count(),1)
        self.assertEqual(BankMovement.objects.get().source['bank_date'],'2026-09-01')
        self.assertEqual(saved.rows.count(),3)

    def test_equal_occurrences_stay_distinct_and_raw_ambiguity_is_not_autolinked(self):
        credit={'bank_date':'2026-09-04','amount':200,'balance':1000,'payment_method':'Cierre'}
        batch=self.migration(workbook(credits=[credit,credit]));result=self.prepare(batch)
        self.commit(result.data['id']);self.assertEqual(BankMovement.objects.count(),3)
        raw=self.native()
        self.assertEqual(self.plan(raw)['counts'],{'ambiguous':1})
        self.commit(raw);self.assertEqual(BankMovement.objects.count(),3)

    def test_assignment_conflict_cannot_create_duplicate_money_or_correct_source(self):
        raw=self.native();self.commit(raw)
        movement=BankMovement.objects.get()
        movement.classification.description='Already corrected';movement.classification.save()
        batch=self.migration();prepared=self.prepare(batch);self.commit(prepared.data['id'])
        plan=self.plan(prepared.data['id'])
        row=next(item for item in plan['rows']['results'] if item['outcome']=='assignment_conflict')
        for action in ('create','correct'):
            response=self.client.post(f"/api/finance/bank-imports/{prepared.data['id']}/resolve/",{
                'expected_plan':plan['token'],'decision_id':row['decision_id'],'expected_revision':row['revision'],
                'action':action,'note':'Synthetic review','movement_id':movement.pk,'expected_movement_revision':movement.revision},format='json')
            self.assertEqual(response.status_code,400,response.data)
        self.assertEqual(BankMovement.objects.count(),2)

    def test_unknown_classifications_are_preserved_in_source_without_inventing_config(self):
        batch=self.migration(workbook(debits=[{'bank_date':'2026-09-01','amount':20,'manual_description':'Keep this text',
            'expense_period':'2026-08-01','category':'Unconfigured category','subcategory':'Unconfigured child',
            'location':'Unconfigured studio','legacy_reviewed':True}],credits=[]))
        counts=(Category.objects.count(),Studio.objects.count())
        prepared=self.prepare(batch);self.commit(prepared.data['id'])
        movement=BankMovement.objects.get()
        self.assertEqual(movement.classification.description,'Keep this text')
        self.assertIsNone(movement.classification.category_id)
        self.assertFalse(movement.classification.reviewed)
        self.assertEqual((Category.objects.count(),Studio.objects.count()),counts)
        detail=self.client.get(f'/api/finance/bank-movements/{movement.pk}/').data
        self.assertEqual(detail['historical_source']['category'],'Unconfigured category')

    def test_historical_undo_preserves_original_workbook_and_has_no_double_post(self):
        batch=self.migration();prepared=self.prepare(batch);self.commit(prepared.data['id'])
        url=f"/api/finance/bank-imports/{prepared.data['id']}/"
        plan=self.client.get(url+'undo-preview/').data
        response=self.client.post(url+'undo/',{'expected_plan':plan['token'],'note':'Synthetic test reset'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(BankMovement.objects.filter(active=True).count(),0)
        self.assertEqual(MigrationImportBatch.objects.get(pk=batch).rows.count(),2)

    def test_copy_preview_requires_target_scope_and_preserves_original(self):
        from .models import Company
        batch=self.migration();source=MigrationImportBatch.objects.get(pk=batch)
        target=Company.objects.create(name='Configured target',site=self.site,default_currency='DOP')
        response=self.client.post(f'/api/finance/migration-imports/{batch}/copy-to-company/',{'company':target.pk},format='json')
        self.assertEqual(response.status_code,201,response.data)
        clone=MigrationImportBatch.objects.get(pk=response.data['id'])
        self.assertEqual(clone.company_id,target.pk)
        self.assertEqual(bytes(clone.original_file),bytes(source.original_file))
        self.assertEqual(clone.rows.count(),source.rows.count())
        self.assertEqual(source.company_id,self.company.pk)
        self.assertEqual(BankMovement.objects.count(),0)
        self.profile.can_import_finance=False;self.profile.save()
        self.assertEqual(self.client.post(f'/api/finance/migration-imports/{batch}/copy-to-company/',{'company':target.pk},format='json').status_code,403)

    def test_same_workbook_row_cannot_be_posted_twice_to_different_accounts(self):
        second=Account.objects.create(company=self.company,name='Other bank',currency='DOP')
        batch=self.migration();first=self.prepare(batch);another=self.prepare(batch,account=second.pk)
        stale=self.plan(another.data['id'])['token']
        self.commit(first.data['id'])
        self.assertEqual(self.prepare(batch,account=second.pk).status_code,400)
        response=self.client.post(f"/api/finance/bank-imports/{another.data['id']}/commit/",{'expected_plan':stale},format='json')
        self.assertEqual(response.status_code,409,response.data)
        self.assertEqual(self.plan(another.data['id'])['counts'],{'origin_conflict':2})
        self.commit(another.data['id'])
        self.assertEqual(BankMovement.objects.count(),2)
        self.assertEqual(BankMovement.objects.filter(account=second).count(),0)

    def test_optional_date_range_filters_rows_and_totals_without_changing_import_scope(self):
        batch=self.migration(workbook(credits=[{'bank_date':'2026-08-31','amount':10,'balance':100},
            {'bank_date':'2026-09-01','amount':15,'balance':115}]))
        response=self.client.get(f'/api/finance/migration-imports/{batch}/rows/',{'scope':'all','start':'2026-09-01','end':'2026-09-01','kind':'credit'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['count'],1)
        self.assertEqual(response.data['filtered_totals']['credit_total'],'15.00')
        self.assertEqual(len(self.client.get(f'/api/finance/migration-imports/{batch}/bank-candidates/').data['row_ids']),3)
        bad=self.client.get(f'/api/finance/migration-imports/{batch}/rows/',{'scope':'all','start':'2026-09-02','end':'2026-09-01'})
        self.assertEqual(bad.status_code,400)

    def test_reconciled_existing_record_is_linked_without_assignment_writes(self):
        normal=self.native();self.commit(normal)
        movement=BankMovement.objects.get();movement.reconciled=True;movement.save()
        batch=self.migration();prepared=self.prepare(batch);plan=self.plan(prepared.data['id'])
        self.assertEqual(plan['counts'].get('assignment_conflict'),1)
        self.commit(prepared.data['id'])
        movement.refresh_from_db()
        self.assertIsNone(movement.classification.operation_date)
        self.assertTrue(movement.reconciled)
