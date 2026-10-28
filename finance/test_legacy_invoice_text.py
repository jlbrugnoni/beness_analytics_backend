"""Strict legacy text comparison, protected invoice recovery and exact payment links."""
from copy import deepcopy
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_sales_posting as fixtures
from .models import (MigrationImportBatch, SalesImportBatch, SalesPosting, SalesDecision,
    FinancialSale, FinancialReceipt, PaymentImportBatch, PaymentImportRow, SalesEvent)


def damaged(text):return text.encode('cp1252').decode('mac_roman')


@override_settings(FINANCE_ENABLED=True)
class LegacyInvoiceTextTests(APITestCase):
    setUp=fixtures.SalesPostingTests.setUp
    upload=fixtures.SalesPostingTests.upload
    url=fixtures.SalesPostingTests.url
    plan=fixtures.SalesPostingTests.plan
    commit=fixtures.SalesPostingTests.commit
    assign=fixtures.SalesPostingTests.assign

    def rows(self,legacy=False,**changes):
        row={'customer':'Cliente Peña','item_name':'Grupal x2 días','payment_method':'Tarjeta crédito',**changes}
        return [{key:damaged(value) if legacy and isinstance(value,str) else value for key,value in row.items()}]

    def legacy(self,rows=None):
        batch=self.upload(rows or self.rows(True))
        origin=MigrationImportBatch.objects.create(company=self.company,selected_month='2026-09-01',
            file_name='legacy.xlsx',file_hash='a'*64,byte_size=1,original_file=b'x',parser_version='fixture',status='preview')
        SalesImportBatch.objects.filter(pk=batch).update(migration_batch=origin)
        return batch

    def pending(self,rows=None):
        batch=self.upload(rows or self.rows());posting=SalesPosting.objects.create(batch_id=batch,actor=self.user)
        for invoice in posting.batch.invoices.all():
            SalesDecision.objects.create(posting=posting,invoice=invoice,sale=FinancialSale.objects.get(code=invoice.code),resolution='pending')
        return batch

    def apply(self,batch,token=None):
        return self.client.post(self.url(batch,'apply-pending'),{'expected_plan':token or self.plan(batch)['token']},format='json')

    def receipt(self,customer='Cliente Peña'):
        batch=PaymentImportBatch.objects.create(company=self.company,file_name='payments.xlsx',file_hash='b'*64)
        row=PaymentImportRow.objects.create(batch=batch,source_row=2,source={})
        return FinancialReceipt.objects.create(company=self.company,number='101',created_from=row,
            source={'number':'101','date':'2026-09-01','amount':'100.00','currency':'DOP',
                    'invoice_code':'B0200000001','customer':customer},link_issue='customer_conflict',
            channel='recurring',studio=self.other,assignments={'channel_origin':'manual'})

    def test_legacy_then_native_links_preserving_original_text_items_and_manual_studio(self):
        first=self.legacy();self.commit(first);sale=FinancialSale.objects.get()
        self.assign(sale,studio=self.other.pk)
        before=list(FinancialSale.objects.values());native=self.upload(self.rows())
        self.assertEqual(self.plan(native)['counts'],{'unchanged':1})
        self.assertEqual(self.commit(native).status_code,200)
        self.assertEqual(list(FinancialSale.objects.values()),before)

    def test_native_then_legacy_has_same_identity_without_rewriting_native_text(self):
        native=self.upload(self.rows());self.commit(native)
        before=list(FinancialSale.objects.values());legacy=self.legacy()
        self.assertEqual(self.plan(legacy)['counts'],{'unchanged':1})
        self.commit(legacy);self.assertEqual(list(FinancialSale.objects.values()),before)

    def test_native_to_native_text_changes_are_still_source_anomalies(self):
        first=self.upload(self.rows(True));self.commit(first)
        native=self.upload(self.rows())
        self.assertEqual(self.plan(native)['counts'],{'anomaly':1})

    def test_real_customer_item_and_amount_changes_never_disappear_as_encoding(self):
        first=self.legacy();self.commit(first)
        for change in ({'customer':'Different client'},{'item_name':'Different service'},
                       {'invoice_total':'200.00','unit_price':'200.00','item_total':'200.00'}):
            batch=self.upload(self.rows(**change))
            self.assertEqual(self.plan(batch)['counts'],{'anomaly':1})

    def test_recovery_links_exact_encoded_customer_but_preserves_manual_payment_assignments(self):
        first=self.legacy();self.commit(first);receipt=self.receipt()
        sale_before=list(FinancialSale.objects.values());receipt_before=deepcopy(receipt.source)
        batch=self.pending();state=self.plan(batch)
        self.assertEqual(state['ready_count'],1)
        result=self.apply(batch,state['token']);self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['linked'],1);receipt.refresh_from_db()
        self.assertEqual(receipt.sale_id,FinancialSale.objects.get().pk);self.assertEqual(receipt.link_issue,'')
        self.assertEqual(receipt.source,receipt_before);self.assertEqual(receipt.channel,'recurring')
        self.assertEqual(receipt.studio_id,self.other.pk);self.assertEqual(receipt.assignments,{'channel_origin':'manual'})
        self.assertEqual(list(FinancialSale.objects.values()),sale_before)
        self.assertEqual(self.apply(batch,state['token']).status_code,409)
        self.assertEqual(self.apply(batch).data['linked'],0)
        self.assertEqual(SalesEvent.objects.filter(posting__batch_id=batch,action='link').count(),1)

    def test_genuine_customer_conflict_does_not_link_after_encoding_recovery(self):
        first=self.legacy();self.commit(first);receipt=self.receipt('Other person')
        batch=self.pending();self.apply(batch);receipt.refresh_from_db()
        self.assertIsNone(receipt.sale_id);self.assertEqual(receipt.link_issue,'customer_conflict')

    def test_cancellation_and_anomaly_decisions_remain_pending(self):
        first=self.legacy();self.commit(first)
        for change,outcome in [({'status':'Anulada'},'cancellation'),({'customer':'Other person'},'anomaly')]:
            batch=self.pending(self.rows(**change));state=self.plan(batch)
            self.assertEqual(state['ready_count'],0);self.assertEqual(state['rows']['results'][0]['outcome'],outcome)
            self.assertEqual(self.apply(batch).data['linked'],0)
            self.assertEqual(SalesDecision.objects.get(posting__batch_id=batch).resolution,'pending')

    def test_permission_revocation_blocks_recovery_without_changing_decisions(self):
        first=self.legacy();self.commit(first);batch=self.pending()
        self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.apply(batch).status_code,403)
        self.assertEqual(SalesDecision.objects.get(posting__batch_id=batch).resolution,'pending')

    def test_native_customer_conflict_cannot_use_historical_encoding_exception(self):
        batch=self.upload(self.rows());self.commit(batch);receipt=self.receipt(damaged('Cliente Peña'))
        from .payment_posting import refresh_links
        refresh_links(self.company,self.user);receipt.refresh_from_db()
        self.assertIsNone(receipt.sale_id);self.assertEqual(receipt.link_issue,'customer_conflict')

    def test_recovery_does_not_apply_encoding_rule_to_unrelated_old_invoice_links(self):
        first=self.legacy(self.rows(True)+self.rows(True,code='B0200000002'));self.commit(first)
        receipt=self.receipt()
        row=PaymentImportRow.objects.create(batch=receipt.created_from.batch,source_row=3,source={})
        unrelated=FinancialReceipt.objects.create(company=self.company,number='102',created_from=row,
            source={**receipt.source,'number':'102','invoice_code':'B0200000002'},link_issue='customer_conflict')
        before=FinancialReceipt.objects.values().get(pk=unrelated.pk)
        batch=self.pending();self.apply(batch)
        self.assertEqual(FinancialReceipt.objects.values().get(pk=unrelated.pk),before)
