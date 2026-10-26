from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_bank_posting as fixtures
from .models import BankMovement, BankMovementClassification, BankEvent, Category, Terminal


@override_settings(FINANCE_ENABLED=True)
class BankClassificationTests(APITestCase):
    setUp=fixtures.BankPostingTests.setUp
    upload=fixtures.BankPostingTests.upload
    preview=fixtures.BankPostingTests.preview
    processing=fixtures.BankPostingTests.processing
    commit=fixtures.BankPostingTests.commit
    post=fixtures.BankPostingTests.post

    def records(self):
        self.batch=self.post()
        self.debit=BankMovement.objects.get(source__direction='debit')
        self.credit=BankMovement.objects.get(source__direction='credit')
        self.studio=Studio.objects.create(site=self.site,name='Bank studio')
        self.category=Category.objects.create(company=self.company,name='Services')
        self.subcategory=Category.objects.create(company=self.company,parent=self.category,name='Electricity')

    def assign(self,obj,**values):
        return self.client.post(f'/api/finance/bank-movements/{obj.pk}/assign/',
            {'expected_revision':obj.revision,'note':'Synthetic review',**values},format='json')

    def test_expense_assignment_preserves_source_and_records_audit(self):
        self.records();source=dict(self.debit.source)
        response=self.assign(self.debit,description='August electricity',category=self.category.pk,subcategory=self.subcategory.pk,
            expense_period='2026-08-01',studio=self.studio.pk,channel='transfer',movement_kind='expense',reviewed=True)
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data['needs_review']);self.assertFalse(response.data['reconciled'])
        self.assertEqual(response.data['classification_labels']['subcategory_name'],'Electricity')
        review=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'debit','status':'review'})
        self.assertEqual(review.data['count'],0)
        self.debit.refresh_from_db();self.assertEqual(self.debit.source,source);self.assertEqual(self.debit.revision,2)
        event=BankEvent.objects.get(action='classify');self.assertEqual(event.actor,self.user)
        self.assertEqual(event.before['classification'],{});self.assertEqual(event.after['classification']['expense_period'],'2026-08-01')
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/').data['classification']['description'],'August electricity')

    def test_overlap_and_explicit_source_correction_keep_assignments_and_protect_undo(self):
        self.records();self.assertEqual(self.assign(self.debit,description='Keep manual',movement_kind='expense').status_code,200)
        repeated=self.post();self.assertEqual(BankMovement.objects.count(),2)
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/').data['classification']['description'],'Keep manual')
        # Source changes use the existing review service, not the classification editor.
        changed=self.preview(fixtures.BASE.replace('Expense','Corrected expense'))
        self.assertEqual(self.commit(changed).status_code,200)
        plan=self.processing(changed);row=next(r for r in plan['rows']['results'] if r['source']['direction']=='debit')
        self.debit.refresh_from_db()
        response=self.client.post(f'/api/finance/bank-imports/{changed}/resolve/',{'expected_plan':plan['token'],
            'decision_id':row['decision_id'],'expected_revision':row['revision'],'action':'correct','note':'Correct bank source',
            'movement_id':self.debit.pk,'expected_movement_revision':self.debit.revision},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/').data['classification']['description'],'Keep manual')
        undo=self.client.get(f'/api/finance/bank-imports/{self.batch}/undo-preview/')
        self.assertTrue(any(r['movement_id']==self.debit.pk for r in undo.data['protected']))

    def test_incomplete_review_is_saved_but_not_falsely_complete_or_reconciled(self):
        self.records();response=self.assign(self.debit,reviewed=True)
        self.assertEqual(response.status_code,200);self.assertTrue(response.data['needs_review']);self.assertFalse(response.data['reconciled'])
        url='/api/finance/workspace/'
        result=self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'reviewed'})
        self.assertEqual(result.data['count'],1)
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'review'}).data['count'],1)
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'reconciled'}).data['count'],0)
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'missing_category'}).data['count'],1)

    def test_credit_terminal_scope_and_operation_date(self):
        self.records();terminal=Terminal.objects.create(account=self.account,identifier='QA-TERMINAL',studio=self.studio,channel='card_terminal')
        response=self.assign(self.credit,terminal=terminal.pk,channel='cash',studio=self.studio.pk)
        self.assertEqual(response.status_code,400)
        response=self.assign(self.credit,terminal=terminal.pk,channel='card_terminal',studio=self.studio.pk,operation_date='2026-08-30',movement_kind='customer_receipt',reviewed=True)
        self.assertEqual(response.status_code,200,response.data);self.assertFalse(response.data['needs_review'])
        other=Terminal.objects.create(account=self.foreign,identifier='OTHER',studio=Studio.objects.create(site=self.es,name='Foreign studio'),channel='card_terminal')
        self.credit.refresh_from_db();self.assertEqual(self.assign(self.credit,terminal=other.pk).status_code,404)
        self.assertEqual(self.assign(self.credit,expense_period='2026-08-01').status_code,400)
        self.assertEqual(self.assign(self.debit,operation_date='2026-08-30').status_code,400)

    def test_source_facts_hierarchy_direction_and_studio_validation(self):
        self.records()
        for key,value in [('source',{}),('amount','1.00'),('bank_date','2026-01-01'),('reconciled',True)]:
            self.assertEqual(self.assign(self.debit,**{key:value}).status_code,400)
        other=Category.objects.create(company=self.company,name='Other')
        self.assertEqual(self.assign(self.debit,category=other.pk,subcategory=self.subcategory.pk).status_code,400)
        self.assertEqual(self.assign(self.debit,category=self.subcategory.pk).status_code,400)
        self.assertEqual(self.assign(self.debit,expense_period='2026-08-15').status_code,400)
        self.assertEqual(self.assign(self.credit,movement_kind='expense').status_code,400)
        self.assertEqual(self.assign(self.debit,movement_kind='customer_receipt').status_code,400)
        foreign=Studio.objects.create(site=self.es,name='Other')
        self.assertEqual(self.assign(self.debit,studio=foreign.pk).status_code,400)
        self.assertEqual(self.assign(self.debit,studio=self.studio.pk,administration=True).status_code,400)
        self.assertFalse(BankMovementClassification.objects.exists())

    def test_permissions_stale_and_reconciled_guard(self):
        self.records();self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.assign(self.debit,reviewed=True).status_code,403)
        self.profile.can_edit_finance=True;self.profile.save()
        self.assertEqual(self.assign(self.debit,reviewed=True).status_code,200)
        self.assertEqual(self.assign(self.debit,reviewed=False).status_code,409)
        self.debit.refresh_from_db();self.debit.reconciled=True;self.debit.save()
        self.assertEqual(self.assign(self.debit,reviewed=False).status_code,400)
        self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/options/').status_code,403)

    def test_filters_use_manual_fields_and_do_not_require_configuration_permission(self):
        self.records();response=self.assign(self.debit,description='Manual searchable text',category=self.category.pk,subcategory=self.subcategory.pk,studio=self.studio.pk,channel='transfer')
        self.assertEqual(response.status_code,200)
        result=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'debit','search':'searchable','category':self.category.pk,'subcategory':self.subcategory.pk,'studio':self.studio.pk,'channel':'transfer'})
        self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['count'],1);self.assertEqual(result.data['total'],'-20.00')
        self.assertEqual(result.data['results'][0]['classification']['description'],'Manual searchable text')
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/options/').status_code,200)
        self.assertFalse(self.profile.can_manage_finance_settings)

    def test_internal_movement_and_administration_are_assignments_only(self):
        self.records();response=self.assign(self.debit,movement_kind='internal_transfer',reviewed=True)
        self.assertEqual(response.status_code,200);self.assertFalse(response.data['needs_review'])
        response=self.assign(self.credit,administration=True,movement_kind='extraordinary',reviewed=True)
        self.assertEqual(response.status_code,200);self.assertFalse(response.data['needs_review'])
        self.assertEqual(BankMovement.objects.count(),2)

    def test_partial_studio_grant_cannot_assign_other_studios_or_administration(self):
        self.records();self.account.studios.add(self.studio);self.profile.allowed_studios.add(self.studio)
        outside=Studio.objects.create(site=self.site,name='Outside assigned studio')
        choices=self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/options/')
        self.assertEqual(choices.status_code,200)
        self.assertEqual([s['id'] for s in choices.data['studios']],[self.studio.pk])
        self.assertEqual(self.assign(self.debit,studio=outside.pk).status_code,400)
        self.assertEqual(self.assign(self.debit,administration=True).status_code,403)
        self.assertEqual(self.assign(self.debit,studio=self.studio.pk).status_code,200)
