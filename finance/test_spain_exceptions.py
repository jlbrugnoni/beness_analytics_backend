"""Operational exception rehearsals through the existing Analytics importer/API."""
from datetime import date
import uuid
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.importers import SALES_REQUIRED_HEADERS, import_sales_report
from core_data.test_analytics_import_guards import xlsx_upload
from . import test_spain_closures as fixtures
from .models import BankMovement, BankMovementClassification, Category


@override_settings(FINANCE_ENABLED=True)
class SpainExceptionTests(APITestCase):
    setUp=fixtures.SpainClosureTests.setUp
    row=fixtures.SpainClosureTests.row
    report=fixtures.SpainClosureTests.report
    summary=fixtures.SpainClosureTests.summary
    method=fixtures.SpainClosureTests.method
    actual=fixtures.SpainClosureTests.actual
    evidence=fixtures.SpainClosureTests.evidence
    detail=fixtures.SpainClosureTests.detail
    write=fixtures.SpainClosureTests.write

    def export(self, payments, code='301', day=date(2026,10,9), total='165.00'):
        # Same layout observed in the real April9/sale301 export, with synthetic
        # customer details. Date defaults to October to share the test comparison.
        rows=[]
        for method,paid in payments:
            p={header:'' for header in SALES_REQUIRED_HEADERS}
            p.update({'Fecha de Venta':(day-date(1899,12,30)).days,'ID del Cliente':'12',
                'Cliente':'Synthetic exception client','No. de Venta':code,'Nombre del artículo':'Membership',
                'Localidad':self.studio.name,'Precio del artículo (excluyendo impuestos)':total,
                'Cantidad':1,'Sub-total (excluyendo impuestos)':total,'Descuento en %':0,
                'Cantidad de descuento':0,'Impuesto':0,'Total de artículos':total,
                'Total Pagado con Método de Pago':paid,'Forma de Pago':method})
            rows.append([p[h] for h in SALES_REQUIRED_HEADERS])
        return xlsx_upload('synthetic-spain-exceptions.xlsx',SALES_REQUIRED_HEADERS,rows)

    def test_native_import_split_sale_is_one_item_and_methods_close_independently(self):
        import_sales_report(self.export([('Efectivo','5.00'),('Card','160.00')]),self.site,self.user)
        sale=self.detail('301').data
        self.assertEqual(sale['source']['invoice_total'],'165.00')
        self.assertEqual(len(sale['items']),1)
        self.assertEqual({(p['channel'],p['amount']) for p in sale['payments']},{('cash','5.00'),('card_terminal','160.00')})
        self.actual(amount='160',operation='2026-10-09')
        self.actual(amount='5',operation='2026-10-09',channel='cash',account=self.cash)
        self.assertEqual(self.method()['difference'],'0.00')
        self.assertEqual(self.method('cash')['difference'],'0.00')
        token=sale['token']
        # A later correction changes one payment slice; neither the old Analytics
        # row identity nor the previous payment group can add another collection.
        import_sales_report(self.export([('Efectivo','10.00'),('Card','155.00')]),self.site,self.user)
        changed=self.detail('301').data
        self.assertNotEqual(changed['token'],token)
        self.assertTrue(changed['source_changed']);self.assertTrue(changed['locked'])
        self.assertEqual(changed['source']['invoice_total'],'165.00')
        self.assertEqual(self.method()['expected'],'155.00')
        self.assertEqual(self.method('cash')['expected'],'10.00')
        import_sales_report(self.export([('Efectivo','10.00'),('Card','155.00')]),self.site,self.user)
        self.assertEqual(self.detail('301').data['token'],changed['token'])
        self.assertEqual(self.method()['expected'],'155.00')

    def test_native_import_negative_refund_is_preserved_pending_and_not_positive_income(self):
        import_sales_report(self.export([('Card','-165.00')],code='refund-test',total='-165.00'),self.site,self.user)
        sale=self.detail('refund-test').data
        self.assertEqual(sale['source']['paid_total'],'-165.00')
        self.assertIn('refund_requires_review',sale['missing_fields'])
        self.assertFalse(sale['reviewed'])
        self.assertEqual(self.method()['expected'],'0.00')
        self.assertEqual(self.evidence(side='review',issue='invalid_facts')['count'],1)
        self.assertEqual(self.write('review',code='refund-test').status_code,400)
        # This is a deliberate pending exception, not validated refund accounting.

    def test_separate_terminal_charge_and_reimbursement_preserve_both_records(self):
        self.report([self.row(amount=160)])
        self.actual(amount='160')
        fee=BankMovement.objects.create(account=self.bank,provider='manual',manual_key=uuid.uuid4(),fingerprint='fee',
            source={'direction':'debit','amount':'-36.00','currency':'EUR','bank_date':'2026-10-07','description':'Terminal fee'})
        category=Category.objects.create(company=self.company,name='Bank fees')
        BankMovementClassification.objects.create(movement=fee,category=category,studio=self.studio,
            expense_period='2026-10-01',movement_kind='expense',reviewed=True)
        reimbursement=self.actual(amount='36.00',kind='refund')
        card=self.method()
        self.assertEqual((card['gross'],card['fees'],card['actual'],card['difference']),('160.00','0.00','160.00','0.00'))
        self.assertEqual(self.summary()['excluded'],{'refund':1})
        self.assertTrue(BankMovement.objects.filter(pk=fee.pk,active=True).exists())
        self.assertTrue(BankMovement.objects.filter(pk=reimbursement.pk,active=True).exists())

    def test_customer_cash_receipt_and_later_bank_deposit_are_not_double_counted(self):
        self.report([self.row(amount=100,method='Efectivo')])
        receipt=self.actual(amount='100',channel='cash',account=self.cash)
        deposit=self.actual(amount='100',channel='cash',kind='internal_transfer')
        cash=self.method('cash')
        self.assertEqual((cash['expected'],cash['actual'],cash['difference']),('100.00','100.00','0.00'))
        self.assertEqual(self.method()['actual'],'0.00')
        self.assertEqual(self.summary()['excluded'],{'internal_transfer':1})
        self.assertEqual(self.evidence(side='excluded')['results'][0]['id'],deposit.pk)
        self.assertFalse(BankMovement.objects.get(pk=receipt.pk).reconciled)
