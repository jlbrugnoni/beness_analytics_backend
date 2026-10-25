from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .models import Company, FinancialSale, SalesPosting, SalesDecision, SalesEvent, SourceMapping, BankMovement
from .test_sales_imports import report
from django.core.files.uploadedfile import SimpleUploadedFile


@override_settings(FINANCE_ENABLED=True)
class SalesPostingTests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('sales-posting@example.test')
        self.profile=get_or_create_user_access_profile(self.user)
        for key in ('can_view_money','can_view_finance','can_import_finance','can_edit_finance','can_view_sensitive_finance'):
            setattr(self.profile,key,True)
        self.profile.save()
        self.site=Site.objects.create(name='Sales Posting DO',country_code='DO')
        self.company=Company.objects.create(name='Sales Posting QA',site=self.site,default_currency='DOP')
        self.studio=Studio.objects.create(name='Studio QA',site=self.site)
        self.other=Studio.objects.create(name='Other Studio QA',site=self.site)
        self.profile.allowed_sites.add(self.site)
        self.client.force_authenticate(self.user)
        SourceMapping.objects.create(company=self.company,source_field='alegra_cost_center',source_value='Studio QA',normalized_value='studio qa',studio=self.studio)
        SourceMapping.objects.create(company=self.company,source_field='alegra_payment_method',source_value='Tarjeta crédito',normalized_value='tarjeta crédito',channel='card_terminal',requires_review=True)

    def upload(self,rows=None):
        response=self.client.post('/api/finance/sales-imports/',{'company':self.company.pk,'file':SimpleUploadedFile('synthetic.csv',report(rows))},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']

    def url(self,batch,suffix):return f'/api/finance/sales-imports/{batch}/{suffix}/'
    def plan(self,batch):
        response=self.client.get(self.url(batch,'processing'));self.assertEqual(response.status_code,200,response.data);return response.data
    def commit(self,batch,token=None):
        return self.client.post(self.url(batch,'commit'),{'expected_plan':token or self.plan(batch)['token']},format='json')
    def resolve(self,batch,action='cancel'):
        plan=self.plan(batch);row=plan['rows']['results'][0]
        return self.client.post(self.url(batch,'resolve'),{'expected_plan':plan['token'],'decision_id':row['decision_id'],'expected_revision':row['decision_revision'],'action':action,'note':'Synthetic decision'},format='json')
    def assign(self,sale,**values):
        sale.refresh_from_db()
        return self.client.post(f'/api/finance/sales/{sale.pk}/assign/',{'expected_revision':sale.revision,'note':'Synthetic assignment',**values},format='json')
    def undo(self,batch):
        preview=self.client.get(self.url(batch,'undo-preview'));self.assertEqual(preview.status_code,200,preview.data)
        return self.client.post(self.url(batch,'undo'),{'expected_plan':preview.data['token'],'note':'Synthetic undo'},format='json')

    def test_commit_overlap_reordered_items_and_retries_count_once(self):
        rows=[{'invoice_total':'300.00','item_name':'Item A'}, {'invoice_total':'300.00','item_name':'Item A'}, {'invoice_total':'300.00','item_name':'Item B'}]
        first=self.upload(rows);self.assertEqual(self.commit(first).status_code,200)
        self.assertEqual(self.commit(first).status_code,200)
        second=self.upload(list(reversed(rows)));self.assertEqual(self.plan(second)['counts'],{'unchanged':1})
        self.assertEqual(self.commit(second).status_code,200)
        sale=FinancialSale.objects.get();self.assertEqual(len(sale.items),3);self.assertEqual(sale.source['invoice_total'],'300.00')
        self.assertEqual(sale.studio_id,self.studio.pk);self.assertTrue(sale.assignments['requires_review'])
        self.assertEqual(SalesPosting.objects.count(),2)

    def test_cancellation_requires_approval_preserves_facts_and_no_bank_refund(self):
        first=self.upload();self.commit(first);sale=FinancialSale.objects.get()
        cancelled=self.upload([{'status':'Anulada'}]);self.assertEqual(self.plan(cancelled)['counts'],{'cancellation':1});self.commit(cancelled)
        sale.refresh_from_db();self.assertEqual(sale.source['status_kind'],'paid')
        self.assertEqual(self.resolve(cancelled).status_code,200)
        sale.refresh_from_db();self.assertEqual(sale.source['status_kind'],'cancelled');self.assertEqual(sale.source['date'],'2026-09-01')
        self.assertEqual(sale.source['invoice_total'],'100.00');self.assertEqual(sale.cancellation_treatment,'pending')
        detail=self.client.get(f'/api/finance/sales/{sale.pk}/');self.assertEqual(detail.data['contribution'],'0.00')
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(SalesEvent.objects.filter(action='cancel').count(),1)
        self.assertEqual(self.resolve(cancelled).status_code,409)

    def test_old_paid_file_does_not_reactivate_cancelled_invoice(self):
        first=self.upload();self.commit(first)
        cancelled=self.upload([{'status':'Anulada'}]);self.commit(cancelled);self.resolve(cancelled)
        old=self.upload();self.assertEqual(self.plan(old)['counts'],{'stale_paid':1});self.commit(old)
        self.assertEqual(self.resolve(old).status_code,400)
        self.assertEqual(self.resolve(old,'retain').status_code,200)
        self.assertEqual(FinancialSale.objects.get().source['status_kind'],'cancelled')

    def test_new_cancelled_invoice_is_evidence_not_paid_income(self):
        batch=self.upload([{'status':'Anulada'}]);self.commit(batch)
        sale=FinancialSale.objects.get();self.assertEqual(sale.source['status_kind'],'cancelled')
        self.assertEqual(self.client.get(f'/api/finance/sales/{sale.pk}/').data['contribution'],'0.00')

    def test_v1_cancelled_preview_interpretation_does_not_rewrite_source(self):
        batch=self.upload([{'status':'Anulada'}])
        from .models import SalesImportBatch
        source=SalesImportBatch.objects.get(pk=batch);source.parser_version='alegra-items-v1';source.summary={'paid_total':'0.00'};source.save()
        invoice=source.invoices.get();invoice.issues=['status_requires_review'];invoice.source['status_kind']='review';invoice.save()
        self.assertEqual(self.plan(batch)['counts'],{'new':1});self.commit(batch)
        source.refresh_from_db();invoice.refresh_from_db()
        self.assertEqual(source.summary,{'paid_total':'0.00'});self.assertEqual(invoice.issues,['status_requires_review'])
        self.assertEqual(FinancialSale.objects.get().source['status_kind'],'cancelled')

    def test_changed_immutable_facts_or_items_stay_pending_independent_new_continues(self):
        first=self.upload();self.commit(first)
        for fields in ({'date':'02/09/2026'},{'customer':'Different synthetic client'},{'item_total':'200.00','invoice_total':'200.00'},{'item_name':'Different item'}):
            batch=self.upload([fields,{'code':'B0200000002'}]);self.commit(batch)
            self.assertEqual(self.plan(batch)['rows']['results'][0]['outcome'],'anomaly')
            self.assertEqual(self.resolve(batch).status_code,400)
            self.assertEqual(self.resolve(batch,'retain').status_code,200)
        self.assertEqual(FinancialSale.objects.filter(active=True).count(),2)
        self.assertEqual(FinancialSale.objects.get(code='B0200000001').source['date'],'2026-09-01')

    def test_incomplete_and_unknown_status_do_not_post_while_valid_invoice_does(self):
        batch=self.upload([{'invoice_total':'200.00'},{'code':'B0200000002','status':'Pendiente'},{'code':'B0200000003'}]);self.commit(batch)
        self.assertEqual(FinancialSale.objects.count(),1)
        self.assertEqual(SalesDecision.objects.filter(resolution='invalid').count(),2)
        failed=self.client.post('/api/finance/sales-imports/',{'company':self.company.pk,'file':SimpleUploadedFile('bad.csv',b'bad')},format='multipart')
        self.assertEqual(self.commit(failed.data['id']).status_code,400)

    def test_stale_ledger_and_mapping_plans_rejected(self):
        first=self.upload();second=self.upload();token=self.plan(second)['token'];self.commit(first)
        self.assertEqual(self.commit(second,token).status_code,409)
        token=self.plan(second)['token'];rule=self.company.source_mappings.first();rule.revision+=1;rule.save()
        self.assertEqual(self.commit(second,token).status_code,409)
        self.assertEqual(SalesPosting.objects.count(),1)

    def test_manual_channel_studio_survive_reimports_and_rule_edits(self):
        batch=self.upload();self.commit(batch);sale=FinancialSale.objects.get()
        response=self.assign(sale,channel='recurring',studio=self.other.pk);self.assertEqual(response.status_code,200,response.data)
        rule=self.company.source_mappings.get(source_field='alegra_cost_center');rule.studio=self.studio;rule.revision+=1;rule.save()
        second=self.upload();self.commit(second);sale.refresh_from_db()
        self.assertEqual(sale.studio_id,self.other.pk);self.assertEqual(sale.channel,'recurring')
        self.assertFalse(sale.assignments['requires_review'])
        self.assertEqual(self.assign(sale,channel='cash').status_code,200);sale.refresh_from_db();self.assertEqual(sale.studio_id,self.other.pk)

    def test_partial_assignment_edit_does_not_apply_new_defaults_to_other_field(self):
        batch=self.upload();self.commit(batch);sale=FinancialSale.objects.get()
        rule=self.company.source_mappings.get(source_field='alegra_cost_center')
        rule.studio=self.other;rule.revision+=1;rule.save()
        self.assertEqual(self.assign(sale,channel='recurring').status_code,200)
        sale.refresh_from_db()
        self.assertEqual(sale.studio_id,self.studio.pk)
        self.assertEqual(sale.assignments['studio_origin'],'rule')

    def test_replacement_and_no_refund_treatments_no_bank_effect(self):
        batch=self.upload([{'status':'Anulada'},{'code':'B0200000002'}]);self.commit(batch)
        sale=FinancialSale.objects.get(code='B0200000001');replacement=FinancialSale.objects.get(code='B0200000002')
        self.assertEqual(self.assign(sale,cancellation_treatment='replacement',replacement=replacement.pk).status_code,200)
        sale.refresh_from_db();self.assertEqual(sale.replacement_id,replacement.pk)
        self.assertEqual(self.assign(sale,cancellation_treatment='no_refund').status_code,200)
        sale.refresh_from_db();self.assertIsNone(sale.replacement_id)
        self.assertEqual(self.assign(replacement,cancellation_treatment='refund').status_code,400)
        self.assertEqual(self.assign(sale,cancellation_treatment='replacement',replacement=sale.pk).status_code,400)
        self.assertFalse(BankMovement.objects.exists())

    def test_assignment_revision_and_reconciled_guards(self):
        batch=self.upload();self.commit(batch);sale=FinancialSale.objects.get()
        self.assertEqual(self.assign(sale,channel='cash').status_code,200)
        stale=self.client.post(f'/api/finance/sales/{sale.pk}/assign/',{'expected_revision':1,'channel':'cash','note':'stale'},format='json')
        self.assertEqual(stale.status_code,409)
        sale.reconciled=True;sale.save();self.assertEqual(self.assign(sale,channel='cash').status_code,400)
        cancelled=self.upload([{'status':'Anulada'}]);self.commit(cancelled);self.assertEqual(self.resolve(cancelled).status_code,400)

    def test_undo_only_untouched_new_sales_and_retry_is_safe(self):
        batch=self.upload();self.commit(batch)
        preview=self.client.get(self.url(batch,'undo-preview')).data
        body={'expected_plan':preview['token'],'note':'Synthetic undo'}
        first=self.client.post(self.url(batch,'undo'),body,format='json');second=self.client.post(self.url(batch,'undo'),body,format='json')
        self.assertEqual(first.status_code,200,first.data);self.assertEqual(second.data,first.data)
        self.assertFalse(FinancialSale.objects.get().active)
        fresh=self.upload();self.assertEqual(self.commit(fresh).status_code,200);self.assertEqual(FinancialSale.objects.filter(active=True).count(),1)
        self.assertEqual(self.commit(batch).status_code,409)

    def test_undo_protects_overlap_manual_and_approved_cancellation(self):
        first=self.upload();self.commit(first);second=self.upload();self.commit(second)
        preview=self.client.get(self.url(first,'undo-preview')).data;self.assertEqual(preview['protected'][0]['reason'],'other_import')
        self.assertEqual(self.undo(second).data['status'],'undone')
        sale=FinancialSale.objects.get();self.assign(sale,channel='cash')
        self.assertEqual(self.client.get(self.url(first,'undo-preview')).data['protected'][0]['reason'],'changed')
        cancelled=self.upload([{'status':'Anulada'}]);self.commit(cancelled);self.resolve(cancelled)
        self.assertEqual(self.client.get(self.url(cancelled,'undo-preview')).data['protected'][0]['reason'],'approved_cancellation')
        self.assertEqual(self.undo(cancelled).data['status'],'partial_undo')

    def test_undo_protects_linked_replacement(self):
        original=self.upload([{'status':'Anulada'}]);self.commit(original)
        replacement_batch=self.upload([{'code':'B0200000002'}]);self.commit(replacement_batch)
        old=FinancialSale.objects.get(code='B0200000001');new=FinancialSale.objects.get(code='B0200000002')
        self.assign(old,cancellation_treatment='replacement',replacement=new.pk)
        preview=self.client.get(self.url(replacement_batch,'undo-preview')).data
        self.assertEqual(preview['protected'][0]['reason'],'replacement_link')

    def test_permission_scope_and_ownership_protect_actions_and_history(self):
        batch=self.upload();self.commit(batch);sale=FinancialSale.objects.get()
        for flag in ('can_view_money','can_view_finance','can_view_sensitive_finance'):
            setattr(self.profile,flag,False);self.profile.save()
            for url in (self.url(batch,'processing'),self.url(batch,'undo-preview'),f'/api/finance/sales/{sale.pk}/history/'):
                self.assertEqual(self.client.get(url).status_code,403)
            setattr(self.profile,flag,True);self.profile.save()
        self.profile.can_edit_finance=False;self.profile.save();self.assertEqual(self.assign(sale,channel='cash').status_code,403);self.assertEqual(self.undo_preview_status(batch),403)
        self.profile.can_edit_finance=True;self.profile.save()
        stranger=get_user_model().objects.create_user('other-finance@example.test');posting=SalesPosting.objects.get(batch_id=batch);posting.actor=stranger;posting.save()
        self.assertEqual(self.undo_preview_status(batch),403)
        self.profile.can_manage_finance_settings=True;self.profile.save();self.assertEqual(self.undo_preview_status(batch),200)
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.client.get(f'/api/finance/sales/{sale.pk}/history/').status_code,404)
        self.assertEqual(self.client.get(self.url(batch,'processing')).status_code,404)

    def undo_preview_status(self,batch):return self.client.get(self.url(batch,'undo-preview')).status_code


from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, close_old_connections
from rest_framework.test import APIClient, APITransactionTestCase


@skipUnless(connection.vendor=='postgresql','Concurrency checks require PostgreSQL row locks.')
@override_settings(FINANCE_ENABLED=True)
class SalesPostingRaceTests(APITransactionTestCase):
    setUp=SalesPostingTests.setUp
    upload=SalesPostingTests.upload
    url=SalesPostingTests.url
    plan=SalesPostingTests.plan

    def parallel(self,requests):
        user_id=self.user.pk
        def run(item):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(get_user_model().objects.get(pk=user_id))
                return client.post(f'/api/finance/sales-imports/{item[0]}/commit/',{'expected_plan':item[1]},format='json').status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:return sorted(pool.map(run,requests))

    def test_same_batch_concurrent_commit_posts_once(self):
        batch=self.upload();token=self.plan(batch)['token']
        self.assertEqual(self.parallel([(batch,token),(batch,token)]),[200,200])
        self.assertEqual(FinancialSale.objects.count(),1);self.assertEqual(SalesPosting.objects.count(),1)

    def test_overlapping_concurrent_plans_cannot_duplicate_invoice(self):
        first=self.upload();second=self.upload()
        plans=[(batch,self.plan(batch)['token']) for batch in (first,second)]
        self.assertEqual(self.parallel(plans),[200,409]);self.assertEqual(FinancialSale.objects.count(),1)
