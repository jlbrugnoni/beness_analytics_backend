import csv
import io
import zipfile
from xml.etree import ElementTree as ET
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from .test_payment_preview import payment_workbook, MAIN
from .test_sales_imports import report
from . import test_migration_imports as fixtures
from .alegra_reader import FIELDS
from .migration_sales import read_workbook_sales
from .models import FinancialSale,FinancialReceipt,BankMovement,SalesImportBatch,PaymentImportBatch


def combined(rows=None,broken=False):
    """Synthetic four-sheet source, including a numeric date and legacy headers."""
    payments=[dict(date='2026-09-01',number='101',amount=40,associations='Facturas: B0200000001',kind='Ingreso',original_method='Tarjeta crédito',method='Cierre'),
        dict(date='2026-09-01',number='102',amount=60,associations='Facturas: B0200000001',kind='Ingreso',original_method='Efectivo',method='Efectivo')]
    with zipfile.ZipFile(io.BytesIO(payment_workbook(payments))) as z:parts={n:z.read(n) for n in z.namelist()}
    book=ET.fromstring(parts['xl/workbook.xml']);sheets=book.find(f'{{{MAIN}}}sheets')
    ET.SubElement(sheets,f'{{{MAIN}}}sheet',name='Alegra',sheetId='4',attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'rId4'})
    rel=ET.fromstring(parts['xl/_rels/workbook.xml.rels'])
    ET.SubElement(rel,'Relationship',Id='rId4',Target='worksheets/sheet4.xml')
    values=list(csv.reader(io.StringIO(report(rows).decode()),delimiter=';'))[1:]
    sheet=ET.Element('worksheet',xmlns=MAIN);data=ET.SubElement(sheet,'sheetData')
    def col(n):
        result=''
        while n:n,r=divmod(n-1,26);result=chr(65+r)+result
        return result
    for r,values_row in enumerate(values,1):
        node=ET.SubElement(data,'row',r=str(r))
        for c,value in enumerate(values_row,1):
            if r==1:value=value.replace('Ó','”').replace('É','…')
            options={'r':f'{col(c)}{r}','t':'inlineStr'}
            if r>1 and c==1:options['t']='n';value='46266' # 2026-09-01
            if r>1 and c in (list(FIELDS).index('quantity')+1,list(FIELDS).index('unit_price')+1):
                from decimal import Decimal
                options['t']='n';value=str(Decimal(value).normalize())
            cell=ET.SubElement(node,'c',**options)
            if broken and r==2 and c==8:
                cell.set('t','e');ET.SubElement(cell,'f').text='broken()';ET.SubElement(cell,'v').text='#NAME?'
            elif options['t']=='n':ET.SubElement(cell,'v').text=value
            else:ET.SubElement(ET.SubElement(cell,'is'),'t').text=value
    parts.update({'xl/workbook.xml':ET.tostring(book),'xl/_rels/workbook.xml.rels':ET.tostring(rel),'xl/worksheets/sheet4.xml':ET.tostring(sheet)})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in parts.items():z.writestr(n,v)
    return out.getvalue()


class WorkbookInvoiceReaderTests(SimpleTestCase):
    def test_legacy_headers_numeric_date_items_total_and_source_preserved(self):
        result=read_workbook_sales(combined([{'invoice_total':'200.00'},{'invoice_total':'200.00'}]))
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['summary']['invoice_count'],1)
        self.assertEqual(result['summary']['item_rows'],2)
        self.assertEqual(result['summary']['paid_total'],'200.00')
        self.assertEqual(result['invoices'][0]['source']['date'],'2026-09-01')
        self.assertEqual(result['rows'][1]['parsed']['workbook_cells'][0]['value'],'46266')

    def test_errors_and_missing_sheet_fail_closed(self):
        result=read_workbook_sales(combined(broken=True))
        self.assertEqual(result['summary']['valid_invoices'],0)
        self.assertIn('workbook_cell_error',result['invoices'][0]['issues'])
        self.assertTrue(read_workbook_sales(payment_workbook())['file_issues'])
        self.assertTrue(read_workbook_sales(b'not a workbook')['file_issues'])


class WorkbookAlegraAPITests(APITestCase):
    setUp=fixtures.MigrationAPITests.setUp
    upload=fixtures.MigrationAPITests.upload

    def prepare(self,batch):return self.client.post(f'/api/finance/migration-imports/{batch}/prepare-alegra/',{},format='json')
    def commit(self,kind,batch):
        base=f'/api/finance/{kind}-imports/{batch}/'
        plan=self.client.get(base+'processing/');self.assertEqual(plan.status_code,200,plan.data)
        response=self.client.post(base+'commit/',{'expected_plan':plan.data['token']},format='json')
        self.assertEqual(response.status_code,200,response.data)

    def test_explicit_both_sheet_preparation_is_repeatable_all_dates_and_no_post(self):
        upload=self.upload(combined());self.assertEqual(upload.status_code,201,upload.data)
        batch=upload.data['id'];response=self.client.get(f'/api/finance/migration-imports/{batch}/alegra/')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['invoices']['summary']['invoice_count'],1)
        self.assertEqual(response.data['payments']['summary']['rows'],2)
        prepared=self.prepare(batch);self.assertEqual(prepared.status_code,200,prepared.data)
        sales=prepared.data['sales_batch']['id'];payments=prepared.data['payment_batch']['id']
        self.assertEqual(self.prepare(batch).data['sales_batch']['id'],sales)
        self.assertEqual(self.prepare(batch).data['payment_batch']['id'],payments)
        self.assertEqual(FinancialSale.objects.count(),0);self.assertEqual(FinancialReceipt.objects.count(),0)
        self.commit('sales',sales);self.commit('payment',payments)
        self.assertEqual(FinancialSale.objects.count(),1);self.assertEqual(FinancialReceipt.objects.count(),2)
        self.assertEqual(set(FinancialReceipt.objects.values_list('sale_id',flat=True)),{FinancialSale.objects.get().pk})
        self.assertEqual(BankMovement.objects.count(),0)
        # Repeated imports cannot duplicate sales or receipts.
        self.commit('sales',sales);self.commit('payment',payments)
        self.assertEqual(FinancialSale.objects.count(),1);self.assertEqual(FinancialReceipt.objects.count(),2)
        original=self.client.get(f'/api/finance/sales-imports/{sales}/original/')
        self.assertIn('spreadsheet',original['Content-Type'])

    def test_payments_first_refresh_links_when_invoices_post_and_native_overlap(self):
        batch=self.upload(combined()).data['id'];prepared=self.prepare(batch).data
        self.commit('payment',prepared['payment_batch']['id'])
        self.assertFalse(FinancialReceipt.objects.exclude(sale=None).exists())
        self.commit('sales',prepared['sales_batch']['id'])
        self.assertFalse(FinancialReceipt.objects.filter(sale=None).exists())
        from django.core.files.uploadedfile import SimpleUploadedFile
        normal=self.client.post('/api/finance/sales-imports/',{'company':self.company.pk,'file':SimpleUploadedFile('normal.csv',report())},format='multipart')
        self.assertEqual(normal.status_code,201,normal.data)
        self.assertEqual(self.client.get(f"/api/finance/sales-imports/{normal.data['id']}/processing/").data['counts'],{'unchanged':1})
        self.commit('sales',normal.data['id'])
        self.assertEqual(FinancialSale.objects.count(),1)
        self.assertEqual(self.client.get(f"/api/finance/sales-imports/{normal.data['id']}/processing/").data['counts'],{'linked':1})
        changed=self.client.post('/api/finance/sales-imports/',{'company':self.company.pk,'file':SimpleUploadedFile('changed.csv',report([{'unit_price':'101.00'}]))},format='multipart')
        self.assertEqual(self.client.get(f"/api/finance/sales-imports/{changed.data['id']}/processing/").data['counts'],{'anomaly':1})

    def test_scope_and_permissions(self):
        batch=self.upload(combined()).data['id']
        self.profile.can_import_finance_migration=False;self.profile.save()
        self.assertEqual(self.prepare(batch).status_code,403)
        self.assertFalse(SalesImportBatch.objects.exists());self.assertFalse(PaymentImportBatch.objects.exists())
