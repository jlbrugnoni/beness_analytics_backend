"""Date corrections require exact newer source evidence; recovery preserves active rows."""
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_sales_posting as sales_fixtures
from . import test_migration_sales as migration_fixtures
from .models import FinancialSale,SalesEvent,SalesImportBatch,FinancialReceipt,PaymentImportBatch


@override_settings(FINANCE_ENABLED=True)
class InvoiceDateCorrectionTests(APITestCase):
    setUp=sales_fixtures.SalesPostingTests.setUp
    upload=sales_fixtures.SalesPostingTests.upload
    url=sales_fixtures.SalesPostingTests.url
    plan=sales_fixtures.SalesPostingTests.plan
    commit=sales_fixtures.SalesPostingTests.commit

    def prepare(self,changes=None):
        self.first=self.upload();self.commit(self.first);self.sale=FinancialSale.objects.get()
        self.new=self.upload([{'date':'23/04/2026',**(changes or {})}]);self.commit(self.new)

    def correct(self,**extra):
        plan=self.plan(self.new);row=plan['rows']['results'][0]
        return self.client.post(self.url(self.new,'resolve'),{'expected_plan':plan['token'],'decision_id':row['decision_id'],
            'expected_revision':row['decision_revision'],'action':'correct_date','note':'Verified date from corrected source',**extra},format='json')

    def test_approved_date_only_change_preserves_assignments_amounts_and_source_evidence(self):
        self.prepare();before=(self.sale.assignments,self.sale.studio_id,self.sale.channel,self.sale.items)
        self.assertTrue(self.plan(self.new)['rows']['results'][0]['can_correct_date'])
        source=SalesImportBatch.objects.get(pk=self.first).original_file
        self.assertEqual(self.correct().status_code,200)
        self.sale.refresh_from_db();self.assertEqual(self.sale.source['date'],'2026-04-23')
        self.assertEqual(self.sale.source['invoice_total'],'100.00')
        self.assertEqual((self.sale.assignments,self.sale.studio_id,self.sale.channel,self.sale.items),before)
        self.assertEqual(SalesImportBatch.objects.get(pk=self.first).original_file,source)
        event=SalesEvent.objects.get(action='correct_date')
        self.assertEqual(event.before['source']['date'],'2026-09-01');self.assertEqual(event.after['source']['date'],'2026-04-23')
        self.assertEqual(event.actor_id,self.user.pk);self.assertEqual(self.correct().status_code,409)
        self.assertEqual(FinancialSale.objects.count(),1)
        undo=self.client.get(self.url(self.new,'undo-preview'))
        self.assertEqual(undo.data['protected'][0]['reason'],'approved_date_correction')

    def test_other_changed_facts_cannot_be_approved_as_date_only(self):
        self.prepare({'customer':'Other customer'})
        self.assertFalse(self.plan(self.new)['rows']['results'][0]['can_correct_date'])
        self.assertEqual(self.correct().status_code,400);self.sale.refresh_from_db()
        self.assertEqual(self.sale.source['date'],'2026-09-01');self.assertFalse(SalesEvent.objects.filter(action='correct_date').exists())

    def test_reason_permissions_reconciliation_and_stale_plan_are_rechecked(self):
        self.prepare();self.assertEqual(self.correct(note='').status_code,400)
        self.profile.can_edit_finance=False;self.profile.save();self.assertEqual(self.correct().status_code,403)
        self.profile.can_edit_finance=True;self.profile.save();self.sale.reconciled=True;self.sale.save(update_fields=['reconciled'])
        self.assertFalse(self.plan(self.new)['rows']['results'][0]['can_correct_date']);self.assertEqual(self.correct().status_code,400)
        self.sale.reconciled=False;self.sale.save(update_fields=['reconciled'])
        old=self.plan(self.new)['token'];self.company.refresh_from_db();self.company.sales_revision+=1;self.company.save(update_fields=['sales_revision'])
        self.assertEqual(self.correct(expected_plan=old).status_code,409)

    def test_report_older_than_original_cannot_correct_date(self):
        self.prepare()
        SalesImportBatch.objects.filter(pk=self.new).update(created_at=SalesImportBatch.objects.get(pk=self.first).created_at)
        self.assertFalse(self.plan(self.new)['rows']['results'][0]['can_correct_date'])
        self.assertEqual(self.correct().status_code,400)


@override_settings(FINANCE_ENABLED=True)
class InvoiceRecoveryTests(APITestCase):
    setUp=migration_fixtures.WorkbookAlegraAPITests.setUp
    upload=migration_fixtures.WorkbookAlegraAPITests.upload
    prepare=migration_fixtures.WorkbookAlegraAPITests.prepare
    commit=migration_fixtures.WorkbookAlegraAPITests.commit

    def test_reprepare_after_undo_reuses_payments_and_active_invoice_assignments(self):
        self.profile.can_edit_finance=True;self.profile.save()
        batch=self.upload(migration_fixtures.combined([{}, {'code':'B0200000002'}])).data['id']
        prepared=self.prepare(batch).data;first=prepared['sales_batch']['id'];payment=prepared['payment_batch']['id']
        self.commit('sales',first);self.commit('payment',payment)
        retained=FinancialSale.objects.get(code='B0200000001');assignments=retained.assignments
        receipts=list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments','sale_id'))
        base=f'/api/finance/sales-imports/{first}/'
        token=self.client.get(base+'undo-preview/').data['token']
        result=self.client.post(base+'undo/',{'expected_plan':token,'note':'Recover unlinked invoices only'},format='json')
        self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['status'],'partial_undo')
        self.assertEqual(FinancialSale.objects.filter(active=True).count(),1)
        result=self.prepare(batch);self.assertEqual(result.status_code,200,result.data)
        second=result.data['sales_batch']['id'];self.assertNotEqual(first,second)
        self.assertEqual(result.data['payment_batch']['id'],payment)
        self.assertEqual(FinancialSale.objects.filter(active=True).count(),1)  # Preview does not post.
        self.assertEqual(self.prepare(batch).data['sales_batch']['id'],second)  # Retry reuses unposted preview.
        self.commit('sales',second)
        self.assertEqual(FinancialSale.objects.filter(active=True).count(),2)
        retained.refresh_from_db();self.assertEqual(retained.assignments,assignments)
        self.assertEqual(list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments','sale_id')),receipts)
        self.assertEqual(PaymentImportBatch.objects.count(),1)
