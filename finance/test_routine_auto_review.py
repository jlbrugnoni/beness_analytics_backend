"""Routine invoice review completes at import, without hiding matching exceptions."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from . import test_sales_posting as sales_fixtures
from .models import FinancialReceipt, FinancialSale, PaymentEvent, SalesEvent
from .test_payment_posting import payment_csv


@override_settings(FINANCE_ENABLED=True)
class RoutineAutoReviewTests(APITestCase):
    upload = sales_fixtures.SalesPostingTests.upload
    url = sales_fixtures.SalesPostingTests.url
    plan = sales_fixtures.SalesPostingTests.plan
    commit = sales_fixtures.SalesPostingTests.commit
    code = 'E320000000001'

    def setUp(self):
        sales_fixtures.SalesPostingTests.setUp(self)
        self.profile.can_view_finance_bank_accounts = True
        self.profile.can_reopen_finance = True
        self.profile.save()

    def invoices(self, **values):
        batch = self.upload([{'code': self.code, 'date': '09/09/2026', 'customer': 'QA Client', **values}])
        response = self.commit(batch)
        self.assertEqual(response.status_code, 200, response.data)
        return FinancialSale.objects.get(code=self.code)

    def payments(self, **values):
        content = payment_csv([{'number': '101', 'amount': '100.00',
                                'association': f'Facturas: {self.code}', **values}])
        response = self.client.post('/api/finance/payment-imports/', {
            'company': self.company.pk, 'file': SimpleUploadedFile('payments.csv', content)}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/finance/payment-imports/{response.data['id']}"
        plan = self.client.get(f'{url}/processing/')
        self.assertEqual(plan.status_code, 200, plan.data)
        response = self.client.post(f'{url}/commit/', {'expected_plan': plan.data['token']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return FinancialReceipt.objects.get(number='101')

    def assert_completed(self):
        sale = FinancialSale.objects.get(code=self.code)
        payment = FinancialReceipt.objects.get(number='101')
        self.assertTrue(sale.reviewed)
        self.assertTrue(payment.reviewed)
        self.assertFalse(payment.assignments['channel_review'])
        self.assertEqual(payment.sale_id, sale.pk)
        self.assertEqual(SalesEvent.objects.filter(sale=sale, action='routine_auto_review').count(), 1)
        self.assertEqual(PaymentEvent.objects.filter(receipt=payment, action='routine_auto_review').count(), 1)

    def test_invoice_then_payment_completes_and_identical_uploads_preserve_review(self):
        self.assertFalse(self.invoices().reviewed)
        self.payments()
        self.assert_completed()
        self.invoices()
        self.payments()
        self.assert_completed()

    def test_payment_then_invoice_completes(self):
        self.assertFalse(self.payments().reviewed)
        self.invoices()
        self.assert_completed()

    def test_missing_method_remains_open(self):
        self.invoices()
        receipt = self.payments(method='Unmapped')
        self.assertFalse(receipt.reviewed)
        self.assertFalse(FinancialSale.objects.get(code=self.code).reviewed)

    def test_missing_studio_remains_open(self):
        self.invoices(cost_center='Unmapped')
        self.assertFalse(self.payments().reviewed)
        self.assertFalse(FinancialSale.objects.get(code=self.code).reviewed)

    def test_mismatched_total_remains_open(self):
        self.invoices()
        receipt = self.payments(amount='99.00')
        self.assertEqual(receipt.link_issue, 'amount_mismatch')
        self.assertFalse(FinancialSale.objects.get(code=self.code).reviewed)

    def test_explicit_reopen_is_not_relocked_by_repeat_uploads(self):
        self.payments()
        sale = self.invoices()
        self.assertTrue(sale.reviewed)
        response = self.client.post(f'/api/finance/sales/{sale.pk}/reopen/',
                                    {'expected_revision': sale.revision}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(self.invoices().reviewed)
        self.assertFalse(self.payments().reviewed)
        self.assertEqual(SalesEvent.objects.filter(sale=sale, action='routine_auto_review').count(), 1)
