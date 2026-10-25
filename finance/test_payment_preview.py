import io
import zipfile
from datetime import date
from unittest.mock import patch
from xml.etree import ElementTree as ET
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from .payment_preview import FIELDS, read_payment_preview
from .models import MigrationImportBatch, FinancialSale, BankMovement
from . import test_migration_imports as migration_tests

workbook=migration_tests.workbook
MAIN=migration_tests.MAIN


def payment_workbook(rows=None,epoch1904=False,omit=(),extra_parts=None):
    """Synthetic source fixture only; never contains customer evidence."""
    if rows is None:
        rows=[{'date':'2026-09-09','number':'101','amount':1200,'associations':'Facturas: B0200005029',
            'kind':'Ingreso','original_method':'Tarjeta crédito','method':'Cierre','location':'Studio QA',
            'source_reviewed':'No','manual_reviewed':True,'cached_invoice':'B0200005029'},
            {'date':'2026-09-09','number':'102','amount':2400,'associations':'Facturas: B0200005029',
            'kind':'Ingreso','original_method':'Efectivo','method':'Efectivo','location':'Studio QA'},
            {'date':'2026-10-02','amount':100,'associations':'Facturas: B0200005000','kind':'Ingreso',
            'original_method':'Tarjeta débito','method':'Link','location':'Studio QA'}]
    original=workbook(epoch1904=epoch1904)
    with zipfile.ZipFile(io.BytesIO(original)) as z:files={n:z.read(n) for n in z.namelist()}
    book=ET.fromstring(files['xl/workbook.xml']);sheets=book.find(f'{{{MAIN}}}sheets')
    ET.SubElement(sheets,f'{{{MAIN}}}sheet',{'name':'Alegra_adm','sheetId':'3',
        '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'rId3'})
    rels=ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    ET.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
        Id='rId3',Target='worksheets/sheet3.xml',Type='worksheet')
    sheet=ET.Element('worksheet',xmlns=MAIN);data=ET.SubElement(sheet,'sheetData')
    fields={k:v for k,v in FIELDS.items() if k not in omit}
    for i,values in enumerate([fields]+rows,1):
        node=ET.SubElement(data,'row',r=str(i))
        for col,(field,label) in enumerate(fields.items(),1):
            if field not in values:continue
            value=values[field];options=value if isinstance(value,dict) else {};value=options.get('value') if options else value
            kind=options.get('type') or ('b' if isinstance(value,bool) else 'n' if isinstance(value,(int,float)) else 'inlineStr')
            cell=ET.SubElement(node,'c',r=f'{chr(64+col)}{i}',t=kind)
            if 'formula' in options:ET.SubElement(cell,'f').text=options['formula']
            if options.get('missing'):continue
            if kind=='inlineStr':ET.SubElement(ET.SubElement(cell,'is'),'t').text=str(value) if value is not None else ''
            else:ET.SubElement(cell,'v').text='1' if value is True else '0' if value is False else str(value) if value is not None else None
    files.update({'xl/workbook.xml':ET.tostring(book),'xl/_rels/workbook.xml.rels':ET.tostring(rels),
        'xl/worksheets/sheet3.xml':ET.tostring(sheet),**(extra_parts or {})})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in files.items():z.writestr(n,v)
    return out.getvalue()


class PaymentReaderTests(SimpleTestCase):
    def test_splits_keep_individual_receipts_and_manual_methods(self):
        result=read_payment_preview(payment_workbook())
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['summary']['amount_total'],'3700.00')
        self.assertEqual(result['summary']['split_invoice_groups'],1)
        self.assertEqual(result['summary']['review_rows'],1)
        a,b,c=result['rows'];self.assertEqual(a['invoice_payment_total'],'3600.00')
        self.assertEqual(b['invoice_payment_rows'],2);self.assertEqual(a['amount'],'1200.00')
        self.assertEqual(a['original_method'],'Tarjeta crédito');self.assertEqual(a['method'],'Cierre')
        self.assertEqual(a['source_reviewed'],'No');self.assertIs(a['manual_reviewed'],True)
        self.assertEqual(a['issues'],[])
        self.assertIn({'code':'missing_payment_number','field':'number'},c['issues'])
        self.assertEqual(result['summary']['financial_records_created'],0)

    def test_original_reference_works_with_missing_derived_ncf_and_number(self):
        row={'date':'2026-09-02','amount':10400,'associations':'Facturas: B0200004842','kind':'Ingreso',
            'original_method':'Tarjeta crédito','method':'Link','location':'Studio QA'}
        result=read_payment_preview(payment_workbook([row]));parsed=result['rows'][0]
        self.assertEqual(parsed['invoice_code'],'B0200004842');self.assertIsNone(parsed['number'])
        self.assertNotIn({'code':'invoice_reference_review','field':'associations'},parsed['issues'])
        self.assertEqual(result['summary']['amount_total'],'10400.00')

    def test_duplicate_numbers_and_unsupported_multiple_references_stay_separate(self):
        rows=[{'date':'2026-09-09','amount':10,'number':'1','kind':'Ingreso','original_method':'Efectivo',
               'associations':'Facturas: B0200005029, B0200005090'},
              {'date':'bad','amount':-5,'number':'1','kind':'Egreso','original_method':'Other',
               'associations':'Facturas: B0200005029; Other invoice 123'}]
        result=read_payment_preview(payment_workbook(rows));self.assertEqual(len(result['rows']),2)
        self.assertEqual(result['summary']['amount_total'],'10.00')
        for r in result['rows']:
            self.assertIsNone(r['invoice_code'])
            self.assertIn({'code':'duplicate_payment_number','field':'number'},r['issues'])
            self.assertIn({'code':'invoice_reference_review','field':'associations'},r['issues'])
        self.assertIsNone(result['rows'][1]['amount']);self.assertIsNone(result['rows'][1]['date'])

    def test_formula_errors_cache_missing_and_reference_conflicts_are_visible(self):
        result=read_payment_preview(payment_workbook([{'date':'2026-09-09','amount':10,'number':'1','kind':'Ingreso',
            'original_method':'Efectivo','associations':'Facturas: B0200005029','cached_invoice':'B0200005090',
            'location':{'type':'e','formula':'LOOKUP(A2)','value':'#NAME?'},
            'method':{'formula':'LOOKUP(B2)','missing':True}}]))
        row=result['rows'][0]
        self.assertEqual(row['invoice_code'],'B0200005029')
        self.assertIn({'code':'invoice_reference_conflict','field':'cached_invoice'},row['issues'])
        self.assertIn({'code':'formula_cache_missing','field':'method'},row['issues'])
        cells={c['column_label']:c for c in row['cells']}
        self.assertEqual(cells['Ubicación']['readable_value'],'#NAME?')
        self.assertEqual(cells['Ubicación']['formula'],'LOOKUP(A2)')
        self.assertIsNone(cells['Metodo']['readable_value'])

    def test_shared_strings_excel_epochs_and_prefilled_checkbox_rows(self):
        for epoch in (False,True):
            serial=(date(2026,9,9)-(date(1904,1,1) if epoch else date(1899,12,30))).days
            result=read_payment_preview(payment_workbook([{'date':{'type':'n','value':serial},'amount':10,
                'number':'001','kind':'Ingreso','associations':{'type':'s','value':0},'original_method':'Efectivo'},
                {'manual_reviewed':False,'cached_invoice':{'formula':'RIGHT(I3,11)','value':''}}],epoch1904=epoch,
                extra_parts={'xl/sharedStrings.xml':f'<sst xmlns="{MAIN}"><si><t>Facturas: B0200005029</t></si></sst>'}))
            self.assertEqual(len(result['rows']),1);self.assertEqual(result['summary']['ignored_empty_rows'],1)
            self.assertEqual(result['rows'][0]['date'],'2026-09-09');self.assertEqual(result['rows'][0]['number'],'001')
            self.assertEqual(result['rows'][0]['invoice_code'],'B0200005029')

    def test_file_validation_fails_closed_and_never_returns_partial_totals(self):
        self.assertEqual(read_payment_preview(workbook())['file_issues'],['missing_payment_sheet'])
        self.assertEqual(read_payment_preview(payment_workbook(omit=['number']))['file_issues'],['missing_payment_header'])
        self.assertEqual(read_payment_preview(b'bad')['file_issues'],['invalid_workbook'])
        for constant,limit in [('MAX_ROWS',1),('MAX_CELLS',1),('MAX_EXPANDED_BYTES',1)]:
            with patch('finance.payment_preview.'+constant,limit):
                result=read_payment_preview(payment_workbook())
                self.assertEqual(result['rows'],[]);self.assertEqual(result['summary']['amount_total'],'0.00')
                self.assertEqual(result['file_issues'],['workbook_limit'])
        malformed=f'<!DOCTYPE worksheet [<!ENTITY x "test">]><worksheet xmlns="{MAIN}"/>'
        self.assertEqual(read_payment_preview(payment_workbook(extra_parts={'xl/worksheets/sheet3.xml':malformed}))['file_issues'],['unsupported_xml'])


class PaymentPreviewAPITests(APITestCase):
    setUp=migration_tests.MigrationAPITests.setUp
    upload=migration_tests.MigrationAPITests.upload

    def test_existing_preview_filters_pagination_and_immutable_no_posting(self):
        content=payment_workbook();uploaded=self.upload(content);self.assertEqual(uploaded.status_code,201)
        batch=MigrationImportBatch.objects.get(pk=uploaded.data['id']);before=list(batch.rows.values())
        url=f'/api/finance/migration-imports/{batch.pk}/payments/'
        response=self.client.get(url);self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['count'],2);self.assertEqual(response.data['filtered_summary']['amount_total'],'3600.00')
        self.assertEqual(response.data['summary']['amount_total'],'3700.00')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(self.client.get(url+'?scope=all').data['count'],3)
        self.assertEqual(self.client.get(url+'?scope=all&review=issues').data['count'],1)
        self.assertEqual(self.client.get(url+'?invoice=B0200005029').data['count'],2)
        self.assertEqual(self.client.get(url+'?scope=all&invoice=B0200005000').data['count'],1)
        for query in ('scope=bad','review=bad','invoice=5029','page=999'):
            self.assertIn(self.client.get(url+'?'+query).status_code,(400,404))
        batch.refresh_from_db();self.assertEqual(bytes(batch.original_file),content)
        self.assertEqual(list(batch.rows.values()),before)
        self.assertEqual(MigrationImportBatch.objects.count(),1)
        self.assertFalse(FinancialSale.objects.exists());self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(self.client.post(url,{}).status_code,405)

    def test_source_privacy_and_scope_before_reading_blob(self):
        uploaded=self.upload(payment_workbook());url=f"/api/finance/migration-imports/{uploaded.data['id']}/payments/"
        for flag in ('can_view_money','can_view_finance','can_view_sensitive_finance','can_view_finance_bank_accounts'):
            setattr(self.profile,flag,False);self.profile.save()
            with patch('finance.migration_views.read_payment_preview') as reader:
                self.assertIn(self.client.get(url).status_code,(403,404));reader.assert_not_called()
            setattr(self.profile,flag,True);self.profile.save()
        self.profile.can_import_finance=False;self.profile.save()
        self.assertEqual(self.client.get(url).status_code,200)
        from core_data.models import Studio
        studio=Studio.objects.create(name='Payment restricted QA',site=self.site)
        self.profile.allowed_studios.add(studio)
        with patch('finance.migration_views.read_payment_preview') as reader:
            self.assertEqual(self.client.get(url).status_code,404);reader.assert_not_called()
        self.profile.allowed_studios.clear()
        self.profile.allowed_sites.clear()
        with patch('finance.migration_views.read_payment_preview') as reader:
            self.assertEqual(self.client.get(url).status_code,404);reader.assert_not_called()

    def test_source_file_without_payment_sheet_has_clear_error(self):
        uploaded=self.upload();response=self.client.get(f"/api/finance/migration-imports/{uploaded.data['id']}/payments/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['file_issues'],['missing_payment_sheet'])
        self.assertEqual(response.data['count'],0)

    def test_page_boundaries_keep_distinct_source_occurrences(self):
        rows=[{'date':'2026-09-09','amount':10,'number':str(i),'kind':'Ingreso','original_method':'Efectivo',
            'associations':'Facturas: B0200005029'} for i in range(17)]
        uploaded=self.upload(payment_workbook(rows));url=f"/api/finance/migration-imports/{uploaded.data['id']}/payments/"
        first=self.client.get(url);second=self.client.get(url+'?page=2')
        self.assertEqual(first.data['count'],17);self.assertEqual(len(first.data['results']),15)
        self.assertEqual(len(second.data['results']),2)
        self.assertEqual(first.data['filtered_summary']['amount_total'],'170.00')
        self.assertFalse({r['source_row'] for r in first.data['results']}&{r['source_row'] for r in second.data['results']})
