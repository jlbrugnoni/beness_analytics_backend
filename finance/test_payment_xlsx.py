"""Routine payment XLSX regression fixtures; no customer data or authored deliverable."""
import io
import zipfile
from xml.etree import ElementTree as ET
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from . import test_payment_posting as posting_tests
from .test_payment_preview import payment_workbook
from .payment_preview import read_payment_xlsx
from .models import FinancialReceipt, PaymentImportBatch
from .test_migration_imports import MAIN


def export_xlsx(preamble=True,duplicate=False,extra_parts=None,native=False):
    """Single-sheet export without migration sheets or enriched manual columns."""
    rows=[{'date':{'type':'n','value':46274},'number':101,'amount':1200,'associations':'Facturas: B0200005029',
        'kind':'Ingreso','source_reviewed':'No','original_method':'Tarjeta crédito'},
        {'date':'2026-09-09','number':'102','amount':2400,'associations':'Facturas: B0200005029',
        'kind':'Ingreso','original_method':'Efectivo'}]
    source=payment_workbook(rows,omit=['method','location','manual_reviewed','cached_invoice'])
    with zipfile.ZipFile(io.BytesIO(source)) as z:files={n:z.read(n) for n in z.namelist()}
    book=ET.fromstring(files['xl/workbook.xml']);sheets=book.find(f'{{{MAIN}}}sheets')
    for sheet in list(sheets):
        if sheet.get('name')!='Alegra_adm':sheets.remove(sheet)
        else:sheet.set('name','Reporte de ingresos')
    if duplicate:
        ET.SubElement(sheets,f'{{{MAIN}}}sheet',{'name':'Another payments report','sheetId':'4',
            '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'rId3'})
    sheet=ET.fromstring(files['xl/worksheets/sheet3.xml']);data=sheet.find(f'{{{MAIN}}}sheetData')
    if native:
        labels={'Numero':'Número','ID':'RNC o Cédula','Tipo_nota':'Tipo de nota débito',
            'Conciliada':'Conciliada?','Metodo_pago':'Método de pago'}
        for cell in data[0]:
            for value in cell.iter(f'{{{MAIN}}}t'):
                value.text=labels.get(value.text,value.text)
        # The vendor exports expenses in the same table. They must never post
        # as collections. Their source rows remain available for review.
        from copy import deepcopy
        expense=deepcopy(data[-1]);expense.set('r','4')
        for cell in expense:
            cell.set('r',''.join(c for c in cell.get('r') if c.isalpha())+'4')
            for value in cell.iter(f'{{{MAIN}}}t'):
                if value.text=='Ingreso':value.text='Egreso'
                elif value.text=='102':value.text='B1300000001'
        data.append(expense)
    if preamble:
        for row in data:
            row.set('r',str(int(row.get('r'))+2))
            for cell in row:
                letters=''.join(c for c in cell.get('r') if c.isalpha());cell.set('r',letters+row.get('r'))
        title=ET.Element(f'{{{MAIN}}}row',r='1')
        cell=ET.SubElement(title,f'{{{MAIN}}}c',r='A1',t='inlineStr')
        ET.SubElement(ET.SubElement(cell,f'{{{MAIN}}}is'),f'{{{MAIN}}}t').text='Synthetic payments report'
        data.insert(0,title)
    files.update({'xl/workbook.xml':ET.tostring(book),'xl/worksheets/sheet3.xml':ET.tostring(sheet),**(extra_parts or {})})
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in files.items():z.writestr(n,v)
    return output.getvalue()


class PaymentXLSXReaderTests(SimpleTestCase):
    def test_single_export_detects_sheet_headers_and_excel_dates_without_enrichment(self):
        result=read_payment_xlsx(export_xlsx())
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['parser_version'],'alegra-payment-xlsx-v2')
        self.assertEqual(result['summary']['amount_total'],'3600.00')
        self.assertEqual(result['rows'][0]['sheet'],'Reporte de ingresos')
        self.assertEqual(result['rows'][0]['source_row'],4)
        self.assertEqual(result['rows'][0]['date'],'2026-09-09')
        self.assertIsNone(result['rows'][0]['location']);self.assertIsNone(result['rows'][0]['method'])
        self.assertEqual(result['rows'][0]['invoice_payment_total'],'3600.00')

    def test_native_labels_preserve_evidence_and_hold_expenses(self):
        from .payment_posting import outcome
        result=read_payment_xlsx(export_xlsx(native=True))
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['summary']['amount_total'],'3600.00')
        self.assertEqual(result['rows'][0]['original_method'],'Tarjeta crédito')
        self.assertEqual(result['rows'][0]['source_reviewed'],'No')
        self.assertEqual(result['rows'][-1]['kind'],'egreso')
        self.assertEqual(outcome(result['rows'][-1],None),'invalid')
        self.assertTrue(any(c['column_label']=='Método de pago' for c in result['rows'][0]['cells']))

    def test_existing_workbook_readable_without_renaming_or_conversion(self):
        result=read_payment_xlsx(payment_workbook())
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['summary']['rows'],3)
        self.assertEqual(result['rows'][0]['method'],'Cierre')

    def test_ambiguous_tables_limits_macros_and_malformed_export_fail_closed(self):
        self.assertEqual(read_payment_xlsx(export_xlsx(duplicate=True))['file_issues'],['ambiguous_payment_sheets'])
        self.assertTrue(read_payment_xlsx(b'not xlsx')['file_issues'])
        self.assertEqual(read_payment_xlsx(export_xlsx(extra_parts={'xl/vbaProject.bin':b'unsupported'}))['file_issues'],['unsupported_macros'])
        with patch('finance.payment_preview.MAX_CELLS',1):
            result=read_payment_xlsx(export_xlsx());self.assertEqual(result['file_issues'],['workbook_limit'])
            self.assertEqual(result['rows'],[])


class PaymentXLSXAPITests(APITestCase):
    setUp=posting_tests.ReceiptPostingTests.setUp
    upload=posting_tests.ReceiptPostingTests.upload
    prepare=posting_tests.ReceiptPostingTests.prepare
    plan=posting_tests.ReceiptPostingTests.plan
    commit=posting_tests.ReceiptPostingTests.commit

    def xlsx_batch(self,source):
        response=self.client.post('/api/finance/payment-imports/',{'company':self.company.pk,
            'file':SimpleUploadedFile('Alegra-pagos.xlsx',source,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},format='multipart')
        self.assertEqual(response.status_code,201,response.data);return response.data['id']

    def test_direct_xlsx_uses_shared_receipts_and_keeps_original_bytes(self):
        source=export_xlsx();batch=self.xlsx_batch(source)
        self.assertEqual(self.plan(batch)['counts'],{'new':2})
        self.assertEqual(self.commit(batch).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertFalse(PaymentImportBatch.objects.get(pk=batch).migration_batch_id)
        self.assertEqual(PaymentImportBatch.objects.get(pk=batch).origin,'report')
        original=self.client.get(f'/api/finance/payment-imports/{batch}/original/')
        self.assertEqual(b''.join(original.streaming_content),source)
        repeat=self.xlsx_batch(source);self.assertEqual(self.plan(repeat)['counts'],{'unchanged':2})
        self.assertEqual(self.commit(repeat).status_code,200);self.assertEqual(FinancialReceipt.objects.count(),2)

    def test_routine_xlsx_overlaps_migration_without_erasing_manual_method(self):
        source=payment_workbook();historical=self.prepare(source);self.commit(historical)
        receipt=FinancialReceipt.objects.get(number='101')
        response=self.client.post(f'/api/finance/receipts/{receipt.pk}/assign/',{'expected_revision':receipt.revision,
            'channel':'recurring','note':'Verified recurring'},format='json')
        self.assertEqual(response.status_code,200)
        routine=self.xlsx_batch(source)
        self.assertEqual(self.plan(routine)['counts'],{'unchanged':2,'invalid':1})
        self.assertEqual(self.commit(routine).status_code,200)
        self.assertEqual(FinancialReceipt.objects.count(),2)
        receipt.refresh_from_db();self.assertEqual(receipt.channel,'recurring')

    def test_malformed_xlsx_is_retained_but_cannot_post(self):
        batch=self.xlsx_batch(b'bad workbook');self.assertFalse(self.plan(batch)['can_commit'])
        self.assertEqual(self.commit(batch).status_code,400)
        self.assertFalse(FinancialReceipt.objects.exists())

    def test_reread_failed_native_report_creates_preview_preserving_old_evidence(self):
        source=export_xlsx(native=True)
        with patch('finance.payment_views.read_payment_xlsx',return_value={
                'rows':[],'file_issues':['missing_payment_header'],'parser_version':'alegra-payment-xlsx-v1'}):
            failed=self.xlsx_batch(source)
        response=self.client.post(f'/api/finance/payment-imports/{failed}/reread/',{},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['file_issues'],[])
        self.assertEqual(response.data['duplicate_of'],failed)
        self.assertEqual(self.plan(response.data['id'])['counts'],{'new':2,'invalid':1})
        self.assertEqual(self.plan(response.data['id'])['excluded_rows'],1)
        self.assertEqual(response.data['date_range'],['2026-09-09','2026-09-09'])
        old=PaymentImportBatch.objects.get(pk=failed)
        self.assertEqual(old.file_issues,['missing_payment_header']);self.assertEqual(old.rows.count(),0)
        self.assertEqual(bytes(old.original_file),source)
        self.assertFalse(FinancialReceipt.objects.exists())
        self.assertEqual(self.client.post(f"/api/finance/payment-imports/{response.data['id']}/reread/",{},format='json').status_code,400)
        self.profile.can_import_finance=False;self.profile.save()
        self.assertEqual(self.client.post(f'/api/finance/payment-imports/{failed}/reread/',{},format='json').status_code,403)
