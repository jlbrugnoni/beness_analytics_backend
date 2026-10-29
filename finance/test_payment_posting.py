import csv
import io
from copy import deepcopy
from datetime import date
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction, IntegrityError
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from . import test_migration_imports as migration_tests
from .test_payment_preview import payment_workbook
from .models import Company, FinancialReceipt, FinancialSale, PaymentPosting, PaymentImportBatch, PaymentDecision, BankMovement, SalesImportBatch, SalesImportInvoice, SalesImportRow
from .payment_preview import read_payment_csv
from .payment_views import store
from . import payment_posting as ops
from . import sales_posting


def payment_csv(rows=None):
    headers=['Cuenta','Fecha','Numero','Cliente','ID','Valor','Observaciones','Notas','Asociaciones','Tipo_nota','Conciliada','Metodo_pago','Estado']
    output=io.StringIO();writer=csv.writer(output,delimiter=';');writer.writerow(headers)
    for r in rows or [dict(number='101',amount='1200'),dict(number='102',amount='2400')]:
        writer.writerow(['Bank QA',r.get('date','09/09/2026'),r.get('number',''),'QA Client','QA-ID',r.get('amount','1200'),'',
            '',r.get('association','Facturas: B0200005029'),'Ingreso','No',r.get('method','Tarjeta crédito'),r.get('status','')])
    return output.getvalue().encode('utf-8-sig')


class PaymentCSVTests(SimpleTestCase):
    def test_raw_preset_no_manual_columns_preserves_each_payment(self):
        r=read_payment_csv(payment_csv())
        self.assertEqual(r['file_issues'],[]);self.assertEqual(len(r['rows']),2)
        self.assertEqual(r['rows'][0]['date'],'2026-09-09')
        self.assertIsNone(r['rows'][0]['method']);self.assertEqual(r['rows'][0]['original_method'],'Tarjeta crédito')
        self.assertEqual(r['summary']['amount_total'],'3600.00')
        self.assertEqual(r['rows'][0]['number'],'101')

    def test_unsupported_csv_shapes_fail_closed_and_status_is_reviewed(self):
        for content in (b'wrong;header\n1;2',b'\x00',payment_csv()+b'bad;width\n'):
            result=read_payment_csv(content);self.assertTrue(result['file_issues']);self.assertEqual(result['rows'],[])
        source=read_payment_csv(payment_csv([{'number':'1','status':'Anulado'}]))['rows'][0]
        self.assertEqual(ops.outcome(source,None),'invalid')
        payload=payment_csv().decode('utf-8-sig').replace('Estado\r\n','Estado;Currency\r\n')
        lines=payload.splitlines();payload='\r\n'.join([lines[0]]+[line+';EUR' for line in lines[1:]])
        result=read_payment_csv(payload.encode());self.assertEqual(result['file_issues'],[])
        self.assertTrue(all(ops.outcome(row,None)=='invalid' for row in result['rows']))


class ReceiptPostingTests(APITestCase):
    upload=migration_tests.MigrationAPITests.upload

    def setUp(self):
        migration_tests.MigrationAPITests.setUp(self)
        self.profile.can_edit_finance=True;self.profile.save()

    def csv_batch(self,content=None):
        response=self.client.post('/api/finance/payment-imports/',{'company':self.company.pk,
            'file':SimpleUploadedFile('payments.csv',content or payment_csv())},format='multipart')
        self.assertEqual(response.status_code,201,response.data);return response.data['id']

    def prepare(self,content=None,scope='selected'):
        source=self.upload(content or payment_workbook());self.assertEqual(source.status_code,201)
        response=self.client.post('/api/finance/payment-imports/from-migration/',{'migration_batch':source.data['id'],'scope':scope},format='json')
        self.assertEqual(response.status_code,201,response.data);return response.data['id']

    def plan(self,batch):
        response=self.client.get(f'/api/finance/payment-imports/{batch}/processing/')
        self.assertEqual(response.status_code,200,response.data);return response.data

    def commit(self,batch,expected=None):
        return self.client.post(f'/api/finance/payment-imports/{batch}/commit/',{'expected_plan':expected or self.plan(batch)['token']},format='json')

    def sale(self,code='B0200005029',total='3600.00',provider='alegra'):
        b=SalesImportBatch.objects.create(company=self.company,file_name='qa.csv',file_hash='a'*64,byte_size=1,original_file=b'x',parser_version='qa',status='preview')
        i=SalesImportInvoice.objects.create(batch=b,occurrence=1,code=code,source={},item_count=1,row_numbers=[1],issues=[])
        return FinancialSale.objects.create(company=self.company,provider=provider,code=code,source={'invoice_total':total,'status_kind':'paid'},items=[],created_from=i)

    def test_migration_shared_receipts_preserve_splits_and_link_existing_sale(self):
        sale=self.sale();batch=self.prepare();plan=self.plan(batch)
        self.assertEqual(plan['counts'],{'new':2});self.assertTrue(plan['can_commit'])
        response=self.commit(batch);self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertEqual(set(FinancialReceipt.objects.values_list('sale_id',flat=True)),{sale.pk})
        self.assertEqual(set(FinancialReceipt.objects.values_list('channel',flat=True)),{'card_terminal','cash'})
        self.assertEqual(FinancialSale.objects.count(),1);self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(self.commit(batch).status_code,200);self.assertEqual(FinancialReceipt.objects.count(),2)
        receipt=FinancialReceipt.objects.first()
        history=self.client.get(f'/api/finance/receipts/{receipt.pk}/history/')
        self.assertGreaterEqual(history.data['count'],2)

    def test_shared_identity_reuses_receipts_across_origins_preserving_manual_choices(self):
        historical=self.prepare();self.assertEqual(self.commit(historical).status_code,200)
        # Native row facts match; raw report lacks manual method/studio columns.
        rows=[]
        for r in PaymentImportBatch.objects.get(pk=historical).rows.all():
            s=deepcopy(r.source);s.update(method=None,location=None)
            rows.append(s)
        batch=store(self.company,self.user,b'raw-source',{'rows':rows,'file_issues':[],'parser_version':'qa'},'routine.csv')
        self.assertEqual(self.plan(batch.pk)['counts'],{'unchanged':2})
        self.assertEqual(self.commit(batch.pk).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertEqual(FinancialReceipt.objects.get(number='102').channel,'cash')
        original=PaymentPosting.objects.get(batch_id=historical);self.company.refresh_from_db()
        preview=ops.undo_plan(original,self.company)
        self.assertEqual(len(preview['protected']),2);self.assertEqual(preview['eligible'],[])

    def test_conflicts_are_pending_and_do_not_overwrite_or_block_new_rows(self):
        first=self.csv_batch();self.commit(first)
        second=self.csv_batch(payment_csv([{'number':'101','amount':'1300'},{'number':'103','amount':'10'}]))
        self.assertEqual(self.plan(second)['counts'],{'conflict':1,'new':1})
        response=self.commit(second);self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(FinancialReceipt.objects.get(number='101').source['amount'],'1200.00')
        self.assertEqual(FinancialReceipt.objects.count(),3)
        plan=self.plan(second);d=next(r for r in plan['rows']['results'] if r['resolution']=='pending')
        response=self.client.post(f'/api/finance/payment-imports/{second}/retain/',{'expected_plan':plan['token'],
            'decision_id':d['decision_id'],'expected_revision':d['decision_revision'],'note':'Keep verified original'},format='json')
        self.assertEqual(response.status_code,200,response.data)

    def test_missing_duplicate_identity_and_multiple_invoice_references_are_not_posted(self):
        batch=self.csv_batch(payment_csv([{'number':'1'},{'number':'1'},{'number':''},
            {'number':'2','association':'Facturas: B0200005029, B0200005090'},{'number':'3','amount':'15'}]))
        self.assertEqual(self.plan(batch)['counts'],{'invalid':4,'new':1})
        self.assertEqual(self.commit(batch).status_code,200)
        self.assertEqual(list(FinancialReceipt.objects.values_list('number',flat=True)),['3'])
        self.assertEqual(PaymentDecision.objects.filter(resolution='invalid',receipt__isnull=False).count(),0)

    def test_payment_first_links_after_invoice_commit_and_sales_undo_is_protected(self):
        batch=self.csv_batch();self.commit(batch)
        self.assertFalse(FinancialReceipt.objects.exclude(sale=None).exists())
        # Exercise actual sales commit hook with minimal valid source evidence.
        b=SalesImportBatch.objects.create(company=self.company,file_name='qa.csv',file_hash='b'*64,byte_size=1,original_file=b'x',parser_version='qa',status='preview')
        source={'code':'B0200005029','date':'2026-09-09','status':'Cobrada','invoice_total':'3600.00',
            'customer':'QA Client','cost_center':'','price_list':'','payment_method':'Tarjeta crédito'}
        SalesImportInvoice.objects.create(batch=b,occurrence=1,code='B0200005029',source=source,item_count=1,row_numbers=[2],issues=[])
        SalesImportRow.objects.create(batch=b,row_number=2,source_line=2,source_line_end=2,kind='data',raw=[],parsed={'customer':'QA Client','item_total':'3600.00'},issues=[])
        self.company.refresh_from_db()
        with transaction.atomic():
            company=Company.objects.select_for_update().get(pk=self.company.pk)
            post=sales_posting.commit(b,company,self.user,sales_posting.token(company,b))
        sale=FinancialSale.objects.get(code='B0200005029')
        self.assertEqual(FinancialReceipt.objects.filter(sale=sale).count(),2)
        self.company.refresh_from_db();undo=sales_posting.undo_plan(post,self.company)
        self.assertEqual(undo['eligible'],[]);self.assertEqual(undo['protected'][0]['reason'],'payment_link')

    def test_overpayment_cancelled_invoice_and_provider_scope(self):
        sale=self.sale(total='1200.00');batch=self.csv_batch();self.commit(batch)
        a=FinancialReceipt.objects.get(number='101');b=FinancialReceipt.objects.get(number='102')
        self.assertIsNone(a.sale_id);self.assertEqual(a.link_issue,'overallocated');self.assertEqual(b.link_issue,'overallocated');self.assertIsNone(b.sale_id)
        sale.source['status_kind']='cancelled';sale.save()
        self.company.refresh_from_db();ops.refresh_links(self.company,self.user)
        a.refresh_from_db();self.assertEqual(a.link_issue,'invoice_cancelled');self.assertIsNone(a.sale_id)
        self.assertEqual(FinancialSale.objects.count(),1)

    def test_other_provider_invoice_does_not_link_and_stale_sales_revision_blocks_commit(self):
        self.sale(provider='mindbody');batch=self.csv_batch();self.commit(batch)
        self.assertFalse(FinancialReceipt.objects.exclude(sale=None).exists())
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'invoice_missing'})
        second=self.csv_batch();expected=self.plan(second)['token']
        self.company.refresh_from_db();self.company.sales_revision+=1;self.company.save(update_fields=['sales_revision'])
        self.assertEqual(self.commit(second,expected).status_code,409)

    def test_explicit_invoice_code_with_customer_conflict_requires_review(self):
        sale=self.sale();sale.source['customer']='Different source customer';sale.save()
        batch=self.csv_batch();self.commit(batch)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertFalse(FinancialReceipt.objects.exclude(sale=None).exists())
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'customer_conflict'})

    def test_stale_plan_undo_and_retry_preserve_history(self):
        batch=self.csv_batch();expected=self.plan(batch)['token']
        self.company.payment_revision+=1;self.company.save()
        self.assertEqual(self.commit(batch,expected).status_code,409)
        self.assertEqual(FinancialReceipt.objects.count(),0)
        self.commit(batch)
        preview=self.client.get(f'/api/finance/payment-imports/{batch}/undo-preview/').data
        response=self.client.post(f'/api/finance/payment-imports/{batch}/undo/',{'expected_plan':preview['token'],'note':'QA reversal'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(FinancialReceipt.objects.filter(active=True).count(),0)
        self.assertEqual(self.commit(batch).status_code,409)
        self.assertEqual(PaymentImportBatch.objects.count(),1)
        self.assertEqual(FinancialReceipt.objects.count(),2)

    def test_permissions_scope_and_source_privacy(self):
        batch=self.csv_batch();base=f'/api/finance/payment-imports/{batch}/'
        for flag in ('can_view_money','can_view_finance','can_view_finance_bank_accounts','can_view_sensitive_finance'):
            setattr(self.profile,flag,False);self.profile.save()
            self.assertIn(self.client.get(base+'processing/').status_code,(403,404))
            self.assertIn(self.client.get(base+'original/').status_code,(403,404))
            setattr(self.profile,flag,True);self.profile.save()
        self.profile.can_import_finance=False;self.profile.save()
        self.assertFalse(self.plan(batch)['can_commit']);self.assertEqual(self.commit(batch).status_code,403)
        self.assertEqual(self.client.get(base+'original/').status_code,403)
        self.profile.allowed_sites.clear();self.assertEqual(self.client.get(base).status_code,404)

    def test_manual_method_edit_survives_repeat_and_protects_undo(self):
        first=self.csv_batch();self.commit(first);r=FinancialReceipt.objects.get(number='101')
        response=self.client.post(f'/api/finance/receipts/{r.pk}/assign/',{'expected_revision':r.revision,'channel':'recurring','note':'Verified recurring payment'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.client.post(f'/api/finance/receipts/{r.pk}/assign/',{'expected_revision':r.revision,'channel':'cash','note':'Stale'},format='json').status_code,409)
        second=self.csv_batch();self.commit(second);r.refresh_from_db()
        self.assertEqual(r.channel,'recurring');self.assertTrue(r.edited)
        preview=self.client.get(f'/api/finance/payment-imports/{first}/undo-preview/').data
        self.assertTrue(any(p['receipt_id']==r.pk and p['reason']=='changed' for p in preview['protected']))
        r.reconciled=True;r.save()
        self.assertEqual(self.client.post(f'/api/finance/receipts/{r.pk}/assign/',{'expected_revision':r.revision,'channel':'cash','note':'Forbidden'},format='json').status_code,400)

    def test_source_scope_receipt_company_and_undo_ownership(self):
        first=self.csv_batch();self.commit(first);r=FinancialReceipt.objects.first()
        # The same external number in a different legal company is a different receipt.
        other=Company.objects.create(name='Other DO QA',site=self.site,default_currency='DOP')
        response=self.client.post('/api/finance/payment-imports/',{'company':other.pk,'file':SimpleUploadedFile('other.csv',payment_csv())},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(self.commit(response.data['id']).status_code,200)
        self.assertEqual(FinancialReceipt.objects.filter(number=r.number).count(),2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialReceipt.objects.create(company=self.company,number=r.number,source=r.source,created_from=r.created_from)
        actor=get_user_model().objects.create_user('other-payment-actor@example.test')
        posting=PaymentPosting.objects.get(batch_id=first);posting.actor=actor;posting.save()
        self.assertEqual(self.client.get(f'/api/finance/payment-imports/{first}/undo-preview/').status_code,403)
        self.profile.can_manage_finance_settings=True;self.profile.save()
        self.assertEqual(self.client.get(f'/api/finance/payment-imports/{first}/undo-preview/').status_code,200)
        from core_data.models import Studio
        self.profile.allowed_studios.add(Studio.objects.create(name='Receipt restricted',site=self.site))
        self.assertEqual(self.client.get(f'/api/finance/receipts/{r.pk}/history/').status_code,404)
        self.assertEqual(self.client.get(f'/api/finance/payment-imports/{first}/processing/').status_code,404)

    def test_import_method_corrections_require_review_in_reverse_arrival_order(self):
        first=self.prepare();rows=[]
        for row in PaymentImportBatch.objects.get(pk=first).rows.all():
            source=deepcopy(row.source);source.update(method=None,location=None);rows.append(source)
        routine=store(self.company,self.user,b'routine-first',{'rows':rows,'file_issues':[],'parser_version':'qa'},'routine.csv')
        self.commit(routine.pk)
        self.assertEqual(self.plan(first)['counts'],{'assignment_conflict':2})
        self.commit(first)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertEqual(PaymentDecision.objects.filter(posting__batch_id=first,resolution='pending').count(),2)

    def test_csv_original_immutability_failed_layout_and_company_guard(self):
        content=payment_csv();batch=self.csv_batch(content)
        response=self.client.get(f'/api/finance/payment-imports/{batch}/original/')
        self.assertEqual(b''.join(response.streaming_content),content)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        failed=self.csv_batch(b'unknown;layout\n1;2');self.assertFalse(self.plan(failed)['can_commit'])
        self.assertEqual(self.commit(failed).status_code,400)
        from django.core.exceptions import ValidationError
        self.company.default_currency='EUR'
        with self.assertRaises(ValidationError):self.company.full_clean()


from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, close_old_connections
from rest_framework.test import APIClient, APITransactionTestCase


@skipUnless(connection.vendor=='postgresql','Receipt concurrency requires PostgreSQL company locks.')
class ReceiptRaceTests(APITransactionTestCase):
    setUp=ReceiptPostingTests.setUp
    csv_batch=ReceiptPostingTests.csv_batch
    plan=ReceiptPostingTests.plan

    def parallel(self,items):
        user_id=self.user.pk
        def run(item):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(get_user_model().objects.get(pk=user_id))
                return client.post(f'/api/finance/payment-imports/{item[0]}/commit/',{'expected_plan':item[1]},format='json').status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:return sorted(pool.map(run,items))

    def test_same_source_concurrent_commit_is_idempotent(self):
        batch=self.csv_batch();token=self.plan(batch)['token']
        self.assertEqual(self.parallel([(batch,token),(batch,token)]),[200,200])
        self.assertEqual(FinancialReceipt.objects.count(),2);self.assertEqual(PaymentPosting.objects.count(),1)

    def test_overlapping_concurrent_imports_cannot_duplicate_receipts(self):
        first=self.csv_batch();second=self.csv_batch()
        self.assertEqual(self.parallel([(b,self.plan(b)['token']) for b in (first,second)]),[200,409])
        self.assertEqual(FinancialReceipt.objects.count(),2)
