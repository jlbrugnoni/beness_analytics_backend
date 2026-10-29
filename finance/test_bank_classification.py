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

    def test_optional_comment_preserves_classification_audit(self):
        self.records()
        for comment in ({}, {'note': ''}):
            self.debit.refresh_from_db()
            revision=self.debit.revision
            response=self.client.post(f'/api/finance/bank-movements/{self.debit.pk}/assign/',
                {'expected_revision':revision,'description':f'Revision {revision}',**comment},format='json')
            self.assertEqual(response.status_code,200,response.data)
            event=BankEvent.objects.filter(action='classify').latest('pk')
            self.assertEqual(event.actor,self.user)
            self.assertIsNotNone(event.created_at)
            self.assertEqual(event.note,'')
            self.assertEqual(event.after['classification']['description'],f'Revision {revision}')
            if revision > 1:
                self.assertEqual(event.before['classification']['description'],f'Revision {revision-1}')
            self.debit.refresh_from_db()
            self.assertEqual(self.debit.revision,revision+1)
        response=self.client.post(f'/api/finance/bank-movements/{self.debit.pk}/assign/',
            {'expected_revision':self.debit.revision},format='json')
        self.assertEqual(response.status_code,400)

    def test_source_review_and_undo_still_require_reason(self):
        self.records()
        for action,payload in [('resolve',{'decision_id':1,'expected_revision':1,'action':'ignore'}),('undo',{})]:
            for comment in ({},{'note':''}):
                response=self.client.post(f'/api/finance/bank-imports/{self.batch}/{action}/',
                    {'expected_plan':'a'*64,**payload,**comment},format='json')
                self.assertEqual(response.status_code,400)
                self.assertIn('note',response.data)

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
        self.assertEqual(event.before['classification']['movement_kind'],'expense');self.assertEqual(event.after['classification']['expense_period'],'2026-08-01')
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

    def test_incomplete_work_can_save_but_cannot_be_reviewed(self):
        self.records();response=self.assign(self.debit,reviewed=True)
        self.assertEqual(response.status_code,400)
        self.assertIn('category',response.data);self.assertIn('studio',response.data)
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())
        response=self.assign(self.debit,movement_kind='expense')
        self.assertEqual(response.status_code,200);self.assertTrue(response.data['needs_review'])
        self.assertFalse(response.data['classification']['reviewed'])
        self.assertIn('category',response.data['missing_fields'])
        url='/api/finance/workspace/'
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'reviewed'}).data['count'],0)
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'debit','status':'unreviewed'}).data['count'],1)

    def test_review_lock_requires_reopen_before_removing_required_data(self):
        self.records()
        response=self.assign(self.credit,movement_kind='customer_receipt',studio=self.studio.pk,
            channel='cash',operation_date='2026-09-01',reviewed=True)
        self.assertEqual(response.status_code,200,response.data)
        self.credit.refresh_from_db()
        self.assertEqual(self.assign(self.credit,operation_date=None).status_code,400)
        self.profile.can_reopen_finance=True;self.profile.save()
        self.assertEqual(self.client.post(f'/api/finance/movements/{self.credit.pk}/reopen/',{'expected_revision':self.credit.revision},format='json').status_code,200)
        self.credit.refresh_from_db()
        response=self.assign(self.credit,operation_date=None)
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data['classification']['reviewed'])
        self.assertIn('operation_date',response.data['missing_fields'])
        self.assertEqual(self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'credit','status':'unreviewed'}).data['count'],1)

    def test_legacy_incomplete_review_flag_is_presented_and_filtered_as_pending(self):
        self.records()
        BankMovementClassification.objects.update_or_create(movement=self.debit,defaults={'movement_kind':'','reviewed':True})
        response=self.client.get(f'/api/finance/bank-movements/{self.debit.pk}/')
        self.assertFalse(response.data['classification']['reviewed'])
        for status,count in [('reviewed',0),('unreviewed',1),('review',1)]:
            result=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'debit','status':status})
            self.assertEqual(result.data['count'],count)

    def test_credit_terminal_scope_and_operation_date(self):
        self.records();terminal=Terminal.objects.create(account=self.account,identifier='QA-TERMINAL',studio=self.studio,channel='card_terminal')
        response=self.assign(self.credit,terminal=terminal.pk,channel='cash',studio=self.studio.pk)
        self.assertEqual(response.status_code,400)
        response=self.assign(self.credit,terminal=terminal.pk,channel='card_terminal',studio=self.studio.pk,operation_date='2026-08-30',movement_kind='customer_receipt',reviewed=True)
        self.assertEqual(response.status_code,200,response.data);self.assertFalse(response.data['needs_review'])
        other=Terminal.objects.create(account=self.foreign,identifier='OTHER',studio=Studio.objects.create(site=self.es,name='Foreign studio'),channel='card_terminal')
        self.credit.refresh_from_db();self.assertEqual(self.assign(self.credit,terminal=other.pk).status_code,400)
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
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.revision,1)
        self.assertFalse(BankEvent.objects.filter(action='classify').exists())
        self.assertIsNone(self.debit.classification.category_id)
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())

    def test_permissions_stale_and_reconciled_guard(self):
        self.records();self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.assign(self.debit,reviewed=True).status_code,403)
        self.profile.can_edit_finance=True;self.profile.save()
        self.assertEqual(self.assign(self.debit,movement_kind='internal_transfer',reviewed=True).status_code,200)
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


@override_settings(FINANCE_ENABLED=True)
class BankTerminalRecognitionTests(APITestCase):
    setUp=BankClassificationTests.setUp
    upload=BankClassificationTests.upload
    preview=BankClassificationTests.preview
    processing=BankClassificationTests.processing
    commit=BankClassificationTests.commit
    post=BankClassificationTests.post
    records=BankClassificationTests.records
    assign=BankClassificationTests.assign

    def terminal_setup(self,identifier='39618800002',**fields):
        self.studio=Studio.objects.create(site=self.site,name='Recognized studio')
        return Terminal.objects.create(account=self.account,identifier=identifier,studio=self.studio,
            channel=fields.pop('channel','card_terminal'),**fields)

    def test_new_import_recognizes_exact_terminal_without_changing_source_or_review(self):
        terminal=self.terminal_setup()
        self.post(fixtures.BASE.replace('Card deposit',terminal.identifier+' - AZUL CR RD$ .00'))
        movement=BankMovement.objects.get(source__direction='credit')
        response=self.client.get(f'/api/finance/bank-movements/{movement.pk}/')
        values=response.data['classification']
        self.assertEqual(values['terminal'],terminal.pk)
        self.assertEqual(values['studio'],terminal.studio_id)
        self.assertEqual(values['channel'],'card_terminal')
        self.assertFalse(values['reviewed']);self.assertFalse(response.data['reconciled'])
        self.assertIsNone(values['operation_date']);self.assertEqual(values['movement_kind'],'customer_receipt')
        self.assertEqual(movement.revision,1)
        event=movement.events.get(action='create')
        self.assertEqual(event.after['classification']['terminal'],terminal.pk)
        self.assertIn(terminal.identifier,movement.source['description'])
        self.assertEqual(BankMovementClassification.objects.get(movement__source__direction='debit').movement_kind,'expense')
        # Repeated overlapping imports keep one movement and the classification.
        self.post(fixtures.BASE.replace('Card deposit',terminal.identifier+' - AZUL CR RD$ .00'))
        self.assertEqual(BankMovement.objects.count(),2)

    def test_unknown_partial_inactive_and_ambiguous_matches_stay_unassigned(self):
        terminal=self.terminal_setup()
        from .bank_classification import recognize_terminal
        self.records()
        for description in ['X'+terminal.identifier,terminal.identifier+'9','Unknown terminal']:
            self.credit.source['description']=description
            self.assertFalse(recognize_terminal(self.credit,self.user))
        second=Terminal.objects.create(account=self.account,identifier='39618800004',studio=terminal.studio,channel='recurring')
        self.credit.source['description']=terminal.identifier+' '+second.identifier
        self.assertFalse(recognize_terminal(self.credit,self.user))
        terminal.active=False;terminal.save()
        self.credit.source['description']=terminal.identifier
        self.assertFalse(recognize_terminal(self.credit,self.user))
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())

    def test_existing_credits_can_be_recognized_with_audit_and_are_idempotent(self):
        self.post(fixtures.BASE.replace('Card deposit','39618800002 - AZUL CR RD$ .00'))
        terminal=self.terminal_setup()
        url='/api/finance/workspace/recognize-terminals/'
        response=self.client.post(url,{'company':self.company.pk},format='json')
        self.assertEqual(response.status_code,200,response.data);self.assertEqual(response.data['updated'],1)
        movement=BankMovement.objects.get(source__direction='credit')
        self.assertEqual(movement.revision,2)
        audit=movement.events.get(action='classify')
        self.assertEqual(audit.before['classification']['movement_kind'],'customer_receipt')
        self.assertEqual(audit.actor,self.user)
        self.assertEqual(audit.after['classification']['terminal'],terminal.pk)
        self.assertEqual(self.client.post(url,{'company':self.company.pk},format='json').data['updated'],0)
        filtered=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'credit','studio':terminal.studio_id,'channel':'card_terminal'})
        self.assertEqual(filtered.data['count'],1)

    def test_preserves_manual_conflicts_reviewed_reconciled_and_nonreceipt_kinds(self):
        from .bank_classification import recognize_terminal
        self.records();terminal=self.terminal_setup()
        self.credit.source['description']=terminal.identifier
        for values in [{'channel':'cash'},{'reviewed':True},{'administration':True},{'movement_kind':'internal_transfer'}]:
            BankMovementClassification.objects.update_or_create(movement=self.credit,defaults={
                'channel':'','reviewed':False,'administration':False,'movement_kind':'',**values})
            self.credit=BankMovement.objects.get(pk=self.credit.pk)
            self.assertFalse(recognize_terminal(self.credit,self.user))
        self.credit.reconciled=True
        self.assertFalse(recognize_terminal(self.credit,self.user))

    def test_recognition_scopes_account_and_user_permissions(self):
        self.post(fixtures.BASE.replace('Card deposit','39618800002'))
        terminal=self.terminal_setup()
        self.profile.can_edit_finance=False;self.profile.save()
        url='/api/finance/workspace/recognize-terminals/'
        response=self.client.post(url,{'company':self.company.pk},format='json')
        self.assertEqual(response.status_code,403)
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())
        self.profile.can_edit_finance=True;self.profile.save()
        self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.client.post(url,{'company':self.company.pk},format='json').status_code,403)
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())

    def test_credit_categories_rejected_and_options_are_debit_only(self):
        self.records()
        self.assertEqual(self.assign(self.credit,category=self.category.pk).status_code,400)
        self.assertEqual(self.assign(self.credit,subcategory=self.subcategory.pk).status_code,400)
        self.assertEqual(self.client.get(f'/api/finance/bank-movements/{self.credit.pk}/options/').data['categories'],[])
        self.assertEqual(self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'credit','status':'missing_category'}).status_code,400)
        self.assertEqual(self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'credit','category':self.category.pk}).status_code,400)

    def test_caixa_recognition_uses_account_mapping_and_keeps_operation_date_pending(self):
        from .test_bank_imports import CAIXA
        studio=Studio.objects.create(site=self.es,name='Estepona fixture')
        terminal=Terminal.objects.create(account=self.foreign,identifier='369092994',studio=studio,channel='card_terminal')
        self.profile.allowed_sites.add(self.es)
        self.post(CAIXA,account=self.foreign.pk,provider='caixa')
        movement=BankMovement.objects.get(account=self.foreign,source__direction='credit')
        self.assertEqual(movement.classification.terminal_id,terminal.pk)
        self.assertEqual(movement.classification.studio_id,studio.pk)
        self.assertIsNone(movement.classification.operation_date)

    def test_terminal_from_another_account_is_never_used(self):
        studio=Studio.objects.create(site=self.es,name='Other company studio')
        Terminal.objects.create(account=self.foreign,identifier='39618800002',studio=studio,channel='card_terminal')
        self.post(fixtures.BASE.replace('Card deposit','39618800002 - AZUL CR RD$ .00'))
        self.assertFalse(BankMovementClassification.objects.filter(terminal__isnull=False).exists())

    def test_direction_specific_types_and_defaults(self):
        self.records()
        for movement,expected,default in [(self.debit,['expense','internal_transfer','refund'],'expense'),
                (self.credit,['customer_receipt','internal_transfer','refund','extraordinary'],'customer_receipt')]:
            response=self.client.get(f'/api/finance/bank-movements/{movement.pk}/options/')
            self.assertEqual([kind['value'] for kind in response.data['kinds']],expected)
            self.assertEqual(movement.classification.movement_kind,default)
        self.assertEqual(self.assign(self.debit,movement_kind='extraordinary').status_code,400)
        self.assertEqual(self.assign(self.debit,movement_kind='fee').status_code,400)
        self.assertEqual(self.assign(self.credit,movement_kind='fee_reimbursement').status_code,400)

    def test_legacy_kinds_are_normalized_without_rewriting_history(self):
        self.records()
        for movement,legacy,current in [(self.debit,'fee','expense'),(self.debit,'extraordinary','expense'),
                (self.credit,'fee_reimbursement','refund')]:
            BankMovementClassification.objects.filter(movement=movement).update(movement_kind=legacy)
            response=self.client.get(f'/api/finance/bank-movements/{movement.pk}/')
            self.assertEqual(response.data['classification']['movement_kind'],current)
            movement.refresh_from_db()
            self.assertEqual(movement.classification.movement_kind,legacy)
            result=self.assign(movement,description='Keep legacy history')
            self.assertEqual(result.status_code,200,result.data)
            event=BankEvent.objects.filter(movement=movement,action='classify').latest('pk')
            self.assertEqual(event.before['classification']['movement_kind'],legacy)
            self.assertEqual(event.after['classification']['movement_kind'],current)

    def test_missing_classification_uses_direction_default_without_get_writes(self):
        self.records()
        self.credit.classification.delete()
        response=self.client.get(f'/api/finance/bank-movements/{self.credit.pk}/')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['classification']['movement_kind'],'customer_receipt')
        self.assertFalse(BankMovementClassification.objects.filter(movement=self.credit).exists())

    def test_debit_refund_needs_no_expense_category_or_expense_month(self):
        self.records()
        result=self.assign(self.debit,movement_kind='refund',studio=self.studio.pk,reviewed=True)
        self.assertEqual(result.status_code,200,result.data)
        self.assertFalse(result.data['needs_review'])
        query=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'debit','status':'missing_category'})
        self.assertEqual(query.data['count'],0)
