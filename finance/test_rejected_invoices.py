"""Rejected source diagnostics do not fabricate invoice amounts or block valid imports."""
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_payment_posting as payment_fixtures
from . import test_sales_posting as sales_fixtures
from .models import FinancialSale,FinancialReceipt,SalesImportInvoice


@override_settings(FINANCE_ENABLED=True)
class RejectedInvoiceTests(APITestCase):
    setUp=payment_fixtures.ReceiptPostingTests.setUp
    upload=sales_fixtures.SalesPostingTests.upload
    url=sales_fixtures.SalesPostingTests.url
    sales_plan=sales_fixtures.SalesPostingTests.plan
    csv_batch=payment_fixtures.ReceiptPostingTests.csv_batch
    plan=payment_fixtures.ReceiptPostingTests.plan
    commit=payment_fixtures.ReceiptPostingTests.commit

    def post_sales(self,batch):
        return self.client.post(self.url(batch,'commit'),{'expected_plan':self.sales_plan(batch)['token']},format='json')

    def test_rejected_filter_search_reason_rows_and_valid_rows_still_import(self):
        batch=self.upload([{'code':'B0200000880','invoice_total':'','item_total':''},{'code':'B0200000881'}])
        before=list(SalesImportInvoice.objects.values_list('pk','source','issues'))
        response=self.client.get(self.url(batch,'processing'),{'outcome':'invalid','search':'0880'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['invalid_count'],1);self.assertEqual(response.data['rows']['count'],1)
        row=response.data['rows']['results'][0]
        self.assertEqual(row['source_rows'],[3])
        self.assertIn('missing_invoice_total',row['review_issues']);self.assertIn('missing_item_total',row['review_issues'])
        self.assertEqual(row['source']['invoice_total'],'')
        self.assertEqual(list(SalesImportInvoice.objects.values_list('pk','source','issues')),before)
        self.assertEqual(self.client.get(self.url(batch,'processing'),{'outcome':'approve_invalid'}).status_code,400)
        self.assertEqual(self.post_sales(batch).status_code,200)
        self.assertEqual(list(FinancialSale.objects.values_list('code',flat=True)),['B0200000881'])
        self.assertEqual(self.client.get(self.url(batch,'processing'),{'outcome':'invalid'}).data['rows']['count'],1)

    def test_corrected_invoice_report_links_existing_payments_without_reupload(self):
        bad=self.upload([{'code':'B0200005029','customer':'QA Client','invoice_total':'','item_total':'','unit_price':'3600'}])
        self.assertEqual(self.post_sales(bad).status_code,200)
        self.assertEqual(self.commit(self.csv_batch()).status_code,200)
        receipt=FinancialReceipt.objects.order_by('pk').first()
        before=list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments'))
        detail=self.client.get(f'/api/finance/receipts/{receipt.pk}/')
        self.assertEqual(detail.data['invoice_problem']['reason'],'missing_invoice_total')
        self.assertEqual(detail.data['invoice_problem']['source_rows'],[3])
        self.assertEqual(detail.data['invoice_problem']['batch'],bad)
        self.assertEqual(detail.data['link_issue'],'invoice_missing')
        good=self.upload([{'code':'B0200005029','customer':'QA Client','invoice_total':'3600','item_total':'3600','unit_price':'3600'}])
        self.assertEqual(self.post_sales(good).status_code,200)
        self.assertEqual(FinancialSale.objects.count(),1);self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertFalse(FinancialReceipt.objects.filter(sale=None).exists())
        self.assertFalse(FinancialReceipt.objects.exclude(link_issue='').exists())
        self.assertEqual(list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments')),before)
        self.assertNotIn('invoice_problem',self.client.get(f'/api/finance/receipts/{receipt.pk}/').data)
