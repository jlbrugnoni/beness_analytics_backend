from decimal import Decimal
from rest_framework.test import APITestCase
from django.test import override_settings
from . import test_closures as fixtures
from .models import ClosureCheck,ClosureCheckEvent,FeePolicy,BankMovement,FinancialReceipt


@override_settings(FINANCE_ENABLED=True)
class OperationalCheckTests(APITestCase):
    receipt=fixtures.ClosureTests.receipt
    actual=fixtures.ClosureTests.actual
    get=fixtures.ClosureTests.get
    method=fixtures.ClosureTests.method
    def setUp(self):
        fixtures.ClosureTests.setUp(self);self.profile.can_reconcile_finance=True;self.profile.save()
        self.receipt();self.movement=self.actual()

    def day(self):return self.method(self.get())['days'][0]
    def check(self,**changes):
        day=self.day()
        payload={'company':self.company.pk,'day':day['date'],'channel':'card_terminal','expected_revision':day['check']['revision'],'expected_token':day['check_token'],**changes}
        return self.client.post('/api/finance/closures/check/',payload,format='json')

    def test_exact_check_is_idempotent_and_never_changes_financial_records(self):
        before=list(BankMovement.objects.values());before_r=list(FinancialReceipt.objects.values())
        self.assertEqual(self.check().status_code,200);self.assertEqual(self.day()['check']['status'],'checked')
        self.assertEqual(self.check().status_code,200);self.assertEqual(ClosureCheckEvent.objects.count(),1)
        self.assertEqual(list(BankMovement.objects.values()),before);self.assertEqual(list(FinancialReceipt.objects.values()),before_r)
        self.assertFalse(self.movement.reconciled)
        history=self.client.get('/api/finance/closures/history/',{'company':self.company.pk,'month':'2026-09','day':'2026-09-01','channel':'card_terminal'})
        self.assertEqual(history.status_code,200);self.assertEqual(history.data['count'],1)

    def test_difference_requires_reason_and_changed_source_reopens_review_without_erasing_history(self):
        self.movement.source['amount']='95.00';self.movement.save()
        self.assertEqual(self.check().status_code,400)
        self.assertEqual(self.check(note='Deposit difference under investigation').status_code,200)
        self.movement.source['amount']='96.00';self.movement.save() # Even a missing revision bump cannot hide changed facts.
        self.assertEqual(self.day()['check']['status'],'needs_recheck')
        self.assertEqual(self.check(note='Updated receipt reviewed').status_code,200)
        self.assertEqual(ClosureCheckEvent.objects.count(),2);self.assertEqual(self.day()['check']['status'],'checked')

    def test_stale_tokens_permissions_and_studio_scope_fail_closed(self):
        old=self.day()['check_token'];self.receipt(number='2')
        self.assertEqual(self.check(expected_token=old,note='Stale').status_code,409)
        self.profile.can_reconcile_finance=False;self.profile.save();self.assertEqual(self.check(note='Not allowed').status_code,403)
        self.profile.can_reconcile_finance=True;self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        response=self.client.post('/api/finance/closures/check/',{'company':self.company.pk,'day':'2026-09-01','channel':'card_terminal','expected_revision':0,'expected_token':old},format='json')
        self.assertEqual(response.status_code,403);self.assertFalse(ClosureCheck.objects.exists())

    def test_reopen_is_audited_and_fee_changes_stale_even_when_rounding_is_equal(self):
        self.check();old=self.day()
        policy=FeePolicy.objects.get(company=self.company,channel='card_terminal');policy.percentage=Decimal('3.5001');policy.save()
        self.assertEqual(self.day()['check']['status'],'needs_recheck')
        body={'company':self.company.pk,'day':'2026-09-01','channel':'card_terminal','expected_revision':old['check']['revision'],'note':'Review configuration'}
        r=self.client.post('/api/finance/closures/reopen/',body,format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.day()['check']['status'],'open');self.assertEqual(ClosureCheckEvent.objects.first().action,'reopen')
        self.assertEqual(self.client.post('/api/finance/closures/reopen/',body,format='json').status_code,409)

    def test_other_day_does_not_invalidate_check_and_studio_view_cannot_confirm_company(self):
        self.check();self.receipt(number='2',day='2026-09-02')
        self.assertEqual(self.day()['check']['status'],'checked')
        data=self.get(studio=self.studio.pk);self.assertFalse(data['can_check'])
        self.assertEqual(self.method(data)['days'][0]['check']['status'],'company_scope')
