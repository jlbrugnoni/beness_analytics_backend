import io
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .bank_readers import read_bank_csv
from .models import Account, BankImportBatch, BankImportRow, Company

POPULAR = '''Bank example
01/09/2026 Hasta 15/09/2026
Fecha Posteo,Descripción Corta,Monto Transacción,Balance ,No. Referencia,No. Serial,Descripción
01/09/2026,Crédito Transferencia,100.00,200.00,,123,Card deposit
01/09/2026,Crédito Transferencia,100.00,200.00,,123,Card deposit

Fecha Posteo,Descripción Corta,Monto Transacción,Balance ,No. Referencia,No. Serial,Descripción
01/09/2026,DB Comisiones,3.50,196.50,,,Transfer fee
'''
CAIXA = 'Concepto;Fecha;Importe;Saldo\nON 369092994 0610;07/10/2026;+121.00EUR;1,121.00EUR\nFee;07/10/2026;-36.00EUR;1,085.00EUR\n'


class BankReaderTests(SimpleTestCase):
    def test_popular_two_sections_preserves_identical_occurrences_and_references(self):
        result = read_bank_csv(POPULAR.encode(), 'popular')
        self.assertEqual(result['file_issues'], [])
        self.assertEqual(result['summary']['valid_rows'], 3)
        self.assertEqual(result['summary']['credit_total'], '200.00')
        self.assertEqual(result['summary']['debit_total'], '3.50')
        self.assertEqual(result['summary']['header_sections'], 2)
        self.assertEqual(result['summary']['repeated_occurrences'], 1)
        rows = [r for r in result['rows'] if r['kind'] == 'data']
        self.assertEqual(rows[0]['parsed']['serial'], '123')
        self.assertEqual(rows[-1]['parsed']['amount'], '-3.50')
        self.assertEqual(rows[0]['source_line'], 4)

    def test_caixa_sign_grouping_and_original_description(self):
        result = read_bank_csv(CAIXA.encode(), 'caixa')
        self.assertEqual(result['summary']['net_total'], '85.00')
        self.assertEqual(result['rows'][1]['parsed']['balance'], '1121.00')
        self.assertEqual(result['rows'][1]['parsed']['description'], 'ON 369092994 0610')
        self.assertNotIn('operation_date', result['rows'][1]['parsed'])

    def test_cp1252_bom_crlf_multiline_csv_and_extra_columns(self):
        content = ('Concepto;Fecha;Importe;Saldo;Extra\r\n"First\r\nsecond";07/10/2026;10.00EUR;;é\r\n').encode('cp1252')
        result = read_bank_csv(content, 'caixa')
        self.assertEqual(result['encoding'], 'cp1252')
        self.assertEqual(result['summary']['valid_rows'], 1)
        self.assertIsNone(result['rows'][1]['parsed']['balance'])
        self.assertEqual(result['rows'][1]['source_line_end'], 3)
        result = read_bank_csv(b'\xef\xbb\xbf' + CAIXA.encode(), 'caixa')
        self.assertEqual(result['summary']['valid_rows'], 2)

    def test_invalid_rows_do_not_drop_valid_ones_or_fabricate_zero(self):
        source = CAIXA + 'Bad date;31/02/2026;1.00EUR;2.00EUR\nBad amount;07/10/2026;1.234,56EUR;1.00EUR\nZero;07/10/2026;0.00EUR;1.00EUR\n'
        result = read_bank_csv(source.encode(), 'caixa')
        self.assertEqual(result['summary']['valid_rows'], 2)
        self.assertEqual(result['summary']['invalid_rows'], 3)
        self.assertEqual([r['issues'][0] for r in result['rows'] if r['issues']], ['invalid_date','invalid_amount','zero_amount'])
        self.assertTrue(all(not r['parsed'] for r in result['rows'] if r['issues']))

    def test_unknown_popular_direction_and_contradictory_negative(self):
        source = POPULAR + '01/09/2026,Other,1.00,2.00,,,Unknown\n01/09/2026,Débito Cuenta,-1.00,2.00,,,Negative\n'
        result = read_bank_csv(source.encode(), 'popular')
        self.assertEqual(result['summary']['invalid_rows'], 2)
        self.assertEqual(result['rows'][-2]['issues'], ['unknown_direction'])
        self.assertEqual(result['rows'][-1]['issues'], ['unexpected_amount_sign'])

    def test_file_errors_and_row_limits(self):
        self.assertIn('missing_header', read_bank_csv(b'not a bank report', 'popular')['file_issues'])
        self.assertIn('binary_or_unsupported_encoding', read_bank_csv(b'\x00text', 'caixa')['file_issues'])
        self.assertIn('no_transactions', read_bank_csv(b'Concepto;Fecha;Importe;Saldo\n','caixa')['file_issues'])
        self.assertIn('invalid_csv', read_bank_csv(b'Concepto;Fecha;Importe;Saldo\n"broken','caixa')['file_issues'])
        with patch('finance.bank_readers.MAX_ROWS', 1):
            self.assertIn('too_many_rows', read_bank_csv(CAIXA.encode(), 'caixa')['file_issues'])

    def test_reordered_rows_have_same_totals_without_chronological_assumption(self):
        lines = CAIXA.splitlines()
        result = read_bank_csv(('\n'.join([lines[0], lines[2], lines[1]])).encode(), 'caixa')
        self.assertEqual(result['summary']['net_total'], '85.00')
        self.assertEqual(result['summary']['first_bank_date'], '2026-10-07')
        self.assertEqual(result['summary']['financial_records_created'], 0)


@override_settings(FINANCE_ENABLED=True)
class BankPreviewAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('bank-preview@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for key in ('can_view_money','can_view_finance','can_import_finance','can_view_finance_bank_accounts','can_view_sensitive_finance'):
            setattr(self.profile, key, True)
        self.profile.save()
        self.site = Site.objects.create(name='DO imports', country_code='DO')
        self.es = Site.objects.create(name='ES imports', country_code='ES')
        self.company = Company.objects.create(name='Bank QA', site=self.site, default_currency='DOP')
        self.spain = Company.objects.create(name='ES QA', site=self.es, default_currency='EUR')
        self.account = Account.objects.create(name='Operating', company=self.company, currency='DOP')
        self.foreign = Account.objects.create(name='Caixa', company=self.spain, currency='EUR')
        self.profile.allowed_sites.add(self.site)
        self.client.force_authenticate(self.user)

    def upload(self, source=POPULAR, **fields):
        return self.client.post('/api/finance/bank-imports/', {'account': self.account.pk, 'provider': 'popular',
            'file': SimpleUploadedFile('bank.csv', source.encode(), content_type='text/csv'), **fields}, format='multipart')

    def test_immutable_history_row_pagination_and_original_bytes(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['summary']['financial_records_created'], 0)
        self.assertNotIn('original_file', response.data)
        batch = BankImportBatch.objects.get()
        self.assertEqual(batch.uploaded_by, self.user)
        self.assertEqual(BankImportRow.objects.filter(batch=batch).count(), 8)
        rows = self.client.get(f'/api/finance/bank-imports/{batch.pk}/rows/')
        self.assertEqual(rows.data['count'], 3)
        all_rows = self.client.get(f'/api/finance/bank-imports/{batch.pk}/rows/?kind=all')
        self.assertEqual(all_rows.data['count'], 8)
        original = self.client.get(f'/api/finance/bank-imports/{batch.pk}/original/')
        self.assertEqual(b''.join(original.streaming_content), POPULAR.encode())
        self.assertEqual(original['Cache-Control'], 'private, no-store')
        self.assertIn('attachment', original['Content-Disposition'])
        self.assertEqual(self.client.patch(f'/api/finance/bank-imports/{batch.pk}/', {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(f'/api/finance/bank-imports/{batch.pk}/').status_code, 405)

    def test_identical_reupload_is_another_preview_not_a_unique_transaction_error(self):
        first = self.upload(); second = self.upload()
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data['duplicate_of'], first.data['id'])
        self.assertEqual(BankImportBatch.objects.count(), 2)
        self.assertEqual(second.data['summary']['valid_rows'], 3)

    def test_invalid_rows_and_failed_files_remain_in_history(self):
        response = self.upload(POPULAR + 'bad,row\n')
        self.assertEqual(response.data['status'], 'preview')
        self.assertEqual(response.data['summary']['invalid_rows'], 1)
        rows = self.client.get(f'/api/finance/bank-imports/{response.data["id"]}/rows/?kind=invalid')
        self.assertEqual(rows.data['count'], 1)
        response = self.upload('Unrecognized layout')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'failed')
        self.assertIn('missing_header', response.data['file_issues'])

    def test_upload_validation_and_account_state(self):
        self.assertEqual(self.upload(file=SimpleUploadedFile('file.xlsx', b'not excel')).status_code, 400)
        self.assertEqual(self.upload(file=SimpleUploadedFile('empty.csv', b'')).status_code, 400)
        self.assertEqual(self.upload(provider='caixa').status_code, 400)
        with patch('finance.import_views.MAX_FILE_BYTES', 5):
            self.assertEqual(self.upload().status_code, 400)
        self.account.active = False; self.account.save()
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(BankImportBatch.objects.count(), 0)

    def test_company_account_foreign_and_partial_studio_scope(self):
        first = self.upload().data['id']
        self.assertEqual(self.upload(account=self.foreign.pk).status_code, 400)
        self.profile.allowed_sites.remove(self.site)
        self.assertEqual(self.client.get('/api/finance/bank-imports/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{first}/rows/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{first}/original/').status_code, 404)
        studio = Studio.objects.create(name='Partial', site=self.site)
        self.profile.allowed_studios.add(studio)
        self.assertEqual(self.upload().status_code, 400)  # shared account not visible
        self.account.studios.add(studio)
        self.assertEqual(self.upload().status_code, 201)

    def test_sensitive_money_bank_feature_and_import_permissions(self):
        first = self.upload().data['id']
        for flag in ('can_view_money','can_view_finance_bank_accounts','can_view_sensitive_finance'):
            setattr(self.profile, flag, False); self.profile.save()
            self.assertEqual(self.client.get('/api/finance/bank-imports/').status_code, 403)
            self.assertEqual(self.client.get(f'/api/finance/bank-imports/{first}/rows/').status_code, 403)
            self.assertEqual(self.upload().status_code, 403)
            setattr(self.profile, flag, True); self.profile.save()
        self.profile.can_import_finance = False; self.profile.save()
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get('/api/finance/bank-imports/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{first}/original/').status_code, 403)
        with override_settings(FINANCE_ENABLED=False):
            self.assertEqual(self.client.get('/api/finance/bank-imports/').status_code, 403)

    def test_caixa_valid_country_and_invalid_filters(self):
        self.profile.allowed_sites.add(self.es)
        result = self.upload(CAIXA, account=self.foreign.pk, provider='caixa')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['summary']['credit_total'], '121.00')
        self.assertEqual(self.client.get('/api/finance/bank-imports/?account=bad').status_code, 400)
        self.assertEqual(self.client.get(f'/api/finance/bank-imports/{result.data["id"]}/rows/?kind=bad').status_code, 400)
