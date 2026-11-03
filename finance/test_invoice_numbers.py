"""Synthetic regression tests for mixed legacy/electronic invoice identities."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from .alegra_reader import read_alegra_csv
from .models import FinancialReceipt, FinancialSale
from .payment_preview import read_payment_xlsx
from .test_payment_posting import payment_csv
from .test_payment_preview import payment_workbook
from .test_sales_imports import report
from . import test_sales_posting as sales_fixtures
from . import test_migration_imports as migration_fixtures

CODES = ('B0100000001', 'B0200000001', 'E310000000001', 'E320000000001')


class InvoiceNumberReaderTests(SimpleTestCase):
    def test_mixed_series_preserve_full_codes_and_count_separate_invoices(self):
        parsed = read_alegra_csv(report([{'code': code} for code in CODES]))
        self.assertEqual(parsed['file_issues'], [])
        self.assertEqual(parsed['summary']['valid_invoices'], 4)
        self.assertEqual(parsed['summary']['paid_total'], '400.00')
        self.assertEqual([row['code'] for row in parsed['invoices']], list(CODES))

    def test_xlsx_payment_associations_and_cached_codes_support_both_series(self):
        parsed = read_payment_xlsx(payment_workbook([{
            'date': '2026-11-02', 'number': str(index), 'amount': 100,
            'associations': f'Facturas: {code}', 'cached_invoice': code,
            'kind': 'Ingreso', 'original_method': 'Efectivo',
        } for index, code in enumerate(CODES, 1)]))
        self.assertEqual(parsed['file_issues'], [])
        self.assertEqual([row['invoice_code'] for row in parsed['rows']], list(CODES))
        self.assertFalse(any(issue['code'] in ('invoice_reference_review', 'invoice_reference_conflict')
                             for row in parsed['rows'] for issue in row['issues']))

    def test_unsupported_series_wrong_lengths_suffixes_and_non_ascii_digits_rejected(self):
        invalid = ('E300000000001', 'E330000000001', 'E340000000001', 'B0300000001',
                   'E31000000001', 'E3200000000001', 'B01000000001', 'E320000000001-extra',
                   'E32' + '０' * 9 + '１')
        for code in invalid:
            with self.subTest(code=code):
                parsed = read_alegra_csv(report([{'code': code}]))
                self.assertIn('unexpected_invoice_code', parsed['invoices'][0]['issues'])
                parsed = read_payment_xlsx(payment_workbook([{
                    'date': '2026-11-02', 'number': '1', 'amount': 100,
                    'associations': f'Facturas: {code}', 'kind': 'Ingreso',
                }]))
                self.assertIsNone(parsed['rows'][0]['invoice_code'])
                self.assertTrue(any(i['code'] == 'invoice_reference_review' for i in parsed['rows'][0]['issues']))

    def test_multi_invoice_or_trailing_references_are_not_partially_matched(self):
        for association in ('Facturas: E310000000001, E320000000001',
                            'Facturas: B0200000001, E320000000001',
                            'Facturas: E320000000001 additional text'):
            parsed = read_payment_xlsx(payment_workbook([{
                'date': '2026-11-02', 'number': '1', 'amount': 100,
                'associations': association, 'kind': 'Ingreso',
            }]))
            self.assertIsNone(parsed['rows'][0]['invoice_code'])


@override_settings(FINANCE_ENABLED=True)
class MixedInvoiceSeriesPostingTests(APITestCase):
    def setUp(self):
        sales_fixtures.SalesPostingTests.setUp(self)
        self.profile.can_view_finance_bank_accounts = True
        self.profile.save()

    def post_reports(self, payments_first):
        invoices = report([{'code': code, 'customer': 'QA Client', 'date': '09/09/2026'} for code in CODES])
        payments = payment_csv([{'number': str(index), 'amount': '100.00', 'association': f'Facturas: {code}'}
                                for index, code in enumerate(CODES, 1)])
        resources = [('sales-imports', invoices, 'invoices.csv'), ('payment-imports', payments, 'payments.csv')]
        if payments_first:
            resources.reverse()
        for repeat in (False, True):
            for resource, content, filename in resources:
                response = self.client.post(f'/api/finance/{resource}/', {
                    'company': self.company.pk, 'file': SimpleUploadedFile(filename, content),
                }, format='multipart')
                self.assertEqual(response.status_code, 201, response.data)
                batch = response.data['id']
                plan = self.client.get(f'/api/finance/{resource}/{batch}/processing/')
                self.assertEqual(plan.status_code, 200, plan.data)
                self.assertEqual(plan.data['counts'], {'unchanged': 4} if repeat else {'new': 4})
                response = self.client.post(f'/api/finance/{resource}/{batch}/commit/', {
                    'expected_plan': plan.data['token'],
                }, format='json')
                self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(FinancialSale.objects.count(), 4)
        self.assertEqual(FinancialReceipt.objects.count(), 4)
        self.assertEqual(set(FinancialSale.objects.values_list('code', flat=True)), set(CODES))
        for receipt in FinancialReceipt.objects.select_related('sale'):
            self.assertEqual(receipt.sale.code, receipt.source['invoice_code'])
            self.assertEqual(receipt.link_issue, '')

    def test_invoices_first_and_repeated_reports_keep_series_distinct(self):
        self.post_reports(payments_first=False)

    def test_payments_first_and_repeated_reports_link_to_the_correct_full_code(self):
        self.post_reports(payments_first=True)


@override_settings(FINANCE_ENABLED=True)
class ElectronicMigrationFilterTests(APITestCase):
    setUp = migration_fixtures.MigrationAPITests.setUp
    upload = migration_fixtures.MigrationAPITests.upload

    def test_migration_payment_filter_accepts_electronic_invoice_code(self):
        response = self.upload(payment_workbook([{
            'date': '2026-09-09', 'number': '1', 'amount': 100,
            'associations': 'Facturas: E320000000001', 'kind': 'Ingreso',
        }]))
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/finance/migration-imports/{response.data['id']}/payments/"
        response = self.client.get(url, {'scope': 'all', 'invoice': 'E320000000001'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['invoice_code'], 'E320000000001')
        self.assertEqual(self.client.get(url, {'invoice': 'E340000000001'}).status_code, 400)
