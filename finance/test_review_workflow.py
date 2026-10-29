"""Business review completion, API locks, independent upload and reopen grants."""
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_bank_classification as bank
from . import test_payment_matching as invoices
from . import test_migration_imports as migration
from .models import FinancialReceipt,SalesEvent,PaymentEvent,BankEvent


@override_settings(FINANCE_ENABLED=True)
class BankReviewLockTests(APITestCase):
    setUp=bank.BankClassificationTests.setUp
    records=bank.BankClassificationTests.records
    post=bank.BankClassificationTests.post
    preview=bank.BankClassificationTests.preview
    upload=bank.BankClassificationTests.upload
    commit=bank.BankClassificationTests.commit
    processing=bank.BankClassificationTests.processing
    assign=bank.BankClassificationTests.assign

    def test_review_locks_even_editor_until_privileged_audited_reopen(self):
        self.records()
        self.assertEqual(self.assign(self.debit,movement_kind='internal_transfer',reviewed=True).status_code,200)
        self.debit.refresh_from_db();source=dict(self.debit.source)
        self.assertEqual(self.assign(self.debit,reviewed=False).status_code,400)
        path=f'/api/finance/movements/{self.debit.pk}/reopen/'
        body={'expected_revision':self.debit.revision}
        self.assertEqual(self.client.post(path,body,format='json').status_code,403)
        self.profile.can_reopen_finance=True;self.profile.save()
        self.assertEqual(self.client.post(path,body,format='json').status_code,200)
        self.assertEqual(self.client.post(path,body,format='json').status_code,409)
        self.debit.refresh_from_db()
        self.assertEqual(self.assign(self.debit,description='Corrected assignment').status_code,200)
        self.debit.refresh_from_db();self.assertEqual(self.debit.source,source)
        self.assertEqual(BankEvent.objects.get(action='reopen').actor_id,self.user.pk)


@override_settings(FINANCE_ENABLED=True)
class InvoiceReviewLockTests(APITestCase):
    setUp=invoices.PaymentMatchingTests.setUp
    prepare_group=invoices.PaymentMatchingTests.prepare_group
    csv_batch=invoices.PaymentMatchingTests.csv_batch
    sale=invoices.PaymentMatchingTests.sale
    plan=invoices.PaymentMatchingTests.plan
    commit=invoices.PaymentMatchingTests.commit

    def prepare(self):
        self.prepare_group(customer='QA Client')
        studio=Studio.objects.create(site=self.site,name='Review studio')
        self.invoice.studio=studio;self.invoice.save()
        FinancialReceipt.objects.update(channel='card_terminal',studio=studio,assignments={'studio_origin':'invoice','channel_review':False})
        self.invoice.refresh_from_db()

    def action(self,name,revision=None):
        self.invoice.refresh_from_db()
        return self.client.post(f'/api/finance/sales/{self.invoice.pk}/{name}/',{'expected_revision':revision or self.invoice.revision},format='json')

    def test_review_requires_completeness_and_locks_invoice_and_payments_together(self):
        self.prepare_group(customer='QA Client')
        self.assertEqual(self.action('review').status_code,400)
        studio=Studio.objects.create(site=self.site,name='Review studio')
        self.invoice.studio=studio;self.invoice.save()
        FinancialReceipt.objects.update(channel='cash',studio=studio)
        self.assertEqual(self.action('review').status_code,200)
        self.invoice.refresh_from_db();self.assertTrue(self.invoice.reviewed)
        self.assertEqual(FinancialReceipt.objects.filter(reviewed=True).count(),2)
        self.assertEqual(self.client.post(f'/api/finance/sales/{self.invoice.pk}/assign/',{'expected_revision':self.invoice.revision,'studio':studio.pk},format='json').status_code,400)
        receipt=FinancialReceipt.objects.first()
        self.assertEqual(self.client.post(f'/api/finance/receipts/{receipt.pk}/assign/',{'expected_revision':receipt.revision,'channel':'cash','note':''},format='json').status_code,400)
        self.assertEqual(self.action('reopen').status_code,403)
        self.profile.can_reopen_finance=True;self.profile.save()
        self.assertEqual(self.action('reopen').status_code,200)
        self.assertFalse(FinancialReceipt.objects.filter(reviewed=True).exists())
        self.invoice.refresh_from_db();self.assertFalse(self.invoice.reviewed)
        self.assertEqual(SalesEvent.objects.filter(action='review').count(),1)
        self.assertEqual(PaymentEvent.objects.filter(action='reopen').count(),2)
        self.assertEqual(self.action('review',revision=1).status_code,409)

    def test_routine_import_stays_pending_and_unchanged_overlap_preserves_review(self):
        self.prepare();self.assertFalse(self.invoice.reviewed)
        self.assertEqual(self.action('review').status_code,200)
        originals=list(FinancialReceipt.objects.values('pk','source','assignments','reviewed','revision'))
        self.assertEqual(self.commit(self.csv_batch()).status_code,200)
        self.assertEqual(list(FinancialReceipt.objects.values('pk','source','assignments','reviewed','revision')),originals)
        result=self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'invoices','status':'reviewed'})
        self.assertEqual(result.data['count'],1)
        self.assertEqual(self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'invoices','status':'review'}).data['count'],0)

    def test_new_payment_does_not_silently_change_a_reviewed_invoice_group(self):
        from .test_payment_posting import payment_csv
        self.prepare();self.assertEqual(self.action('review').status_code,200)
        before=list(FinancialReceipt.objects.values('pk','reviewed','revision','link_issue'))
        batch=self.csv_batch(payment_csv([{'number':'103','amount':'100'}]))
        self.assertEqual(self.commit(batch).status_code,200)
        pending=FinancialReceipt.objects.get(number='103')
        self.assertEqual(pending.link_issue,'invoice_review_locked')
        self.assertIsNone(pending.sale_id);self.assertFalse(pending.reviewed)
        self.assertEqual(list(FinancialReceipt.objects.exclude(number='103').values('pk','reviewed','revision','link_issue')),before)
        self.invoice.refresh_from_db();self.assertTrue(self.invoice.reviewed)

    def test_classifier_needs_no_upload_permission_to_review(self):
        self.prepare();self.profile.can_import_finance=False;self.profile.can_import_finance_migration=False;self.profile.save()
        self.assertEqual(self.action('review').status_code,200)


@override_settings(FINANCE_ENABLED=True)
class IndependentUploadPermissionTests(APITestCase):
    setUp=migration.MigrationAPITests.setUp
    upload=migration.MigrationAPITests.upload
    csv_batch=invoices.PaymentMatchingTests.csv_batch

    def test_routine_upload_does_not_grant_migration_upload(self):
        self.profile.can_import_finance_migration=False;self.profile.save()
        self.csv_batch()
        self.assertEqual(self.upload().status_code,403)

    def test_migration_upload_does_not_grant_routine_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .test_payment_posting import payment_csv
        self.profile.can_import_finance=False;self.profile.save()
        self.assertEqual(self.upload().status_code,201)
        response=self.client.post('/api/finance/payment-imports/',{'company':self.company.pk,'file':SimpleUploadedFile('routine.csv',payment_csv())},format='multipart')
        self.assertEqual(response.status_code,403)
