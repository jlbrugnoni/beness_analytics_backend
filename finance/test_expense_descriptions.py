"""Fixed workbook headers, legacy interpretation repair, and editable description ownership."""
import io
import zipfile
from datetime import date
from xml.etree import ElementTree as ET
from django.test import SimpleTestCase,override_settings
from rest_framework.test import APITestCase
from django.core.management import call_command
from . import test_migration_imports as migration
from . import test_migration_bank as fixtures
from .migration_reader import read_migration_xlsx,NS
from .migration_descriptions import parsed_business_fields,repair_company
from .migration_bank import bank_source
from .bank_posting import fingerprint,event
from .models import MigrationImportBatch,MigrationImportRow,BankImportBatch,BankImportRow,BankMovement,BankMovementClassification,Category,BankEvent


class ExpenseHeaderTests(SimpleTestCase):
    def test_actual_expense_header_meanings_are_independent_of_column_order(self):
        content=migration.workbook(debits=[{'bank_date':'2026-09-09','amount':100,'original_description':'placeholder bank','manual_description':'placeholder note'}],credits=[])
        with zipfile.ZipFile(io.BytesIO(content)) as archive:parts={name:archive.read(name) for name in archive.namelist()}
        sheet=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        # Literal customer-workbook positions: E = Concepto; G = Descripción Original.
        for cell in sheet.findall('.//s:c',NS):
            values={'E1':'Concepto','G1':'Descripción Original','E2':'BANK RAW CONCEPT','G2':'Owner expense note'}
            if cell.get('r') in values:cell.find('s:is/s:t',NS).text=values[cell.get('r')]
        parts['xl/worksheets/sheet1.xml']=ET.tostring(sheet);output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,value in parts.items():archive.writestr(name,value)
        result=read_migration_xlsx(output.getvalue(),'2026-09')
        self.assertEqual(result['file_issues'],[])
        self.assertEqual(result['rows'][0]['parsed']['original_description'],'BANK RAW CONCEPT')
        self.assertEqual(result['rows'][0]['parsed']['manual_description'],'Owner expense note')


@override_settings(FINANCE_ENABLED=True)
class LegacyExpenseRepairTests(APITestCase):
    setUp=fixtures.HistoricalBankTests.setUp

    def legacy(self):
        migration_batch=MigrationImportBatch.objects.create(company=self.company,selected_month=date(2026,9,1),file_name='legacy.xlsx',file_hash='a'*64,byte_size=8,
            original_file=b'original',parser_version='dr-enriched-xlsx-v1',status='preview')
        row=MigrationImportRow.objects.create(batch=migration_batch,sheet='Debitos',source_row=2,kind='debit',bank_date=date(2026,9,9),amount=-100,
            raw=[{'cell':'E2','value':'BANK RAW CONCEPT'},{'cell':'G2','value':'Owner expense note'}],parsed={'original_description':'Owner expense note','manual_description':'BANK RAW CONCEPT'})
        batch=BankImportBatch.objects.create(account=self.account,provider='popular',file_name='legacy.xlsx',file_hash='a'*64,byte_size=8,original_file=b'original',parser_version='historical-bank-v1',status='preview',migration_batch=migration_batch)
        source={'bank_date':'2026-09-09','amount':'-100.00','direction':'debit','currency':'DOP','description':'Owner expense note','balance':None,'short_description':'','reference':'','serial':''}
        origin=BankImportRow.objects.create(batch=batch,migration_row=row,row_number=1,source_line=2,source_line_end=2,kind='data',parsed=source,raw=row.raw,migration_assignments={'description':'BANK RAW CONCEPT'})
        movement=BankMovement.objects.create(account=self.account,provider='popular',source=source,created_from=origin,fingerprint=fingerprint(source))
        parent=Category.objects.get(company=self.company,name='Services');child=Category.objects.get(parent=parent,name='Electricity')
        BankMovementClassification.objects.create(movement=movement,description='BANK RAW CONCEPT',movement_kind='expense',reviewed=True,category=parent,subcategory=child,studio=self.studio,expense_period=date(2026,9,1))
        event(None,self.user,'create',movement,origin)
        return migration_batch,row,origin,movement

    def test_repair_preserves_source_evidence_financial_values_and_review_with_audit(self):
        batch,row,origin,movement=self.legacy();before=dict(movement.source);raw=list(row.raw)
        self.assertEqual(bank_source(row)['description'],'BANK RAW CONCEPT')
        self.assertEqual(parsed_business_fields(row)['manual_description'],'Owner expense note')
        result=repair_company(self.company,self.user);self.assertEqual(result,{'preview_rows':1,'movements':1})
        movement.refresh_from_db();row.refresh_from_db();origin.refresh_from_db();batch.refresh_from_db()
        self.assertEqual(movement.source,{**before,'description':'BANK RAW CONCEPT'})
        self.assertEqual(movement.classification.description,'Owner expense note');self.assertTrue(movement.classification.reviewed)
        self.assertEqual(row.raw,raw);self.assertEqual(row.parsed['original_description'],'Owner expense note')
        self.assertEqual(bytes(batch.original_file),b'original')
        self.assertEqual(origin.parsed['description'],'BANK RAW CONCEPT')
        self.assertEqual(origin.migration_assignments['description'],'Owner expense note')
        audit=movement.events.get(action='description_interpretation');self.assertEqual(audit.actor_id,self.user.pk)
        self.assertEqual(audit.before['source'],before)
        self.assertEqual(repair_company(self.company,self.user),{})

    def test_preserves_owner_edits_and_does_not_repair_ordinary_reports(self):
        batch,row,origin,movement=self.legacy()
        movement.classification.description='Owner edited note';movement.classification.save()
        repair_company(self.company,self.user);movement.refresh_from_db()
        self.assertEqual(movement.classification.description,'Owner edited note')
        self.assertEqual(movement.source['description'],'BANK RAW CONCEPT')
        origin.batch.migration_batch=None;origin.batch.save(update_fields=['migration_batch'])
        self.assertEqual(repair_company(self.company,self.user),{})

    def test_dry_run_rolls_back_every_change(self):
        batch,row,origin,movement=self.legacy()
        call_command('repair_expense_descriptions',company=self.company.pk,actor=self.user.pk,stdout=io.StringIO())
        movement.refresh_from_db();origin.refresh_from_db()
        self.assertEqual(movement.source['description'],'Owner expense note')
        self.assertEqual(origin.parsed['description'],'Owner expense note')
        self.assertFalse(BankEvent.objects.filter(action='description_interpretation').exists())

    def test_repaired_bank_concept_matches_later_routine_overlap(self):
        from .bank_posting import plan
        batch,row,origin,movement=self.legacy()
        repair_company(self.company,self.user);movement.refresh_from_db()
        routine=BankImportBatch.objects.create(account=self.account,provider='popular',file_name='bank.csv',file_hash='b'*64,byte_size=1,original_file=b'x',parser_version='qa',status='preview',summary={'valid_rows':1})
        BankImportRow.objects.create(batch=routine,row_number=1,source_line=1,source_line_end=1,kind='data',parsed=movement.source,raw=[])
        result=plan(routine,self.account)
        self.assertEqual(result['rows'][0]['outcome'],'ambiguous') # Missing balance still requires review.
        self.assertEqual(result['rows'][0]['candidates'][0]['source']['description'],'BANK RAW CONCEPT')
        movement.source={**movement.source,'balance':'1000.00'};movement.save(update_fields=['source'])
        incoming=routine.rows.get();incoming.parsed=movement.source;incoming.save(update_fields=['parsed'])
        result=plan(routine,self.account)
        self.assertEqual(result['rows'][0]['outcome'],'unchanged')
        self.assertEqual(result['rows'][0]['target'],movement.pk)
