import io
import zipfile
from datetime import date
from unittest.mock import patch
from xml.etree import ElementTree as ET
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .migration_reader import MAPPINGS, read_migration_xlsx
from .models import Company, MigrationImportBatch, MigrationImportRow, BankMovement, FinancialSale

MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def workbook(debits=None,credits=None,epoch1904=False,extra_parts=None):
    """Minimal synthetic XML fixture, not a customer workbook or exported artifact."""
    sheets=[('Debitos',debits if debits is not None else [dict(bank_date='2026-09-09',amount=100,manual_description='Synthetic utility',
        original_description='Synthetic bank detail',expense_period='2026-08-01',category='Services',subcategory='Electricity',location='Studio QA',legacy_reviewed=True)]),
        ('Ingresos',credits if credits is not None else [dict(bank_date='2026-09-04',amount=200,operation_date='2026-09-02',
        balance=1000,payment_method='Cierre',manual_description='Synthetic deposit',terminal='39618800002',location='Studio QA')])]
    files={};wb=ET.Element('workbook',xmlns=MAIN);ET.SubElement(wb,'workbookPr',date1904='1' if epoch1904 else '0');ws=ET.SubElement(wb,'sheets')
    rels=ET.Element('Relationships',xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
    for index,(name,rows) in enumerate(sheets,1):
        ET.SubElement(ws,'sheet',{'name':name,'sheetId':str(index),'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':f'rId{index}'})
        ET.SubElement(rels,'Relationship',Id=f'rId{index}',Target=f'worksheets/sheet{index}.xml',Type='worksheet')
        sheet=ET.Element('worksheet',xmlns=MAIN);data=ET.SubElement(sheet,'sheetData');headers=list(MAPPINGS[name.lower()].items())
        for row_index,values in enumerate([dict(headers)]+rows,1):
            node=ET.SubElement(data,'row',r=str(row_index))
            for column,(field,label) in enumerate(headers,1):
                if field not in values:continue
                value=values[field];attrs={};formula=None;missing=False
                if isinstance(value,dict):attrs=value;value=attrs.get('value');formula=attrs.get('formula');missing=attrs.get('missing',False)
                if value is None and not formula:continue
                col=chr(64+column);kind=attrs.get('type')
                if kind is None:kind='b' if isinstance(value,bool) else 'n' if isinstance(value,(int,float)) else 'd' if field in ('bank_date','operation_date','expense_period') and row_index>1 else 'inlineStr'
                cell=ET.SubElement(node,'c',r=f'{col}{row_index}',t=kind)
                if formula is not None:ET.SubElement(cell,'f').text=formula
                if missing:continue
                if kind=='inlineStr':ET.SubElement(ET.SubElement(cell,'is'),'t').text=str(value)
                else:ET.SubElement(cell,'v').text='1' if value is True else '0' if value is False else str(value) if value is not None else None
        files[f'xl/worksheets/sheet{index}.xml']=ET.tostring(sheet)
    files['xl/workbook.xml']=ET.tostring(wb);files['xl/_rels/workbook.xml.rels']=ET.tostring(rels)
    files.update(extra_parts or {});output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in files.items():archive.writestr(name,content)
    return output.getvalue()


class MigrationReaderTests(SimpleTestCase):
    def test_preserves_manual_period_and_different_operation_date_without_account_guess(self):
        result=read_migration_xlsx(workbook(),'2026-09')
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['summary']['selected_bank_month']['credit_total'],'200.00')
        self.assertEqual(result['summary']['selected_bank_month']['debit_total'],'100.00')
        self.assertEqual(result['summary']['selected_bank_month']['by_kind']['debit']['credit_total'],'0.00')
        self.assertEqual(result['summary']['selected_bank_month']['by_kind']['credit']['rows'],1)
        debit,credit=result['rows']
        self.assertEqual(debit['amount'],'-100.00');self.assertEqual(debit['expense_period'],'2026-08-01')
        self.assertEqual(debit['parsed']['manual_description'],'Synthetic utility');self.assertTrue(debit['parsed']['legacy_reviewed'])
        self.assertEqual(credit['operation_date'],'2026-09-02')
        self.assertEqual(credit['parsed']['terminal'],'39618800002')
        self.assertTrue(all(r['parsed']['payment_origin']=='unknown' for r in result['rows']))
        self.assertEqual(result['summary']['financial_records_created'],0)

    def test_empty_checkbox_rows_ignored_but_classification_only_rows_kept_for_review(self):
        result=read_migration_xlsx(workbook(debits=[{'legacy_reviewed':False},{'legacy_reviewed':True},{'category':1,'subcategory':1}]),'2026-09')
        self.assertEqual(result['summary']['ignored_empty_rows'],2)
        self.assertEqual(len(result['rows']),2)
        orphan=result['rows'][0]
        self.assertIsNone(orphan['bank_date']);self.assertIsNone(orphan['amount'])
        self.assertIn({'code':'invalid_label','field':'category'},orphan['issues'])

    def test_formula_cached_values_errors_and_missing_caches_are_not_evaluated(self):
        rows=[{'bank_date':'2026-09-04','amount':10,'terminal':{'type':'str','formula':'LEFT(B2,11)','value':'39618800002'},
            'location':{'type':'e','formula':'XLOOKUP(H2,Other!A:A,Other!B:B)','value':'#NAME?'}},
            {'bank_date':'2026-09-05','amount':20,'terminal':{'formula':'LEFT(B3,11)','missing':True}},
            {'bank_date':'2026-09-06','amount':30,'terminal':{'type':'str','formula':'IF(TRUE,"",1)','value':''}}]
        result=read_migration_xlsx(workbook(debits=[],credits=rows),'2026-09')
        self.assertEqual(result['summary']['all_rows']['credit_total'],'60.00')
        self.assertIn({'code':'formula_error','field':'location'},result['rows'][0]['issues'])
        self.assertIsNone(result['rows'][0]['parsed']['location'])
        self.assertIn({'code':'formula_cache_missing','field':'terminal'},result['rows'][1]['issues'])
        self.assertNotIn({'code':'formula_cache_missing','field':'terminal'},result['rows'][2]['issues'])
        self.assertTrue(any(c['formula'] for c in result['rows'][0]['raw']))

    def test_numeric_excel_dates_epoch_1904_and_phantom_leap_day(self):
        serial=(date(2026,9,9)-date(1899,12,30)).days
        row={'bank_date':{'type':'n','value':serial},'amount':5}
        result=read_migration_xlsx(workbook(debits=[row],credits=[]),'2026-09')
        self.assertEqual(result['rows'][0]['bank_date'],'2026-09-09')
        row['bank_date']['value']=(date(2026,9,9)-date(1904,1,1)).days
        self.assertEqual(read_migration_xlsx(workbook(debits=[row],credits=[],epoch1904=True),'2026-09')['rows'][0]['bank_date'],'2026-09-09')
        row['bank_date']['value']=60
        self.assertIsNone(read_migration_xlsx(workbook(debits=[row],credits=[]),'2026-09')['rows'][0]['bank_date'])

    def test_invalid_rows_do_not_fabricate_money_or_erase_other_rows(self):
        rows=[{'bank_date':'2026-09-01','amount':0},{'bank_date':'bad','amount':10},
            {'bank_date':'2026-09-02','amount':{'value':'NaN','type':'n'}},{'bank_date':'2026-09-03','amount':-5}]
        result=read_migration_xlsx(workbook(debits=[],credits=rows),'2026-09')
        self.assertEqual(result['summary']['all_rows']['valid_amount_date_rows'],0)
        self.assertEqual(result['summary']['all_rows']['credit_total'],'0.00')
        self.assertEqual(len(result['rows']),4)

    def test_bank_operation_and_expense_month_totals_are_distinct(self):
        result=read_migration_xlsx(workbook(),'2026-09')
        self.assertEqual(result['summary']['expense_period_months']['2026-08']['debit_total'],'100.00')
        self.assertNotIn('2026-09',result['summary']['expense_period_months'])
        self.assertEqual(result['summary']['operation_date_months']['2026-09']['credit_total'],'200.00')

    def test_decimal_noise_normalized_but_substantive_fraction_requires_review(self):
        result=read_migration_xlsx(workbook(debits=[{'bank_date':'2026-09-01','amount':100.00000000001},{'bank_date':'2026-09-01','amount':100.123},{'bank_date':'2026-09-01','amount':{'type':'n','value':'9999999999999999.999999999'}}],credits=[]),'2026-09')
        self.assertEqual(result['rows'][0]['amount'],'-100.00');self.assertIsNone(result['rows'][1]['amount']);self.assertIsNone(result['rows'][2]['amount'])

    def test_bad_zip_macro_dtd_and_limits_fail_with_retained_source_status(self):
        for content in (b'not xlsx',workbook(extra_parts={'xl/vbaProject.bin':b'test'}),workbook(extra_parts={'xl/workbook.xml':b'<!DOCTYPE x [<!ENTITY t "bad">]><workbook />'})):
            result=read_migration_xlsx(content,'2026-09');self.assertTrue(result['file_issues']);self.assertTrue(result['summary']['totals_are_partial'])
        with patch('finance.migration_reader.MAX_ROWS',1):self.assertIn('workbook_limit',read_migration_xlsx(workbook(),'2026-09')['file_issues'])
        with patch('finance.migration_reader.MAX_EXPANDED_BYTES',1):self.assertIn('workbook_limit',read_migration_xlsx(workbook(),'2026-09')['file_issues'])

    def test_duplicate_header_invalid_reference_and_shared_string_are_not_silently_used(self):
        source=workbook();files={}
        with zipfile.ZipFile(io.BytesIO(source)) as archive:files={name:archive.read(name) for name in archive.namelist()}
        part=files['xl/worksheets/sheet1.xml'].replace(b'<t>Monto</t>',b'<t>Fecha</t>')
        self.assertIn('duplicate_header',read_migration_xlsx(workbook(extra_parts={'xl/worksheets/sheet1.xml':part}),'2026-09')['file_issues'])
        part=files['xl/worksheets/sheet1.xml'].replace(b'r="A2"',b'r="A3"')
        self.assertIn('invalid_cell_reference',read_migration_xlsx(workbook(extra_parts={'xl/worksheets/sheet1.xml':part}),'2026-09')['file_issues'])
        result=read_migration_xlsx(workbook(debits=[{'bank_date':'2026-09-01','amount':5,'manual_description':{'value':-1,'type':'s'}}],extra_parts={'xl/sharedStrings.xml':f'<sst xmlns="{MAIN}"><si><t>safe</t></si></sst>'.encode()}),'2026-09')
        self.assertIn('invalid_shared_string',result['file_issues'])


@override_settings(FINANCE_ENABLED=True)
class MigrationAPITests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('migration-preview@example.test');self.profile=get_or_create_user_access_profile(self.user)
        for flag in ('can_view_money','can_view_finance','can_view_sensitive_finance','can_view_finance_bank_accounts','can_import_finance','can_import_finance_migration'):setattr(self.profile,flag,True)
        self.profile.save();self.site=Site.objects.create(name='Migration DO',country_code='DO');self.es=Site.objects.create(name='Migration ES',country_code='ES')
        self.company=Company.objects.create(name='Migration QA',site=self.site,default_currency='DOP');self.spain=Company.objects.create(name='Migration ES QA',site=self.es,default_currency='EUR')
        self.profile.allowed_sites.add(self.site);self.client.force_authenticate(self.user)

    def upload(self,source=None,**values):
        return self.client.post('/api/finance/migration-imports/',{'company':self.company.pk,'month':'2026-09',
            'file':SimpleUploadedFile('synthetic.xlsx',source if source is not None else workbook()),**values},format='multipart')

    def test_immutable_preview_retries_raw_cells_original_and_no_financial_writes(self):
        source=workbook();first=self.upload(source);second=self.upload(source)
        self.assertEqual(first.status_code,201,first.data);self.assertEqual(second.data['duplicate_of'],first.data['id'])
        url=f"/api/finance/migration-imports/{first.data['id']}/"
        rows=self.client.get(url+'rows/');self.assertEqual(rows.data['count'],2)
        self.assertNotIn('raw',rows.data['results'][0]);self.assertNotIn('original_file',first.data)
        row=rows.data['results'][0];detail=self.client.get(url+f"source-row/?row={row['id']}")
        self.assertTrue(detail.data['raw'])
        response=self.client.get(url+'original/');self.assertEqual(b''.join(response.streaming_content),source)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertFalse(BankMovement.objects.exists());self.assertFalse(FinancialSale.objects.exists())
        for method in ('patch','delete'):self.assertEqual(getattr(self.client,method)(url,{},format='json').status_code,405)

    def test_existing_source_display_decodes_dates_text_and_preserves_evidence(self):
        source=workbook(debits=[{'bank_date':{'type':'n','value':46269},'amount':100,
            'manual_description':{'type':'s','value':0},'legacy_reviewed':True,
            'expense_period':{'type':'n','value':46266}}],credits=[],
            extra_parts={'xl/sharedStrings.xml':f'<sst xmlns="{MAIN}"><si><t>Readable utility</t></si></sst>'})
        uploaded=self.upload(source);self.assertEqual(uploaded.status_code,201,uploaded.data)
        batch=MigrationImportBatch.objects.get(pk=uploaded.data['id']);row=batch.rows.get();before=row.raw
        detail=self.client.get(f'/api/finance/migration-imports/{batch.pk}/source-row/?row={row.pk}')
        self.assertEqual(detail.status_code,200,detail.data)
        cells={cell['field']:cell for cell in detail.data['cells']}
        self.assertEqual(cells['bank_date']['readable_value'],'2026-09-04')
        self.assertEqual(cells['expense_period']['readable_value'],'2026-09')
        self.assertEqual(cells['manual_description']['readable_value'],'Readable utility')
        self.assertEqual(cells['manual_description']['reported_value'],'0')
        self.assertEqual(cells['manual_description']['column_label'],'Descripción Original')
        self.assertEqual(cells['amount']['readable_value'],'100.00')
        self.assertIs(cells['legacy_reviewed']['readable_value'],True)
        row.refresh_from_db();batch.refresh_from_db()
        self.assertEqual(row.raw,before);self.assertEqual(detail.data['raw'],before)
        self.assertEqual(bytes(batch.original_file),source)
        self.assertFalse(BankMovement.objects.exists());self.assertFalse(FinancialSale.objects.exists())

    def test_source_display_uses_workbook_epoch_and_keeps_unresolved_formula_evidence(self):
        serial=(date(2026,9,9)-date(1904,1,1)).days
        source=workbook(debits=[],credits=[{'bank_date':{'type':'n','value':serial},'amount':200,
            'location':{'type':'e','formula':'LOOKUP(A2)','value':'#NAME?'},
            'terminal':{'formula':'LEFT(B2,11)','missing':True}}],epoch1904=True)
        uploaded=self.upload(source);row=MigrationImportRow.objects.get(batch_id=uploaded.data['id'])
        detail=self.client.get(f"/api/finance/migration-imports/{uploaded.data['id']}/source-row/?row={row.pk}")
        self.assertEqual(detail.status_code,200,detail.data)
        cells={cell['field']:cell for cell in detail.data['cells']}
        self.assertEqual(cells['bank_date']['readable_value'],'2026-09-09')
        self.assertEqual(cells['location']['readable_value'],'#NAME?')
        self.assertEqual(cells['location']['formula'],'LOOKUP(A2)')
        self.assertIsNone(cells['terminal']['readable_value'])
        self.assertEqual(cells['terminal']['issue'],'formula_cache_missing')

    def test_month_basis_and_all_rows_filters(self):
        response=self.upload();url=f"/api/finance/migration-imports/{response.data['id']}/rows/"
        self.assertEqual(self.client.get(url+'?basis=expense_period').data['count'],0)
        self.assertEqual(self.client.get(url+'?basis=operation_date').data['count'],1)
        self.assertEqual(self.client.get(url+'?scope=all&kind=debit').data['count'],1)
        for query in ('basis=bad','scope=bad','kind=bad'):self.assertEqual(self.client.get(url+'?'+query).status_code,400)

    def test_invalid_date_rows_available_in_all_rows_and_file_failures_retained(self):
        response=self.upload(workbook(debits=[{'bank_date':'bad','amount':5}]))
        url=f"/api/finance/migration-imports/{response.data['id']}/rows/"
        self.assertEqual(self.client.get(url).data['count'],1);self.assertEqual(self.client.get(url+'?scope=all').data['count'],2)
        failed=self.upload(b'invalid');self.assertEqual(failed.status_code,201);self.assertEqual(failed.data['status'],'failed')

    def test_each_required_capability_protects_all_preview_and_original_paths(self):
        response=self.upload();batch=response.data['id'];row=MigrationImportRow.objects.filter(batch_id=batch).first()
        paths=[f'/api/finance/migration-imports/{batch}/',f'/api/finance/migration-imports/{batch}/rows/',
            f'/api/finance/migration-imports/{batch}/source-row/?row={row.pk}',f'/api/finance/migration-imports/{batch}/original/']
        for flag in ('can_view_money','can_view_finance','can_view_sensitive_finance','can_view_finance_bank_accounts'):
            setattr(self.profile,flag,False);self.profile.save()
            for path in paths:self.assertEqual(self.client.get(path).status_code,403,(flag,path))
            setattr(self.profile,flag,True);self.profile.save()
        self.profile.can_import_finance_migration=False;self.profile.save()
        self.assertEqual(self.upload().status_code,403);self.assertEqual(self.client.get(paths[-1]).status_code,403)
        self.assertEqual(self.client.get(paths[1]).status_code,200)

    def test_scope_studio_company_country_and_cross_batch_row_privacy(self):
        first=self.upload();second=self.upload();row=MigrationImportRow.objects.filter(batch_id=second.data['id']).first()
        self.assertEqual(self.client.get(f"/api/finance/migration-imports/{first.data['id']}/source-row/?row={row.pk}").status_code,404)
        self.profile.allowed_sites.add(self.es);self.assertEqual(self.upload(company=self.spain.pk).status_code,400)
        self.profile.allowed_sites.clear();self.assertEqual(self.client.get(f"/api/finance/migration-imports/{first.data['id']}/rows/").status_code,404)
        self.profile.allowed_sites.add(self.site);studio=Studio.objects.create(name='Restricted',site=self.site);self.profile.allowed_studios.add(studio)
        self.assertEqual(self.client.get('/api/finance/migration-imports/companies/').data,[]);self.assertEqual(self.upload().status_code,400)

    def test_limits_month_company_state_and_source_identity_guards(self):
        for month in ('2026-00','2026-13','0000-01','bad'):self.assertEqual(self.upload(month=month).status_code,400)
        self.assertEqual(self.upload(file=SimpleUploadedFile('wrong.csv',b'data')).status_code,400)
        self.assertEqual(self.upload(b'x'*(5*1024*1024+1)).status_code,400)
        self.company.active=False;self.company.save();self.assertEqual(self.upload().status_code,400)
        self.company.active=True;self.company.save();self.upload()
        from django.core.exceptions import ValidationError
        self.company.default_currency='EUR'
        with self.assertRaises(ValidationError):self.company.full_clean()
        self.assertEqual(self.client.get('/api/finance/migration-imports/?company=bad').status_code,400)

    @override_settings(FINANCE_ENABLED=False)
    def test_feature_flag(self):
        self.assertEqual(self.upload().status_code,403);self.assertEqual(self.client.get('/api/finance/migration-imports/companies/').status_code,403)
