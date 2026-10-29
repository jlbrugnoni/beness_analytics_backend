"""Standing invoice/payment identity rules and auditable, stale-safe manual decisions."""
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_payment_posting as fixtures
from .models import FinancialReceipt,PaymentEvent,SalesPosting,SalesEvent
from . import payment_posting as operations


@override_settings(FINANCE_ENABLED=True)
class PaymentMatchingTests(APITestCase):
    csv_batch=fixtures.ReceiptPostingTests.csv_batch
    plan=fixtures.ReceiptPostingTests.plan
    commit=fixtures.ReceiptPostingTests.commit
    sale=fixtures.ReceiptPostingTests.sale

    def setUp(self):
        fixtures.ReceiptPostingTests.setUp(self)
        self.profile.can_edit_finance=True;self.profile.save()

    def prepare_group(self,total='3600.00',customer='Invoice Company',content=None):
        self.invoice=self.sale(total=total)
        self.invoice.source.update(customer=customer,date='2026-09-09',code=self.invoice.code,currency='DOP');self.invoice.save()
        SalesPosting.objects.create(batch=self.invoice.created_from.batch,actor=self.user)
        self.assertEqual(self.commit(self.csv_batch(content)).status_code,200)
        self.receipt=FinancialReceipt.objects.order_by('pk').first()
        return self.receipt

    def context(self):
        response=self.client.get(f'/api/finance/receipts/{self.receipt.pk}/')
        self.assertEqual(response.status_code,200,response.data)
        return response.data['matching_review']

    def review(self,decision='accept_names',**values):
        return self.client.post(f'/api/finance/receipts/{self.receipt.pk}/review-link/',
            {'expected_token':self.context()['basis_token'],'decision':decision,**values},format='json')

    def refresh(self):
        return self.client.post('/api/finance/receipts/refresh-links/',{'company':self.company.pk},format='json')

    def test_matching_names_and_total_auto_link_split_payments(self):
        self.prepare_group(customer='QA Client')
        self.assertEqual(set(FinancialReceipt.objects.values_list('sale_id',flat=True)),{self.invoice.pk})
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{''})
        self.assertEqual(self.refresh().data['updated'],0)

    def test_name_difference_requires_audited_explicit_approval_for_entire_group(self):
        self.prepare_group()
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'customer_conflict'})
        before=list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments'))
        c=self.context();self.assertTrue(c['amounts_equal']);self.assertEqual(c['payment_total'],'3600.00');self.assertEqual(c['payment_count'],2)
        self.assertEqual(self.review().status_code,200)
        self.assertEqual(set(FinancialReceipt.objects.values_list('sale_id',flat=True)),{self.invoice.pk})
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{''})
        self.assertEqual(list(FinancialReceipt.objects.order_by('pk').values_list('pk','source','assignments')),before)
        self.assertEqual(PaymentEvent.objects.filter(action='payment_review',actor=self.user).count(),2)
        self.assertEqual(SalesEvent.objects.filter(action='payment_review').count(),1)
        count=PaymentEvent.objects.count();self.assertEqual(self.review().status_code,200);self.assertEqual(PaymentEvent.objects.count(),count)

    def test_different_amount_even_with_same_names_requires_explicit_reason(self):
        self.prepare_group(total='4000.00',customer='QA Client')
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'amount_mismatch'})
        self.assertEqual(self.review().status_code,400)
        self.assertEqual(self.review('accept_difference').status_code,400)
        self.assertEqual(self.review('accept_difference',note='Partial payment; remainder outstanding').status_code,200)
        self.assertEqual(self.context()['difference'],'-400.00')
        self.invoice.refresh_from_db();self.assertEqual(self.invoice.source['invoice_total'],'4000.00')
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{''})

    def test_overpayment_never_auto_allocates_a_convenient_subset(self):
        self.prepare_group(total='1200.00',customer='QA Client')
        self.assertFalse(FinancialReceipt.objects.exclude(sale=None).exists())
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'overallocated'})
        self.assertEqual(self.review('accept_difference',note='Reported excess confirmed; follow-up pending').status_code,200)
        self.assertEqual(self.context()['difference'],'2400.00')

    def test_changed_payment_set_invalidates_approval_and_rejects_stale_confirmation(self):
        self.prepare_group();old=self.context()['basis_token'];self.assertEqual(self.review().status_code,200)
        self.assertEqual(self.commit(self.csv_batch(fixtures.payment_csv([{'number':'103','amount':'50'}]))).status_code,200)
        c=self.context();self.assertFalse(c['approved']);self.assertEqual(c['difference'],'50.00')
        response=self.client.post(f'/api/finance/receipts/{self.receipt.pk}/review-link/',{'expected_token':old,'decision':'accept_names'},format='json')
        self.assertEqual(response.status_code,409)
        self.assertEqual(FinancialReceipt.objects.get(pk=self.receipt.pk).link_issue,'overallocated')

    def test_reopen_withdraws_approval_and_preserves_original_links_and_history(self):
        self.prepare_group();self.review()
        self.assertEqual(self.review('reopen').status_code,200)
        self.assertFalse(self.context()['approved'])
        self.assertEqual(set(FinancialReceipt.objects.values_list('link_issue',flat=True)),{'customer_conflict'})
        self.assertEqual(set(FinancialReceipt.objects.values_list('sale_id',flat=True)),{self.invoice.pk})
        self.assertEqual(SalesEvent.objects.filter(action='payment_review').count(),2)

    def test_source_change_invalidates_approval_but_assignment_edit_does_not(self):
        self.prepare_group();self.review();before=self.context()['basis_token']
        FinancialReceipt.objects.filter(pk=self.receipt.pk).update(channel='cash')
        self.assertEqual(self.context()['basis_token'],before)
        self.invoice.source['customer']='Another legal entity';self.invoice.save(update_fields=['source'])
        self.assertFalse(self.context()['approved']);self.assertNotEqual(self.context()['basis_token'],before)
        self.invoice.source['customer']='QA Client';self.invoice.save(update_fields=['source'])
        self.assertEqual(self.refresh().status_code,200)
        detail=self.client.get(f'/api/finance/receipts/{self.receipt.pk}/')
        self.assertNotIn('matching_review',detail.data)  # New source facts now agree automatically.

    def test_reconcile_permission_scope_and_visibility_are_rechecked(self):
        self.prepare_group();self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.review().status_code,403);self.assertEqual(self.refresh().status_code,403)
        self.profile.can_edit_finance=True;self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.client.get(f'/api/finance/receipts/{self.receipt.pk}/').status_code,403)
        self.profile.can_view_sensitive_finance=True;self.profile.allowed_sites.clear();self.profile.save()
        self.assertEqual(self.client.post(f'/api/finance/receipts/{self.receipt.pk}/review-link/',{}).status_code,404)
        self.assertEqual(SalesEvent.objects.filter(action='payment_review').count(),0)

    def test_cancelled_invoice_reconciliation_and_foreign_currency_cannot_be_approved(self):
        self.prepare_group();self.invoice.source['status_kind']='cancelled';self.invoice.save()
        self.assertEqual(self.review().status_code,400)
        self.invoice.source['status_kind']='paid';self.invoice.save()
        FinancialReceipt.objects.filter(pk=self.receipt.pk).update(reconciled=True)
        self.assertEqual(self.review().status_code,400)
        FinancialReceipt.objects.filter(pk=self.receipt.pk).update(reconciled=False)
        self.receipt.refresh_from_db();self.receipt.source['currency']='EUR';self.receipt.save()
        self.assertEqual(self.review().status_code,400)

    def test_invoice_dialog_includes_unlinked_candidates_and_review_list_includes_linked_warnings(self):
        self.prepare_group()
        result=self.client.get('/api/finance/receipts/',{'company':self.company.pk,'sale':self.invoice.pk})
        self.assertEqual(result.data['count'],2)
        invoices=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'invoices','status':'review'})
        self.assertEqual(invoices.status_code,200,invoices.data)
        self.assertEqual(invoices.data['results'][0]['payment_count'],0)  # No approved links yet; detail exposes both candidates.
        self.assertTrue(invoices.data['results'][0]['needs_review'])
        self.review();self.review('reopen')
        result=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'unlinked'})
        self.assertEqual(result.data['count'],2)
