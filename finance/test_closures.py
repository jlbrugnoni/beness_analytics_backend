"""Closure math, dates, evidence and access: no reconciliation state is written."""
import uuid
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.models import Studio
from . import test_migration_imports as fixtures
from .models import (Account,BankMovement,BankMovementClassification,FeePolicy,FinancialReceipt,FinancialSale,
    SalesImportBatch,SalesImportInvoice,PaymentImportBatch,PaymentImportRow,BankEvent,PaymentEvent)


@override_settings(FINANCE_ENABLED=True)
class ClosureTests(APITestCase):
    def setUp(self):
        fixtures.MigrationAPITests.setUp(self)
        self.studio=Studio.objects.create(site=self.site,name='Closure studio')
        self.other_studio=Studio.objects.create(site=self.site,name='Other studio')
        self.cash=Account.objects.create(company=self.company,name='Cash',kind='cash',currency='DOP')
        self.bank=Account.objects.create(company=self.company,name='Bank',currency='DOP')
        self.sb=SalesImportBatch.objects.create(company=self.company,file_name='invoices.csv',file_hash='a'*64,byte_size=1,original_file=b'x',parser_version='qa',status='preview')
        self.pb=PaymentImportBatch.objects.create(company=self.company,file_name='payments.xlsx',file_hash='b'*64,original_file=b'x',parser_version='qa')
        FeePolicy.objects.create(company=self.company,channel='card_terminal',deposit_mode='net',percentage=Decimal('3.5'))

    def receipt(self,number='1',value='100.00',channel='card_terminal',day='2026-09-01',sale=None,**extra):
        if not sale:
            invoice=SalesImportInvoice.objects.create(batch=self.sb,occurrence=FinancialSale.objects.count()+1,code='I'+number,source={},item_count=1,row_numbers=[1],issues=[])
            sale=FinancialSale.objects.create(company=self.company,code='I'+number,created_from=invoice,studio=self.studio,
                source={'date':day,'invoice_total':value,'status_kind':'paid','currency':'DOP'})
        row=PaymentImportRow.objects.create(batch=self.pb,source_row=FinancialReceipt.objects.count()+1,source={})
        return FinancialReceipt.objects.create(company=self.company,number=number,created_from=row,sale=sale,studio=self.studio,
            channel=channel,link_issue='',source={'date':day,'amount':value,'currency':'DOP','invoice_code':sale.code},assignments={'studio_origin':'invoice'},**extra)

    def actual(self,value='96.50',channel='card_terminal',operation='2026-09-01',bank_day='2026-09-03',kind='customer_receipt',studio=None,account=None):
        m=BankMovement.objects.create(account=account or self.bank,provider='manual',manual_key=uuid.uuid4(),fingerprint='x'*64,
            source={'bank_date':bank_day,'amount':value,'currency':'DOP','direction':'credit','description':'Actual receipt'})
        BankMovementClassification.objects.create(movement=m,channel=channel,studio=studio or self.studio,operation_date=operation,movement_kind=kind,reviewed=True)
        return m

    def get(self,month='2026-09',**extra):
        response=self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':month,**extra})
        self.assertEqual(response.status_code,200,response.data);return response.data

    def method(self,data,channel='card_terminal'):
        return next(row for row in data['methods'] if row['channel']==channel)

    def test_month_daily_rounding_split_payments_and_cumulative_conserve_totals(self):
        a=self.receipt(value='0.14');a.sale.source['invoice_total']='0.28';a.sale.save()
        self.receipt(number='2',value='0.14',sale=a.sale)
        self.actual(value='0.27')
        data=self.get();card=self.method(data)
        self.assertEqual(card['gross'],'0.28');self.assertEqual(card['fees'],'0.01');self.assertEqual(card['expected'],'0.27')
        self.assertEqual(card['actual'],'0.27');self.assertEqual(card['difference'],'0.00')
        self.assertEqual(len(card['days']),30);self.assertEqual(card['days'][-1]['cumulative_difference'],'0.00')
        self.assertEqual(self.method(data,'cash')['actual'],'0.00')
        self.assertFalse(data['reconciled']);self.assertFalse(data['source_coverage_verified'])

    def test_operation_date_controls_month_even_when_bank_date_is_later(self):
        self.receipt(day='2026-08-31');self.actual(operation='2026-08-31',bank_day='2026-09-02')
        aug=self.method(self.get('2026-08'));sep=self.method(self.get())
        self.assertEqual(aug['actual'],'96.50');self.assertEqual(len(aug['days']),31);self.assertEqual(sep['actual'],'0.00')
        self.assertEqual(self.method(self.get('2028-02'))['days'][-1]['date'],'2028-02-29')

    def test_cash_is_independent_and_internal_transfers_reimbursements_are_excluded(self):
        self.receipt(channel='cash');cash=self.method(self.get(),'cash')
        self.assertEqual(cash['expected'],'100.00');self.assertEqual(cash['actual'],'0.00')
        self.actual(value='100',channel='cash',account=self.cash)
        for kind in ('internal_transfer','refund','extraordinary'):self.actual(value='100',kind=kind)
        self.actual(value='100',channel='cash') # bank cash credit is not another cash receipt
        data=self.get();self.assertEqual(self.method(data,'cash')['actual'],'100.00')
        self.assertEqual(data['excluded'],{'internal_transfer':1,'refund':1,'extraordinary':1});self.assertEqual(data['issues']['cash_account'],1)

    def test_missing_policy_is_unknown_not_zero_and_effective_dates_are_inclusive(self):
        self.receipt(channel='payment_link');self.assertIsNone(self.method(self.get(),'payment_link')['expected'])
        FeePolicy.objects.create(company=self.company,channel='payment_link',deposit_mode='full',valid_until=date(2026,9,1))
        self.receipt(number='2',channel='payment_link',day='2026-09-02')
        card=self.method(self.get(),'payment_link');self.assertEqual(card['days'][0]['expected'],'100.00');self.assertIsNone(card['days'][1]['expected'])
        self.assertIsNone(card['difference']);self.assertEqual(card['known_expected'],'100.00')

    def test_uncertain_and_missing_assignments_are_visible_and_do_not_fabricate_totals(self):
        r=self.receipt();r.link_issue='invoice_missing';r.save()
        m=self.actual(operation=None);data=self.get()
        self.assertEqual(self.method(data)['gross'],'100.00');self.assertEqual(self.method(data)['actual'],'0.00')
        self.assertEqual(data['issues']['operation_date'],1);self.assertEqual(data['issues']['payment_link'],1)
        response=self.client.get('/api/finance/closures/evidence/',{'company':self.company.pk,'month':'2026-09','side':'review'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['count'],2)
        self.assertIn(m.pk,[x['id'] for x in response.data['results'] if x['side']=='actual'])
        m.classification.operation_date=date(2026,9,1);m.classification.reviewed=False;m.classification.save()
        self.assertEqual(self.method(self.get())['actual'],'96.50') # classified, unreviewed amounts remain visible

    def test_scope_and_permissions_fail_closed_and_spain_is_explicitly_unsupported(self):
        self.receipt();self.actual(studio=self.other_studio)
        self.assertEqual(self.method(self.get(studio=self.studio.pk))['actual'],'0.00')
        for value in ('2026-00','0000-01','2026-13','2026-9'):
            self.assertEqual(self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':value}).status_code,400)
        self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        self.assertEqual(self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':'2026-09'}).status_code,403)
        self.profile.can_view_finance_bank_accounts=True;self.profile.save()
        self.profile.allowed_sites.add(self.es)
        self.assertFalse(self.client.get('/api/finance/closures/',{'company':self.spain.pk,'month':'2026-09'}).data['supported'])
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':'2026-09'}).status_code,404)

    def test_get_is_read_only_and_invoice_cancellation_does_not_erase_a_payment(self):
        r=self.receipt();m=self.actual();before=list(FinancialReceipt.objects.values());before_m=list(BankMovement.objects.values())
        self.get();self.client.get('/api/finance/closures/evidence/',{'company':self.company.pk,'month':'2026-09'})
        self.assertEqual(list(FinancialReceipt.objects.values()),before);self.assertEqual(list(BankMovement.objects.values()),before_m)
        self.assertFalse(BankEvent.objects.exists());self.assertFalse(PaymentEvent.objects.exists())
        r.sale.source['status_kind']='cancelled';r.sale.save();self.assertEqual(self.method(self.get())['expected'],'96.50');self.assertEqual(self.get()['issues']['payment_link'],1)
        self.assertEqual(self.client.post('/api/finance/closures/',{},format='json').status_code,405)

    def test_unlinked_payments_still_count_and_unknown_currency_cannot_be_added_to_dop(self):
        r=self.receipt(channel='cash');r.sale=None;r.link_issue='invoice_missing';r.save()
        data=self.get();self.assertEqual(self.method(data,'cash')['expected'],'100.00')
        self.assertEqual(data['issues']['payment_link'],1)
        r.source['currency']='EUR';r.save();data=self.get()
        self.assertEqual(self.method(data,'cash')['expected'],'0.00');self.assertEqual(data['issues']['source_currency'],1)
        self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.client.get('/api/finance/closures/evidence/',{'company':self.company.pk,'month':'2026-09'}).status_code,403)

    def test_issue_queue_filters_and_refreshes_after_authorized_assignment(self):
        receipt=self.receipt()
        missing=self.actual(operation=None)
        self.actual(operation='2026-09-02')
        params={'company':self.company.pk,'month':'2026-09','side':'review','issue':'operation_date'}
        before=list(BankMovementClassification.objects.values())
        result=self.client.get('/api/finance/closures/evidence/',params)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.data['count'],1)
        self.assertEqual((result.data['results'][0]['side'],result.data['results'][0]['id']),('actual',missing.pk))
        result=self.client.get('/api/finance/closures/evidence/',{**params,'side':'expected'})
        self.assertEqual(result.data['count'],0)
        result=self.client.get('/api/finance/closures/evidence/',{k:v for k,v in params.items() if k not in ('issue','side')})
        expected=next(row for row in result.data['results'] if row['side']=='expected')
        self.assertEqual(expected['sale_id'],receipt.sale_id)
        self.assertEqual(expected['sale_file_name'],self.sb.file_name)
        self.assertEqual(expected['sale_batch'],self.sb.pk)
        self.assertEqual(list(BankMovementClassification.objects.values()),before)
        self.assertEqual(self.client.get('/api/finance/closures/evidence/',{**params,'issue':'unsupported'}).status_code,400)
        self.profile.can_edit_finance=True;self.profile.save()
        response=self.client.post(f'/api/finance/movements/{missing.pk}/assign/',
            {'expected_revision':missing.revision,'operation_date':'2026-09-01'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.client.get('/api/finance/closures/evidence/',params).data['count'],0)
        self.assertEqual(self.method(self.get())['actual'],'193.00')
        missing.refresh_from_db()
        self.assertEqual(missing.source['bank_date'],'2026-09-03')
        self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        self.assertEqual(self.client.get('/api/finance/closures/evidence/',params).status_code,403)
