import csv
import io
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .alegra_reader import FIELDS, read_alegra_csv
from .models import Company, SalesImportBatch, SalesImportInvoice, SalesImportRow, BankMovement


def report(rows=None, headers=None):
    headers = headers or list(FIELDS.values()) + ['PRODUCTO/SERVICIO - IMPUESTO', 'PRODUCTO/SERVICIO - IMPUESTO']
    defaults = dict(date='01/09/2026', code='B0200000001', status='Cobrada', cost_center='Studio QA',
        payment_method='Tarjeta crédito', price_list='General', customer='Synthetic client', item_name='Synthetic class',
        quantity='1.00', unit_price='100.00', item_total='100.00', invoice_total='100.00')
    output = io.StringIO(newline=''); writer = csv.writer(output, delimiter=';')
    writer.writerow(['sep=', '']); writer.writerow(headers)
    for values in rows if rows is not None else [{}]:
        row = {**defaults, **values}; by_header = {FIELDS[key]: value for key, value in row.items()}
        writer.writerow([by_header.get(header, '') for header in headers])
    return output.getvalue().encode()


class AlegraReaderTests(SimpleTestCase):
    def test_multiple_and_identical_items_count_invoice_total_once(self):
        result = read_alegra_csv(report([{'invoice_total': '200.00'}, {'invoice_total': '200.00'}]))
        self.assertEqual(result['file_issues'], [])
        self.assertEqual(result['summary']['invoice_count'], 1)
        self.assertEqual(result['summary']['item_rows'], 2)
        self.assertEqual(result['summary']['paid_total'], '200.00')
        self.assertEqual(result['invoices'][0]['row_numbers'], [3, 4])
        self.assertEqual(result['invoices'][0]['issues'], [])

    def test_reorder_does_not_change_totals_and_retains_occurrences(self):
        rows = [{'code':'B0100000002'}, {'invoice_total':'200.00'}, {'invoice_total':'200.00'}]
        self.assertEqual(read_alegra_csv(report(rows))['summary'], read_alegra_csv(report(list(reversed(rows))))['summary'])

    def test_incomplete_invoice_never_counts_partial_items(self):
        result = read_alegra_csv(report([{'invoice_total':'200.00'}, {'code':'B0200000002'}]))
        self.assertEqual(result['summary']['paid_total'], '100.00')
        self.assertEqual(result['summary']['review_invoices'], 1)
        self.assertIn('invoice_total_mismatch', result['invoices'][0]['issues'])

    def test_invalid_item_invalidates_whole_invoice_but_not_independent_invoice(self):
        result = read_alegra_csv(report([{'invoice_total':'200.00'}, {'invoice_total':'200.00', 'date':'31/02/2026'}, {'code':'B0200000002'}]))
        self.assertEqual(result['summary']['paid_total'], '100.00')
        self.assertIn('invalid_date', result['invoices'][0]['issues'])
        self.assertIn('inconsistent_date', result['invoices'][0]['issues'])

    def test_unknown_status_and_unverified_cancel_label_are_review_not_paid(self):
        result = read_alegra_csv(report([{'status':'Anulada'}, {'code':'B0200000002','status':'Pendiente'}, {'code':'B0200000003'}]))
        self.assertEqual(result['summary']['paid_total'], '100.00')
        self.assertEqual(result['summary']['review_invoices'], 2)
        self.assertEqual(result['invoices'][0]['source']['status'], 'Anulada')
        self.assertIn('status_requires_review', result['invoices'][0]['issues'])

    def test_disagreeing_invoice_headers_are_not_silently_overwritten(self):
        for key, value in [('invoice_total','201.00'), ('status','Other'), ('payment_method','Efectivo'), ('cost_center','Other'), ('customer','Different synthetic client')]:
            result = read_alegra_csv(report([{'invoice_total':'200.00'}, {'invoice_total':'200.00',key:value}]))
            self.assertEqual(result['summary']['valid_invoices'], 0)
            self.assertIn('inconsistent_' + key, result['invoices'][0]['issues'])

    def test_malformed_amount_and_code_never_fabricate_values(self):
        for fields in [{'item_total':'NaN'}, {'invoice_total':'1,00'}, {'quantity':'Infinity'}, {'unit_price':'-1'}, {'code':''}, {'code':'B020001'}, {'item_total':'-1'}]:
            result = read_alegra_csv(report([fields]))
            self.assertEqual(result['summary']['paid_total'], '0.00', fields)
            self.assertEqual(result['summary']['review_invoices'], 1)

    def test_duplicate_tax_headers_allowed_duplicate_required_columns_rejected(self):
        self.assertEqual(read_alegra_csv(report())['file_issues'], [])
        result = read_alegra_csv(report(headers=list(FIELDS.values()) + [FIELDS['code']]))
        self.assertIn('duplicate_required_header', result['file_issues'])
        self.assertIsNone(result['summary']['paid_total'])

    def test_bad_layout_binary_encoding_and_truncation_are_file_errors(self):
        for content in (b'wrong report', b'\x00binary', report() + b'"unterminated'):
            result = read_alegra_csv(content)
            self.assertTrue(result['file_issues'])
            self.assertIsNone(result['summary']['paid_total'])
        with patch('finance.alegra_reader.MAX_ROWS', 3):
            result = read_alegra_csv(report([{}, {'code':'B0200000002'}]))
            self.assertIn('too_many_rows', result['file_issues'])
            self.assertEqual(result['summary']['valid_invoices'], 0)

    def test_cp1252_bom_and_multiline_source_cells_retained(self):
        source = report([{'item_name':'Clase\nPilátes'}]).decode().encode('cp1252')
        result = read_alegra_csv(source)
        self.assertEqual(result['encoding'], 'cp1252')
        self.assertEqual(result['rows'][-1]['source_line'], 3)
        self.assertEqual(result['rows'][-1]['source_line_end'], 4)
        self.assertEqual(result['rows'][-1]['parsed']['item_name'], 'Clase\nPilátes')
        self.assertEqual(read_alegra_csv(b'\xef\xbb\xbf' + report())['summary']['valid_invoices'], 1)


@override_settings(FINANCE_ENABLED=True)
class SalesPreviewAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('sales-preview@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for key in ('can_view_money','can_view_finance','can_import_finance','can_view_sensitive_finance'):
            setattr(self.profile, key, True)
        self.profile.save()
        self.site = Site.objects.create(name='Sales DO', country_code='DO')
        self.other_site = Site.objects.create(name='Other DO', country_code='DO')
        self.es = Site.objects.create(name='Sales ES', country_code='ES')
        self.company = Company.objects.create(name='Sales QA',site=self.site,default_currency='DOP')
        self.foreign = Company.objects.create(name='Foreign QA',site=self.other_site,default_currency='DOP')
        self.spain = Company.objects.create(name='Spain QA',site=self.es,default_currency='EUR')
        self.profile.allowed_sites.add(self.site)
        self.client.force_authenticate(self.user)

    def upload(self, source=None, company=None, name='sales.csv'):
        return self.client.post('/api/finance/sales-imports/', {'company': company or self.company.pk,
            'file':SimpleUploadedFile(name, report() if source is None else source, content_type='text/csv')}, format='multipart')

    def test_saved_preview_items_raw_original_and_idempotent_financial_effect(self):
        source = report([{'invoice_total':'200.00'},{'invoice_total':'200.00'}])
        first = self.upload(source); second = self.upload(source)
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(second.data['duplicate_of'],first.data['id'])
        self.assertEqual(first.data['summary']['paid_total'],'200.00')
        self.assertEqual(first.data['summary']['financial_records_created'],0)
        self.assertNotIn('original_file',first.data)
        url=f"/api/finance/sales-imports/{first.data['id']}/"
        invoices=self.client.get(url+'invoices/'); self.assertEqual(invoices.data['count'],1)
        invoice_id=invoices.data['results'][0]['id']
        rows=self.client.get(url+f'rows/?invoice={invoice_id}'); self.assertEqual(rows.data['count'],2)
        self.assertEqual(rows.data['results'][0]['source_line'],3)
        original=self.client.get(url+'original/')
        self.assertEqual(b''.join(original.streaming_content),source)
        self.assertEqual(original['Cache-Control'],'private, no-store')
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(SalesImportBatch.objects.count(),2)
        for method in ('patch','delete'):
            self.assertEqual(getattr(self.client,method)(url,{},format='json').status_code,405)

    def test_review_filter_and_failed_file_history(self):
        response=self.upload(report([{'status':'Other'},{'code':'B0200000002'}]))
        result=self.client.get(f"/api/finance/sales-imports/{response.data['id']}/invoices/?kind=review")
        self.assertEqual(result.data['count'],1)
        failed=self.upload(b'wrong format')
        self.assertEqual(failed.status_code,201)
        self.assertEqual(failed.data['status'],'failed')
        self.assertIsNone(failed.data['summary']['paid_total'])

    def test_permission_revocation_protects_all_source_paths(self):
        response=self.upload(); pk=response.data['id']; base=f'/api/finance/sales-imports/{pk}/'
        for flag in ('can_view_money','can_view_finance','can_view_sensitive_finance'):
            setattr(self.profile,flag,False); self.profile.save()
            for suffix in ('','rows/','invoices/','original/'):
                self.assertEqual(self.client.get(base+suffix).status_code,403,(flag,suffix))
            setattr(self.profile,flag,True);self.profile.save()
        self.profile.can_import_finance=False; self.profile.save()
        self.assertEqual(self.upload().status_code,403)
        self.assertEqual(self.client.get(base+'original/').status_code,403)
        self.assertEqual(self.client.get(base+'invoices/').status_code,200)

    def test_site_and_studio_restrictions_no_company_file_leak(self):
        response=self.upload();pk=response.data['id']
        self.assertEqual(self.upload(company=self.foreign.pk).status_code,400)
        self.profile.allowed_sites.clear()
        self.assertEqual(self.client.get(f'/api/finance/sales-imports/{pk}/rows/').status_code,404)
        self.profile.allowed_sites.add(self.site)
        studio=Studio.objects.create(name='Restricted',site=self.site)
        self.profile.allowed_studios.add(studio)
        self.assertEqual(self.client.get('/api/finance/sales-imports/companies/').data,[])
        self.assertEqual(self.client.get(f'/api/finance/sales-imports/{pk}/invoices/').status_code,404)
        self.assertEqual(self.upload().status_code,400)

    def test_company_context_and_inactive_file_type_size_and_bad_query(self):
        self.profile.allowed_sites.add(self.es)
        self.assertEqual(self.upload(company=self.spain.pk).status_code,400)
        self.company.active=False;self.company.save()
        self.assertEqual(self.upload().status_code,400)
        self.company.active=True;self.company.save()
        self.assertEqual(self.upload(name='sales.xlsx').status_code,400)
        self.assertEqual(self.upload(b'x'*(5*1024*1024+1)).status_code,400)
        self.assertEqual(self.client.get('/api/finance/sales-imports/?company=bad').status_code,400)

    def test_invoice_rows_cannot_cross_batch(self):
        first=self.upload();second=self.upload()
        invoice=SalesImportInvoice.objects.get(batch_id=second.data['id'])
        url=f"/api/finance/sales-imports/{first.data['id']}/rows/?invoice={invoice.pk}"
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(SalesImportRow.objects.count(),6)

    @override_settings(FINANCE_ENABLED=False)
    def test_feature_flag_denies_read_and_upload(self):
        self.assertEqual(self.client.get('/api/finance/sales-imports/companies/').status_code,403)
        self.assertEqual(self.upload().status_code,403)

    def test_sales_source_prevents_company_site_or_currency_reinterpretation(self):
        from django.core.exceptions import ValidationError
        self.upload()
        self.company.site=self.other_site
        with self.assertRaises(ValidationError):
            self.company.full_clean()
        self.company.refresh_from_db()
        self.company.default_currency='EUR'
        with self.assertRaises(ValidationError):
            self.company.full_clean()
