"""Daily workspace queries and assignment regression tests, synthetic data only."""
from django.test import override_settings
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from core_data.models import Studio
from . import test_payment_posting as receipts
from .models import Account, FinancialReceipt, FinancialSale, PaymentEvent
from .test_bank_posting import BASE


@override_settings(FINANCE_ENABLED=True)
class WorkspaceTests(APITestCase):
    setUp=receipts.ReceiptPostingTests.setUp
    prepare=receipts.ReceiptPostingTests.prepare
    upload=receipts.ReceiptPostingTests.upload
    plan=receipts.ReceiptPostingTests.plan
    commit=receipts.ReceiptPostingTests.commit
    csv_batch=receipts.ReceiptPostingTests.csv_batch
    sale=receipts.ReceiptPostingTests.sale

    def invoices(self,**filters):
        return self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'invoices',**filters})

    def test_invoice_totals_count_invoices_once_and_filter_before_pagination(self):
        first=self.sale(total='3600.00');first.source.update(date='2026-09-09',customer='QA Client');first.save()
        second=self.sale(code='B0200005000',total='200.00');second.source.update(date='2026-08-09',customer='Synthetic Beta');second.save()
        self.commit(self.csv_batch())
        result=self.invoices();self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['count'],2);self.assertEqual(result.data['total'],'3800.00')
        self.assertEqual(result.data['results'][0]['payment_count'],2)
        self.assertIn('payment_methods',result.data['results'][0])
        FinancialReceipt.objects.filter(number='102').update(channel='cash')
        self.assertEqual(self.invoices(channel='cash').data['total'],'3600.00')
        self.assertEqual(self.invoices(channel='cash').data['results'][0]['payment_count'],2)
        result=self.invoices(start='2026-09-01',end='2026-09-30',search='QA Client')
        self.assertEqual(result.data['count'],1);self.assertEqual(result.data['total'],'3600.00')
        self.assertEqual(self.invoices(status='review').data['count'],2)
        for receipt in FinancialReceipt.objects.all():
            receipt.assignments={**receipt.assignments,'channel_review':False};receipt.save()
        result=self.invoices(status='review');self.assertEqual(result.data['count'],1)
        self.assertEqual(result.data['results'][0]['id'],second.pk)
        self.assertEqual(self.invoices(start='2026-10-01',end='2026-09-01').status_code,400)
        self.assertEqual(self.invoices(start='not a date').status_code,400)
        self.assertEqual(self.invoices(sort='unknown').status_code,400)
        self.assertEqual(result['Cache-Control'],'private, no-store')

    def test_bank_direction_totals_and_company_account_scope(self):
        account=Account.objects.create(company=self.company,name='Workspace bank',currency='DOP',kind='bank')
        response=self.client.post('/api/finance/bank-imports/',{'account':account.pk,'provider':'popular',
            'file':SimpleUploadedFile('bank.csv',BASE.encode())},format='multipart')
        self.assertEqual(response.status_code,201,response.data);batch=response.data['id']
        plan=self.client.get(f'/api/finance/bank-imports/{batch}/processing/').data
        response=self.client.post(f'/api/finance/bank-imports/{batch}/commit/',{'expected_plan':plan['token']},format='json')
        self.assertEqual(response.status_code,200,response.data)
        url='/api/finance/workspace/'
        for kind,total in [('credit','100.00'),('debit','-20.00')]:
            result=self.client.get(url,{'company':self.company.pk,'kind':kind})
            self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['count'],1);self.assertEqual(result.data['total'],total)
        result=self.client.get(url,{'company':self.company.pk,'kind':'debit','search':'nothing'})
        self.assertEqual(result.data['count'],0);self.assertEqual(result.data['total'],'0.00')
        result=self.client.get(url,{'company':self.company.pk,'kind':'debit','studio':1})
        self.assertEqual(result.status_code,400)

    def test_options_and_all_queries_respect_scope_and_detail_permissions(self):
        response=self.client.get('/api/finance/workspace/options/')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual([c['id'] for c in response.data['companies']],[self.company.pk])
        self.assertEqual(self.client.get('/api/finance/workspace/',{'company':self.spain.pk,'kind':'credit'}).status_code,404)
        studio=Studio.objects.create(name='Partial',site=self.site)
        self.profile.allowed_studios.add(studio)
        self.assertEqual(self.client.get('/api/finance/workspace/options/').data['companies'],[])
        self.assertEqual(self.invoices().status_code,404)
        self.profile.allowed_studios.clear();self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.invoices().status_code,403)
        self.assertEqual(self.client.get('/api/finance/workspace/options/').status_code,403)

    def test_unlinked_receipts_reachable_then_visible_under_correct_invoice(self):
        self.commit(self.csv_batch())
        url='/api/finance/workspace/'
        result=self.client.get(url,{'company':self.company.pk,'kind':'unlinked'})
        self.assertEqual(result.data['count'],2);self.assertEqual(result.data['total'],'3600.00')
        sale=self.sale()
        from .payment_posting import refresh_links
        refresh_links(self.company,self.user)
        result=self.client.get(f'/api/finance/receipts/?sale={sale.pk}')
        self.assertEqual(result.data['count'],2)
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'unlinked'}).data['count'],0)
        self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        self.assertEqual(self.client.get(url,{'company':self.company.pk,'kind':'unlinked'}).status_code,403)
        self.assertEqual(self.invoices().data['results'][0]['payment_count'],None)

    def test_payment_studio_override_source_lock_stale_and_reimport(self):
        studio=Studio.objects.create(name='Invoice studio',site=self.site)
        override=Studio.objects.create(name='Payment override',site=self.site)
        foreign=Studio.objects.create(name='Foreign',site=self.es)
        sale=self.sale();sale.studio=studio;sale.save()
        self.commit(self.csv_batch());receipt=FinancialReceipt.objects.get(number='101')
        url=f'/api/finance/receipts/{receipt.pk}/assign/'
        before=dict(receipt.source);channel=receipt.channel
        response=self.client.post(url,{'expected_revision':receipt.revision,'studio':override.pk,'note':'Verified payment studio'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['effective_studio'],override.pk)
        self.assertIn('file_name',response.data)
        self.assertIn('batch',response.data)
        receipt.refresh_from_db();self.assertEqual(receipt.channel,channel);self.assertEqual(receipt.source,before)
        self.assertTrue(PaymentEvent.objects.filter(receipt=receipt,action='assign',note='Verified payment studio').exists())
        self.assertEqual(self.client.post(url,{'expected_revision':receipt.revision-1,'studio':None,'note':'Stale'},format='json').status_code,409)
        self.assertEqual(self.client.post(url,{'expected_revision':receipt.revision,'studio':foreign.pk,'note':'Wrong scope'},format='json').status_code,400)
        self.assertEqual(self.client.post(url,{'expected_revision':receipt.revision,'amount':'1.00','note':'Locked facts'},format='json').status_code,400)
        batch=self.csv_batch();self.commit(batch);receipt.refresh_from_db();self.assertEqual(receipt.studio,override)
        response=self.client.post(url,{'expected_revision':receipt.revision,'studio':None,'note':'Restore inheritance'},format='json')
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['effective_studio'],studio.pk)
        sale.studio=override;sale.save()
        self.assertEqual(self.client.get(f'/api/finance/receipts/{receipt.pk}/').data['effective_studio'],override.pk)
        receipt.refresh_from_db();receipt.reconciled=True;receipt.save()
        self.assertEqual(self.client.post(url,{'expected_revision':receipt.revision,'channel':'cash','note':'Protected'},format='json').status_code,400)

    def test_payment_studio_edit_requires_existing_edit_capability(self):
        self.commit(self.csv_batch());receipt=FinancialReceipt.objects.first()
        self.profile.can_edit_finance=False;self.profile.save()
        response=self.client.post(f'/api/finance/receipts/{receipt.pk}/assign/',{'expected_revision':receipt.revision,'studio':None,'note':'Denied'},format='json')
        self.assertEqual(response.status_code,403)
