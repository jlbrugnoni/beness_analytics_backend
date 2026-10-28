"""Read-only monthly collections comparison. Never creates matches or writes flags."""
import calendar
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db.models import Q, Exists, OuterRef
from .bank_posting import fingerprint
from .models import BankMovement, FinancialReceipt, FinancialSale, FeePolicy, BankDecision, PaymentDecision

CHANNELS=('card_terminal','transfer','cash','recurring','payment_link')
ZERO=Decimal('0')


def money(value):
    return None if value is None else f'{value.quantize(Decimal(".01"),rounding=ROUND_HALF_UP):.2f}'


def amount(value):
    try:
        result=Decimal(str(value))
        return result if result.is_finite() and result>0 else None
    except (InvalidOperation,ValueError):return None


def month_bounds(month):
    year,number=map(int,month.split('-'))
    return date(year,number,1),date(year,number,calendar.monthrange(year,number)[1])


def estimate(gross,channel,day,policies):
    matches=[p for p in policies if p.channel==channel and (not p.valid_from or p.valid_from<=day) and (not p.valid_until or day<=p.valid_until)]
    if not matches and channel in ('cash','transfer'):return ZERO,None
    if len(matches)!=1:return None,'fee_policy'
    policy=matches[0]
    if policy.deposit_mode=='full':return ZERO,None
    if policy.deposit_mode=='net' and policy.percentage is not None and 0<=policy.percentage<=100:
        return (gross*policy.percentage/Decimal('100')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),None
    return None,'fee_policy'


def compare(company,accounts,month,studio=None):
    start,end=month_bounds(month);days=[date(start.year,start.month,n).isoformat() for n in range(1,end.day+1)]
    grid={ch:{day:{'gross':ZERO,'actual':ZERO,'payments':0,'receipts':0,'review':0} for day in days} for ch in CHANNELS}
    evidence=[];issues=Counter();excluded=Counter()
    def record(side,obj,day,channel,value,studio_id,number,description,reasons,include=True,**extra):
        item={'side':side,'id':obj.pk,'date':day,'channel':channel,'amount':money(value),'studio':studio_id,
            'revision':obj.revision,'source_hash':fingerprint(obj.source),
            'number':number,'description':description,'currency':obj.source.get('currency'),'issues':reasons,'included':include,**extra}
        evidence.append(item)
        for reason in reasons:issues[reason]+=1
        return item
    receipts=FinancialReceipt.objects.filter(company=company,active=True,source__date__gte=start.isoformat(),source__date__lte=end.isoformat()).select_related('sale','created_from__batch','studio','sale__studio','sale__created_from__batch')
    for receipt in receipts:
        sale=receipt.sale;sid=sale.studio_id if sale and receipt.assignments.get('studio_origin')=='invoice' else receipt.studio_id
        if studio and sid!=studio:continue
        source=receipt.source;day=source.get('date');ch=receipt.channel;value=amount(source.get('amount'));reasons=[]
        if receipt.provider!='alegra' or source.get('currency')!=company.default_currency:reasons.append('source_currency')
        if ch not in CHANNELS:reasons.append('payment_method')
        if value is None or day not in days:reasons.append('invalid_facts')
        include=not reasons
        # The payment report is the collection authority. Invoice problems flag
        # review but do not erase a valid posted payment or copy invoice totals.
        if not sale or not sale.active or sale.source.get('status_kind')!='paid' or receipt.link_issue:reasons.append('payment_link')
        if not sid:reasons.append('studio_missing')
        if receipt.assignments.get('channel_review'):reasons.append('method_review')
        if receipt.assignments.get('studio_origin')=='manual_pending':reasons.append('studio_review')
        if sale and sale.assignments.get('requires_review'):reasons.append('invoice_review')
        record('expected',receipt,day,ch,value,sid,receipt.number,source.get('customer') or '',reasons,include,
            sale_id=sale.pk if sale else None,sale_batch=sale.created_from.batch_id if sale else None,
            sale_file_name=sale.created_from.batch.file_name if sale else None,sale_revision=sale.revision if sale else None,invoice=sale.code if sale else source.get('invoice_code'),file_name=receipt.created_from.batch.file_name,
            studio_name=sale.studio.name if sid and sale and receipt.assignments.get('studio_origin')=='invoice' else receipt.studio.name if receipt.studio_id else None)
        if include:
            cell=grid[ch][day];cell['gross']+=value;cell['payments']+=1;cell['review']+=bool(reasons)
    movements=BankMovement.objects.filter(account__in=accounts,active=True,source__direction='credit').filter(
        Q(classification__operation_date__range=(start,end))|Q(classification__operation_date__isnull=True,source__bank_date__gte=start.isoformat(),source__bank_date__lte=end.isoformat())
    ).select_related('account','classification__studio','created_from__batch','historical_row__batch')
    for movement in movements:
        c=getattr(movement,'classification',None);sid=c.studio_id if c else None
        if studio and sid!=studio:continue
        source=movement.source;day=c.operation_date.isoformat() if c and c.operation_date else None;ch=c.channel if c else '';value=amount(source.get('amount'))
        kind=c.movement_kind if c else ''
        if kind in ('internal_transfer','refund','extraordinary'):
            excluded[kind]+=1
            record('actual',movement,day,ch,value,sid,source.get('reference') or source.get('serial') or '',c.description or source.get('description') or '',[],False,excluded_kind=kind,account_name=movement.account.name,bank_date=source.get('bank_date'))
            continue
        reasons=[]
        if not c or kind not in ('','customer_receipt'):reasons.append('movement_type')
        if not day:reasons.append('operation_date')
        if ch not in CHANNELS:reasons.append('payment_method')
        if value is None:reasons.append('invalid_facts')
        if movement.account.currency!=company.default_currency or source.get('currency')!=company.default_currency:reasons.append('source_currency')
        if ch=='cash' and movement.account.kind!='cash':reasons.append('cash_account')
        if movement.account.kind=='cash' and ch!='cash':reasons.append('cash_account')
        include=not reasons
        if not sid:reasons.append('studio_missing')
        if c and not c.reviewed:reasons.append('unreviewed')
        record('actual',movement,day,ch,value,sid,source.get('reference') or source.get('serial') or '',(c.description if c else '') or source.get('description') or '',reasons,include,
            account_name=movement.account.name,studio_name=c.studio.name if sid else None,bank_date=source.get('bank_date'),
            file_name=movement.created_from.batch.file_name if movement.created_from_id else movement.historical_row.batch.file_name if movement.historical_row_id else None)
        if include:
            cell=grid[ch][day];cell['actual']+=value;cell['receipts']+=1;cell['review']+=bool(reasons)
    # Missing payment coverage must not masquerade as a completed comparison.
    linked=FinancialReceipt.objects.filter(sale_id=OuterRef('pk'),active=True)
    sales=FinancialSale.objects.filter(company=company,active=True,source__date__gte=start.isoformat(),source__date__lte=end.isoformat()).select_related('created_from__batch')
    if studio:sales=sales.filter(studio_id=studio)
    for sale in sales.filter(source__status_kind='paid').annotate(has_receipts=Exists(linked)).filter(has_receipts=False):
        record('invoice',sale,sale.source.get('date'),'',amount(sale.source.get('invoice_total')),sale.studio_id,sale.code,
            sale.source.get('customer') or '',['invoice_without_payments'],False,invoice=sale.code,
            file_name=sale.created_from.batch.file_name,batch=sale.created_from.batch_id)
    pending_bank=BankDecision.objects.filter(posting__batch__account__in=accounts,posting__status='active',resolution='pending',
        row__parsed__bank_date__gte=start.isoformat(),row__parsed__bank_date__lte=end.isoformat()).count()
    pending_payments=PaymentDecision.objects.filter(posting__batch__company=company,posting__status='active',resolution='pending',
        row__source__date__gte=start.isoformat(),row__source__date__lte=end.isoformat()).count()
    if pending_bank:issues['pending_bank_import']=pending_bank
    if pending_payments:issues['pending_payment_import']=pending_payments
    policies=list(FeePolicy.objects.filter(company=company,active=True));methods=[]
    for ch in CHANNELS:
        daily=[];gross=actual=fees=known_expected=ZERO;incomplete=False;payments=receipts_count=reviews=0
        for day in days:
            cell=grid[ch][day];fee,problem=estimate(cell['gross'],ch,date.fromisoformat(day),policies) if cell['payments'] else (ZERO,None)
            expected=cell['gross']-fee if fee is not None else None
            if problem:issues[problem]+=1
            gross+=cell['gross'];actual+=cell['actual'];payments+=cell['payments'];receipts_count+=cell['receipts'];reviews+=cell['review']
            incomplete=incomplete or expected is None
            if fee is not None:fees+=fee;known_expected+=expected
            daily.append({'date':day,'gross':money(cell['gross']),'fees':money(fee),'expected':money(expected),'actual':money(cell['actual']),
                'difference':money(cell['actual']-expected) if expected is not None else None,'cumulative_expected':None if incomplete else money(known_expected),
                'cumulative_actual':money(actual),'cumulative_difference':None if incomplete else money(actual-known_expected),
                'payments':cell['payments'],'receipts':cell['receipts'],'review':cell['review'],'fee_issue':bool(problem)})
        methods.append({'channel':ch,'gross':money(gross),'fees':None if incomplete else money(fees),'expected':None if incomplete else money(known_expected),
            'known_expected':money(known_expected),'actual':money(actual),'difference':None if incomplete else money(actual-known_expected),
            'payments':payments,'receipts':receipts_count,'review':reviews,'days':daily})
    return {'company':company.pk,'month':month,'currency':company.default_currency,'supported':True,'methods':methods,
        'issues':dict(issues),'excluded':dict(excluded),'source_coverage_verified':False,'reconciled':False,
        'rounding_basis':'daily_method','difference_basis':'actual_minus_expected'},evidence
