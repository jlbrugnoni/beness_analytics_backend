import uuid
from django.test import override_settings
from rest_framework.test import APITestCase
from . import test_mindbody as fixtures
from .models import Account, BankMovement, BankMovementClassification, FeePolicy, ClosureCheckEvent, MindbodySaleAssignment


@override_settings(FINANCE_ENABLED=True)
class SpainClosureTests(APITestCase):
    row=fixtures.MindbodyFinanceTests.row
    report=fixtures.MindbodyFinanceTests.report
    detail=fixtures.MindbodyFinanceTests.detail
    write=fixtures.MindbodyFinanceTests.write

    def setUp(self):
        fixtures.MindbodyFinanceTests.setUp(self)
        self.bank=Account.objects.create(company=self.company,name='Caixa',currency='EUR')
        self.cash=Account.objects.create(company=self.company,name='Cash',kind='cash',currency='EUR')
        FeePolicy.objects.create(company=self.company,channel='card_terminal',deposit_mode='full')

    def summary(self,**filters):
        response=self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':'2026-10',**filters})
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def method(self,channel='card_terminal',**filters):
        return next(r for r in self.summary(**filters)['methods'] if r['channel']==channel)

    def actual(self,amount='50.00',operation='2026-10-06',bank_date='2026-10-08',channel='card_terminal',account=None,kind='customer_receipt',reviewed=True):
        movement=BankMovement.objects.create(account=account or self.bank,provider='manual',manual_key=uuid.uuid4(),fingerprint='qa',
            source={'direction':'credit','amount':amount,'currency':'EUR','bank_date':bank_date,'description':'Receipt'})
        BankMovementClassification.objects.create(movement=movement,operation_date=operation,studio=self.studio,channel=channel,movement_kind=kind,reviewed=reviewed)
        return movement

    def evidence(self,**filters):
        response=self.client.get('/api/finance/closures/evidence/',{'company':self.company.pk,'month':'2026-10',**filters})
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def day(self,channel='card_terminal',day='2026-10-06'):
        return next(d for d in self.method(channel)['days'] if d['date']==day)

    def check(self,channel='card_terminal',day='2026-10-06',**values):
        current=self.day(channel,day)
        return self.client.post('/api/finance/closures/check/',{'company':self.company.pk,'day':day,'channel':channel,
            'expected_revision':current['check']['revision'],'expected_token':current['check_token'],**values},format='json')

    def test_card_gross_settlement_and_cash_actuals_are_independent(self):
        self.report([self.row(),self.row(code='101',amount=20,method='Efectivo')]);self.actual()
        card=self.method();cash=self.method('cash')
        self.assertEqual((card['gross'],card['fees'],card['expected'],card['actual'],card['difference']),('50.00','0.00','50.00','50.00','0.00'))
        self.assertEqual((cash['expected'],cash['actual'],cash['difference']),('20.00','0.00','-20.00'))
        self.actual(amount='20.00',channel='cash',account=self.cash)
        self.assertEqual(self.method('cash')['difference'],'0.00')
        self.assertEqual(len(card['days']),31)
        self.assertEqual(self.summary()['sales_source'],'mindbody')
        self.assertFalse(self.summary()['source_coverage_verified'])
        self.assertFalse(MindbodySaleAssignment.objects.exists())

    def test_operation_dates_across_months_and_unclassified_cash_bank_credit(self):
        self.report([self.row(_sale_date='2026-10-31')]);self.actual(operation='2026-10-31',bank_date='2026-11-02')
        self.actual(amount='100',operation='2026-09-30',bank_date='2026-10-02')
        self.actual(amount='20',operation=None)
        self.actual(amount='30',channel='cash')
        self.assertEqual(self.method()['actual'],'50.00')
        self.assertEqual(self.method('cash')['actual'],'0.00')
        self.assertEqual(self.summary()['issues']['operation_date'],1)
        self.assertEqual(self.summary()['issues']['cash_account'],1)
        self.assertEqual(self.evidence(side='review',issue='operation_date')['count'],1)

    def test_excluded_internal_refund_extraordinary_do_not_count_as_sales(self):
        self.report();self.actual()
        for kind in ('internal_transfer','refund','extraordinary'):
            self.actual(amount='100',kind=kind)
        data=self.summary()
        self.assertEqual(self.method()['actual'],'50.00')
        self.assertEqual(data['excluded'],{'internal_transfer':1,'refund':1,'extraordinary':1})
        self.assertEqual(self.evidence(side='excluded')['count'],3)

    def test_evidence_opens_mindbody_sale_not_alegra_and_filters_by_studio(self):
        self.report();self.actual()
        evidence=self.evidence(side='expected',channel='card_terminal',day='2026-10-06')
        self.assertEqual(evidence['count'],1)
        row=evidence['results'][0]
        self.assertEqual((row['provider'],row['sale_id'],row['invoice']),('mindbody','100','100'))
        self.assertEqual(self.method(studio=self.other_studio.pk)['expected'],'0.00')
        self.assertFalse(self.summary(studio=self.studio.pk)['can_check'])
        self.assertFalse(BankMovement.objects.get().reconciled)

    def test_unknown_source_assignments_are_actionable_without_fabricating_expected_amounts(self):
        self.report([self.row(method='Unmapped')]);self.actual()
        self.assertEqual(self.method()['expected'],'0.00')
        self.assertEqual(self.evidence(side='review',issue='payment_method')['count'],1)
        response=self.write('assign',payments={'unmapped':{'channel':'card_terminal'}})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.method()['expected'],'50.00')
        self.assertEqual(self.write('review').status_code,200)
        self.assertNotIn('invoice_review',self.summary()['issues'])

    def test_check_repeat_source_and_new_source_recheck_with_explicit_reopen(self):
        self.report();self.actual()
        self.assertEqual(self.check().status_code,200)
        self.assertEqual(self.day()['check']['status'],'checked')
        token=self.day()['check_token']
        self.report()
        self.assertEqual(self.day()['check_token'],token)
        self.assertEqual(self.day()['check']['status'],'checked')
        self.report([self.row(amount=60)])
        self.assertEqual(self.day()['check']['status'],'needs_recheck')
        self.assertEqual(self.check(note='Changed source').status_code,400)
        day=self.day()
        payload={'company':self.company.pk,'day':'2026-10-06','channel':'card_terminal','expected_revision':day['check']['revision']}
        self.profile.can_reopen_finance=False;self.profile.save()
        self.assertEqual(self.client.post('/api/finance/closures/reopen/',payload,format='json').status_code,403)
        self.profile.can_reopen_finance=True;self.profile.save()
        self.assertEqual(self.client.post('/api/finance/closures/reopen/',payload,format='json').status_code,200)
        self.assertEqual(self.check(note='Difference investigated').status_code,200)
        self.assertEqual(ClosureCheckEvent.objects.count(),3)

    def test_new_sale_other_day_does_not_invalidate_checked_day_but_manual_method_edit_does(self):
        self.report();self.actual();self.assertEqual(self.check().status_code,200)
        token=self.day()['check_token']
        self.report([self.row(code='101',amount=20,_sale_date='2026-10-07')])
        self.assertEqual(self.day()['check_token'],token)
        self.assertEqual(self.write().status_code,200)
        self.assertEqual(self.write('assign',payments={'card':{'channel':'cash'}}).status_code,200)
        self.assertEqual(self.day()['check']['status'],'needs_recheck')
        self.assertEqual(self.method('cash')['expected'],'50.00')
        self.assertEqual(self.method()['expected'],'20.00')

    def test_missing_fee_policy_does_not_assume_zero_and_access_checks_hold(self):
        self.report();FeePolicy.objects.all().delete()
        self.assertIsNone(self.method()['expected'])
        self.assertEqual(self.check(note='Not enough data').status_code,400)
        self.profile.can_edit_finance=False;self.profile.save()
        self.assertEqual(self.check().status_code,403)
        self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        response=self.client.get('/api/finance/closures/',{'company':self.company.pk,'month':'2026-10'})
        self.assertEqual(response.status_code,403)

    def test_invalid_source_excluded_and_stale_check_token_cannot_be_used(self):
        self.report();self.actual();token=self.day()['check_token']
        self.report([self.row(amount=60)],invalid=True)
        self.assertEqual(self.method()['expected'],'0.00')
        self.assertEqual(self.evidence(side='review',issue='invalid_facts')['count'],1)
        self.assertEqual(self.check(expected_token=token,note='Stale view').status_code,409)
