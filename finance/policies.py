"""Dated configuration resolution; no financial records are created here."""
from decimal import Decimal, ROUND_HALF_UP
from .models import FeePolicy, SettlementPolicy, TaxProfile


def policy_at(model, company, date, **filters):
    from django.db.models import Q
    return model.objects.filter(company=company, active=True, **filters).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=date)).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=date)).first()


def preview_policies(company, date, channel, amount):
    fee = policy_at(FeePolicy, company, date, channel=channel)
    settlement = policy_at(SettlementPolicy, company, date, channel=channel)
    tax = policy_at(TaxProfile, company, date)
    money = lambda value: str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    ref = lambda rule: {'id': rule.pk, 'revision': rule.revision} if rule else None
    withheld = None
    if fee and fee.deposit_mode == 'full':
        withheld = Decimal('0')
    elif fee and fee.deposit_mode == 'net' and fee.percentage is not None:
        withheld = amount * fee.percentage / Decimal('100')
    tax_amount = None
    if tax and tax.treatment in ('no_tax', 'exempt'):
        tax_amount = Decimal('0')
    elif tax and tax.treatment == 'inclusive' and tax.rate is not None:
        tax_amount = amount - amount / (1 + tax.rate / Decimal('100'))
    return {
        'currency': company.default_currency, 'gross_amount': money(amount),
        'fee_policy': ref(fee), 'deposit_mode': fee.deposit_mode if fee else 'unknown',
        'estimated_withheld_fee': money(withheld) if withheld is not None else None,
        'estimated_deposit': money(amount - Decimal(money(withheld))) if withheld is not None else None,
        'separate_fee_amount': str(fee.separate_fee_amount) if fee and fee.separate_fee_amount is not None else None,
        'separate_fee_frequency': fee.separate_fee_frequency if fee else 'unknown',
        'tax_profile': ref(tax), 'tax_treatment': tax.treatment if tax else 'unknown',
        'included_tax': money(tax_amount) if tax_amount is not None else None,
        'result_basis': 'tax_inclusive',
        'settlement_policy': ref(settlement),
        'settlement': {'minimum_hours': settlement.minimum_hours, 'maximum_hours': settlement.maximum_hours,
                       'weekend_delays': settlement.weekend_delays} if settlement else None,
        'requires_review': withheld is None or tax_amount is None,
    }
