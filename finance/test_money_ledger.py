import uuid
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_migration_imports as fixtures
from .models import Account,Category,BankMovement,BankEvent,FinancialSale,FinancialReceipt,MigrationImportBatch
from .test_bank_imports import POPULAR


@override_settings(FINANCE_ENABLED=True)
class MoneyLedgerTests(APITestCase):
    upload=fixtures.MigrationAPITests.upload
    def setUp(self):
        fixtures.MigrationAPITests.setUp(self)
        self.profile.can_edit_finance=True;self.profile.can_manage_finance_settings=True;self.profile.save()
        self.cash=Account.objects.create(company=self.company,name='General cash QA',kind='cash',currency='DOP',statement_imports_expected=False)
        self.bank=Account.objects.create(company=self.company,name='Bank QA',currency='DOP')
        self.studio=Studio.objects.create(site=self.site,name='Studio QA')
        self.category=Category.objects.create(company=self.company,name='Services')
        self.sub=Category.objects.create(company=self.company,parent=self.category,name='Electricity')

    def payload(self,**updates):
        return {'account':self.cash.pk,'direction':'credit','date':'2026-09-01','amount':'100.00',
            'description':'Actual received cash','studio':self.studio.pk,'request_key':str(uuid.uuid4()),**updates}

    def create(self,**updates):
        body=self.payload(**updates);response=self.client.post('/api/finance/movements/',body,format='json')
        self.assertEqual(response.status_code,201,response.data);return BankMovement.objects.get(pk=response.data['id']),body

    def test_cash_income_is_independent_idempotent_and_genuine_equal_receipts_remain_separate(self):
        obj,body=self.create(reviewed=True)
        self.assertEqual(obj.classification.channel,'cash');self.assertIsNone(obj.source['balance'])
        self.assertIsNone(obj.created_from_id);self.assertEqual(FinancialSale.objects.count(),0);self.assertEqual(FinancialReceipt.objects.count(),0)
        repeat=self.client.post('/api/finance/movements/',body,format='json')
        self.assertEqual(repeat.status_code,200);self.assertTrue(repeat.data['reused']);self.assertEqual(BankMovement.objects.count(),1)
        conflict=self.client.post('/api/finance/movements/',{**body,'amount':'101.00'},format='json');self.assertEqual(conflict.status_code,409)
        self.create();self.assertEqual(BankMovement.objects.count(),2)
        rows=self.client.get(f'/api/finance/workspace/?company={self.company.pk}&kind=credit&origin=manual')
        self.assertEqual(rows.data['count'],2);self.assertEqual(rows.data['total'],'200.00');self.assertEqual(rows.data['results'][0]['origin'],'manual')
        history=self.client.get(f'/api/finance/movements/{obj.pk}/history/')
        self.assertEqual(history.status_code,200,history.data);self.assertEqual(history.data['results'][0]['action'],'manual_create')

    def test_expense_period_account_edit_and_void_are_audited_without_deletion(self):
        obj,body=self.create(direction='debit',expense_period='2026-08-01',category=self.category.pk,subcategory=self.sub.pk,reviewed=True)
        self.assertEqual(str(obj.classification.expense_period),'2026-08-01');self.assertTrue(obj.classification.reviewed)
        response=self.client.post(f'/api/finance/movements/{obj.pk}/edit-entry/',{**body,'account':self.bank.pk,'date':'2026-09-02','amount':'150.00','expected_revision':1},format='json')
        self.assertEqual(response.status_code,200,response.data);obj.refresh_from_db();self.assertEqual(obj.account_id,self.bank.pk);self.assertEqual(obj.source['amount'],'-150.00')
        audit=obj.events.get(action='manual_edit');self.assertEqual(audit.before['account'],self.cash.pk);self.assertEqual(audit.after['account'],self.bank.pk)
        stale=self.client.post(f'/api/finance/movements/{obj.pk}/edit-entry/',{**body,'expected_revision':1},format='json');self.assertEqual(stale.status_code,409)
        response=self.client.post(f'/api/finance/movements/{obj.pk}/void/',{'expected_revision':obj.revision,'note':'Synthetic test correction'},format='json')
        self.assertEqual(response.status_code,200,response.data);obj.refresh_from_db();self.assertFalse(obj.active);self.assertEqual(obj.classification.subcategory_id,self.sub.pk)
        rows=self.client.get(f'/api/finance/workspace/?company={self.company.pk}&kind=debit');self.assertEqual(rows.data['count'],0)
        self.assertTrue(BankEvent.objects.filter(movement=obj,action='manual_void').exists())

    def test_required_review_fields_invalid_cash_method_and_permissions(self):
        body=self.payload(direction='debit',reviewed=True)
        self.assertEqual(self.client.post('/api/finance/movements/',body,format='json').status_code,400)
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(self.client.post('/api/finance/movements/',self.payload(channel='transfer'),format='json').status_code,400)
        self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.client.post('/api/finance/movements/',self.payload(),format='json').status_code,403)
        self.profile.can_edit_finance=True;self.profile.save()
        other=Account.objects.create(company=self.spain,name='Other company cash',kind='cash',currency='EUR')
        self.assertEqual(self.client.post('/api/finance/movements/',self.payload(account=other.pk),format='json').status_code,400)

    def test_general_cash_is_idempotent_unverified_and_configured_through_settings_permission(self):
        url=f'/api/finance/companies/{self.company.pk}/general-cash/'
        first=self.client.post(url,{},format='json');self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(self.client.post(url,{},format='json').data['id'],first.data['id'])
        self.assertIsNone(first.data['opening_balance']);self.assertIsNone(first.data['opening_balance_date']);self.assertFalse(first.data['statement_imports_expected'])
        self.profile.can_manage_finance_settings=False;self.profile.save();self.assertEqual(self.client.post(url,{},format='json').status_code,403)

    def cash_workbook(self,amount=40,description='Actual cash'):
        return fixtures.workbook(credits=[{'bank_date':'2026-09-01','operation_date':'2026-09-01','amount':amount,'payment_method':'Efectivo','manual_description':description,'balance':12345,'location':'Studio QA'},
            {'bank_date':'2026-09-01','operation_date':'2026-09-01','amount':amount,'payment_method':'Efectivo','manual_description':description,'location':'Studio QA'}])

    def cash_plan(self,batch,account=None):
        response=self.client.get(f'/api/finance/migration-imports/{batch}/cash-preview/?account={account or self.cash.pk}')
        self.assertEqual(response.status_code,200,response.data);return response.data

    def import_cash(self,batch,token=None):
        return self.client.post(f'/api/finance/migration-imports/{batch}/import-cash/',{'account':self.cash.pk,'expected_plan':token or self.cash_plan(batch)['token']},format='json')

    def test_cash_migration_preserves_individual_rows_and_does_not_post_expenses_or_sales(self):
        content=self.cash_workbook();batch=self.upload(content).data['id'];plan=self.cash_plan(batch)
        self.assertEqual(plan['new'],2);self.assertEqual(plan['new_total'],'80.00');self.assertFalse(BankMovement.objects.exists())
        result=self.import_cash(batch);self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['created'],2)
        self.assertEqual(set(BankMovement.objects.values_list('account_id',flat=True)),{self.cash.pk})
        self.assertFalse(BankMovement.objects.filter(source__direction='debit').exists())
        for movement in BankMovement.objects.all():
            self.assertIsNone(movement.source['balance']);self.assertEqual(movement.classification.channel,'cash');self.assertEqual(movement.classification.studio_id,self.studio.pk)
            self.assertEqual(self.client.get(f'/api/finance/movements/{movement.pk}/').data['origin'],'migration')
        self.assertEqual(self.import_cash(batch,token=plan['token']).status_code,409)
        self.assertEqual(self.import_cash(batch).data['created'],0)
        repeat=self.upload(content).data['id'];self.assertEqual(self.cash_plan(repeat)['already_imported'],2)
        self.assertEqual(self.import_cash(repeat).data['created'],0)
        self.assertEqual(BankMovement.objects.count(),2);self.assertFalse(FinancialSale.objects.exists());self.assertFalse(FinancialReceipt.objects.exists())
        rows=self.client.get(f'/api/finance/workspace/?company={self.company.pk}&kind=credit&origin=migration');self.assertEqual(rows.data['count'],2)

    def test_cash_migration_ambiguous_other_sources_and_invalid_dates_stay_pending(self):
        self.create(amount='40.00')
        batch=self.upload(self.cash_workbook()).data['id'];plan=self.cash_plan(batch)
        self.assertEqual(plan['pending'],2);self.assertEqual(plan['new'],0)
        self.assertEqual(self.import_cash(batch).data['created'],0)
        self.assertEqual(BankMovement.objects.count(),1)
        bad=self.upload(fixtures.workbook(credits=[{'bank_date':'invalid','amount':40,'payment_method':'Efectivo'}])).data['id']
        self.assertEqual(self.cash_plan(bad)['rows'][0]['status'],'invalid')
        self.assertEqual(self.client.get(f'/api/finance/migration-imports/{batch}/cash-preview/?account={self.bank.pk}').status_code,404)
        self.profile.can_import_finance=False;self.profile.save();self.assertEqual(self.import_cash(batch).status_code,403)

    def test_imported_cash_facts_protected_but_classification_edit_works(self):
        batch=self.upload(self.cash_workbook()).data['id'];self.import_cash(batch);obj=BankMovement.objects.first()
        change=self.client.post(f'/api/finance/movements/{obj.pk}/assign/',{'expected_revision':obj.revision,'description':'Reviewed actual cash'},format='json')
        self.assertEqual(change.status_code,200,change.data)
        obj.refresh_from_db();response=self.client.post(f'/api/finance/movements/{obj.pk}/edit-entry/',self.payload(expected_revision=obj.revision),format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post(f'/api/finance/movements/{obj.pk}/void/',{'expected_revision':obj.revision,'note':'No'},format='json').status_code,400)

    def test_studio_cash_migration_cannot_absorb_other_studios_and_account_type_is_protected(self):
        other_studio=Studio.objects.create(site=self.site,name='Other studio')
        self.cash.studios.add(other_studio)
        batch=self.upload(self.cash_workbook()).data['id'];plan=self.cash_plan(batch)
        self.assertEqual(plan['new'],0);self.assertEqual(plan['pending'],2)
        self.assertTrue(all(row['status']=='account_scope_review' for row in plan['rows']))
        self.assertEqual(self.client.post('/api/finance/movements/',self.payload(studio=self.studio.pk),format='json').status_code,400)
        self.cash.studios.clear();self.create()
        changed=self.client.patch(f'/api/finance/accounts/{self.cash.pk}/',{'kind':'bank','expected_revision':self.cash.revision},format='json')
        self.assertEqual(changed.status_code,400)

    def test_manual_bank_overlap_is_reviewed_not_duplicated_and_linked_entries_lock_facts(self):
        text=POPULAR.replace('01/09/2026,Crédito Transferencia,100.00,200.00,,123,Card deposit\n','',1)
        native=self.client.post('/api/finance/bank-imports/',{'account':self.bank.pk,'provider':'popular','file':SimpleUploadedFile('bank.csv',text.encode())},format='multipart')
        self.assertEqual(native.status_code,201,native.data);batch=native.data['id']
        from .models import BankImportRow,BankDecision
        source=BankImportRow.objects.filter(batch_id=batch,kind='data',parsed__direction='credit').first().parsed
        obj,_=self.create(account=self.bank.pk,date=source['bank_date'],amount=source['amount'],channel='transfer')
        plan=self.client.get(f'/api/finance/bank-imports/{batch}/processing/').data
        self.assertTrue(any(r['outcome']!='new' and any(c['id']==obj.pk for c in r['candidates']) for r in plan['rows']['results']))
        result=self.client.post(f'/api/finance/bank-imports/{batch}/commit/',{'expected_plan':plan['token']},format='json');self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(BankMovement.objects.filter(source__bank_date=source['bank_date'],source__amount=source['amount']).count(),1)
        decision=BankDecision.objects.get(posting__batch_id=batch,row__parsed__direction='credit')
        current=self.client.get(f'/api/finance/bank-imports/{batch}/processing/').data
        resolved=self.client.post(f'/api/finance/bank-imports/{batch}/resolve/',{'expected_plan':current['token'],
            'decision_id':decision.pk,'expected_revision':decision.revision,'action':'link','movement_id':obj.pk,
            'expected_movement_revision':obj.revision,'note':'Confirmed manual bank entry'},format='json')
        self.assertEqual(resolved.status_code,200,resolved.data)
        self.assertFalse(self.client.get(f'/api/finance/movements/{obj.pk}/').data['can_edit_facts'])
        self.assertEqual(self.client.post(f'/api/finance/movements/{obj.pk}/void/',{'expected_revision':obj.revision,'note':'Blocked'},format='json').status_code,400)
        repeated=self.client.post('/api/finance/bank-imports/',{'account':self.bank.pk,'provider':'popular','file':SimpleUploadedFile('repeat.csv',text.encode())},format='multipart')
        repeated_plan=self.client.get(f"/api/finance/bank-imports/{repeated.data['id']}/processing/").data
        self.assertEqual(repeated_plan['counts'],{'unchanged':2})
