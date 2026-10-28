"""Missing payment numbers are a reviewed identity issue, not grounds for a reset."""
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_payment_posting as f
from .models import FinancialReceipt,PaymentEvent,PaymentDecision,SourceMapping


@override_settings(FINANCE_ENABLED=True)
class PaymentIdentityTests(APITestCase):
    setUp=f.ReceiptPostingTests.setUp
    sale=f.ReceiptPostingTests.sale
    csv_batch=f.ReceiptPostingTests.csv_batch
    plan=f.ReceiptPostingTests.plan
    commit=f.ReceiptPostingTests.commit

    def missing(self,amount='3600',**extra):
        batch=self.csv_batch(f.payment_csv([{'number':'','amount':amount,**extra}]))
        self.assertEqual(self.commit(batch).status_code,200)
        return batch

    def resolve(self,batch,action='create',row=None,**extra):
        plan=self.plan(batch);row=row or plan['rows']['results'][0]
        return self.client.post(f'/api/finance/payment-imports/{batch}/resolve-identity/',
            {'row_id':row['row_id'],'expected_plan':plan['token'],'action':action,**extra},format='json')

    def test_accept_missing_number_preserves_source_and_links_invoice_with_audit_and_retry(self):
        SourceMapping.objects.create(company=self.company,source_field='alegra_payment_method',source_value='Tarjeta crédito',normalized_value='tarjeta crédito',channel='card_terminal')
        invoice=self.sale();batch=self.missing();row=self.plan(batch)['rows']['results'][0]
        self.assertTrue(row['can_resolve_identity']);self.assertFalse(FinancialReceipt.objects.exists())
        original=PaymentDecision.objects.get(row_id=row['row_id']).row.source
        response=self.resolve(batch);self.assertEqual(response.status_code,200,response.data)
        receipt=FinancialReceipt.objects.get();self.assertTrue(receipt.number.startswith('manual-'))
        self.assertIsNone(receipt.source['number']);self.assertEqual(receipt.sale_id,invoice.pk);self.assertEqual(receipt.link_issue,'')
        self.assertEqual(PaymentDecision.objects.get(row_id=row['row_id']).row.source,original)
        self.assertEqual(PaymentEvent.objects.filter(action='identity_review',actor=self.user).count(),1)
        self.assertEqual(self.resolve(batch).status_code,200);self.assertEqual(FinancialReceipt.objects.count(),1)
        self.assertEqual(PaymentEvent.objects.filter(action='identity_review').count(),1)
        self.assertFalse(self.plan(batch)['rows']['results'][0]['can_resolve_identity'])
        closure=self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':'2026-09'})
        self.assertEqual(closure.status_code,200,closure.data)
        card=next(r for r in closure.data['methods'] if r['channel']=='card_terminal')
        self.assertEqual(card['gross'],'3600.00')
        self.assertEqual(card['actual'],'0.00')

    def test_repeated_anonymous_report_requires_explicit_link_not_duplicate_creation(self):
        self.sale();first=self.missing();self.resolve(first);receipt=FinancialReceipt.objects.get()
        second=self.missing();row=self.plan(second)['rows']['results'][0]
        self.assertEqual(row['identity_candidates'][0]['id'],receipt.pk)
        self.assertEqual(self.resolve(second).status_code,400)
        before=(receipt.source,receipt.assignments)
        self.assertEqual(self.resolve(second,'link',receipt_id=receipt.pk).status_code,200)
        receipt.refresh_from_db();self.assertEqual((receipt.source,receipt.assignments),before)
        self.assertEqual(FinancialReceipt.objects.count(),1)

    def test_later_numbered_report_requires_link_then_establishes_overlap_alias(self):
        self.sale();first=self.missing();self.resolve(first);receipt=FinancialReceipt.objects.get()
        numbered=self.csv_batch(f.payment_csv([{'number':'103','amount':'3600'}]))
        self.assertEqual(self.plan(numbered)['counts'],{'identity_review':1})
        self.assertEqual(self.commit(numbered).status_code,200);self.assertEqual(FinancialReceipt.objects.count(),1)
        self.assertEqual(self.resolve(numbered,'link',receipt_id=receipt.pk).status_code,200)
        again=self.csv_batch(f.payment_csv([{'number':'103','amount':'3600'}]))
        self.assertEqual(self.plan(again)['counts'],{'unchanged':1})
        self.assertEqual(self.commit(again).status_code,200);self.assertEqual(FinancialReceipt.objects.count(),1)
        self.assertIsNone(FinancialReceipt.objects.get().source['number'])

    def test_same_facts_can_be_separate_occurrences_only_with_explicit_distinct_confirmation(self):
        self.sale(total='7200.00');first=self.missing();self.resolve(first)
        second=self.missing();self.assertEqual(self.resolve(second,distinct=True).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        third=self.missing();self.assertEqual(len(self.plan(third)['rows']['results'][0]['identity_candidates']),2)
        self.assertEqual(self.resolve(third).status_code,400)

    def test_bad_date_amount_status_and_duplicate_number_cannot_be_bypassed(self):
        for extra in ({'date':'bad'},{'amount':'-2'},{'status':'MEDIAS'}):
            batch=self.missing(**extra);self.assertFalse(self.plan(batch)['rows']['results'][0]['can_resolve_identity'])
            self.assertEqual(self.resolve(batch).status_code,400)
        self.assertFalse(FinancialReceipt.objects.exists())

    def test_wrong_receipt_scope_stale_and_permissions_are_enforced(self):
        self.sale();other=self.csv_batch(f.payment_csv([{'number':'104','amount':'1200'}]));self.commit(other)
        receipt=FinancialReceipt.objects.get();batch=self.missing()
        self.assertEqual(self.resolve(batch,'link',receipt_id=receipt.pk).status_code,400)
        self.profile.can_edit_finance=False;self.profile.save();self.assertEqual(self.resolve(batch).status_code,403)
        self.profile.can_edit_finance=True;self.profile.save()
        old=self.plan(batch)['token'];self.company.refresh_from_db();self.company.payment_revision+=1;self.company.save(update_fields=['payment_revision'])
        self.assertEqual(self.resolve(batch,expected_plan=old).status_code,409)
        self.assertEqual(self.resolve(batch,amount='99').status_code,400)

    def test_review_filter_and_undo_recognize_manually_created_receipt(self):
        self.sale();batch=self.missing()
        plan=self.client.get(f'/api/finance/payment-imports/{batch}/processing/',{'review':'identity'})
        self.assertEqual(plan.status_code,200);self.assertEqual(plan.data['rows']['count'],1)
        self.assertEqual(self.resolve(batch).status_code,200)
        plan=self.client.get(f'/api/finance/payment-imports/{batch}/processing/',{'review':'identity'})
        self.assertEqual(plan.data['rows']['count'],0)
        preview=self.client.get(f'/api/finance/payment-imports/{batch}/undo-preview/')
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertEqual(len(preview.data['eligible']),1)

    def test_changed_numbered_overlap_is_reviewed_even_when_amount_differs(self):
        self.sale();first=self.missing();self.resolve(first)
        changed=self.csv_batch(f.payment_csv([{'number':'110','amount':'3500'}]))
        self.assertEqual(self.plan(changed)['counts'],{'identity_review':1})
        self.assertEqual(self.commit(changed).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),1)
        receipt=FinancialReceipt.objects.get()
        self.assertEqual(self.resolve(changed,'link',receipt_id=receipt.pk).status_code,400)
        self.assertEqual(self.resolve(changed).status_code,400)
        self.assertEqual(self.resolve(changed,distinct=True).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),2)
