"""Explicit identity decisions for complete payments whose source number is absent."""
from uuid import uuid4
from rest_framework.exceptions import ValidationError
from .bank_readers import normalized
from .configuration import ConfigurationConflict
from .models import FinancialReceipt,PaymentDecision


def manual(receipt):return receipt.number.startswith('manual-')


def key(source):
    return (source.get('invoice_code'),source.get('date'),source.get('amount'),source.get('currency'),
        normalized(source.get('customer') or ''),source.get('kind'))


def eligible(source):
    from .payment_posting import FATAL
    if not source.get('customer'):return False
    return not any(i['code'] in FATAL-{'missing_payment_number'} or
        (i['field'] in ('number','date','amount','associations','original_method','kind') and
         i['code'] in ('formula_error','cell_error','formula_cache_missing')) for i in source['issues'])


def index(company,provider):
    rows=list(FinancialReceipt.objects.filter(company=company,provider=provider,active=True))
    numbers={r.number:r for r in rows};by_id={r.pk:r for r in rows}
    # Explicit links to later numbered exports establish aliases without rewriting
    # the original missing-number source or changing the receipt's internal identity.
    for d in PaymentDecision.objects.filter(receipt_id__in=by_id,resolution='identity_linked',
            posting__status__in=['active','partial_undo']).select_related('row'):
        number=d.row.source.get('number')
        if number:
            if number in numbers and numbers[number].pk!=d.receipt_id:raise ConfigurationConflict('Payment identity aliases conflict. Review the sources.')
            numbers[number]=by_id[d.receipt_id]
    groups={}
    for r in rows:
        groups.setdefault(key(r.source),[]).append(r)
        if manual(r):groups.setdefault(('manual_invoice',r.source.get('invoice_code')),[]).append(r)
    return numbers,groups


def candidates(source,groups):
    rows=groups.get(key(source),[])+groups.get(('manual_invoice',source.get('invoice_code')),[])
    return list({r.pk:r for r in rows}.values())


def needed(source,receipt,groups):
    return bool(eligible(source) and ((not source.get('number')) or
        (not receipt and any(manual(r) for r in candidates(source,groups)))))


def resolve(batch,company,actor,row_id,expected,action,receipt_id=None,distinct=False,note=''):
    from . import payment_posting as ops
    posting=getattr(batch,'posting',None)
    if not posting or posting.status!='active':raise ConfigurationConflict('Import valid rows first, then review this payment.')
    decision=PaymentDecision.objects.select_related('row','receipt').filter(posting=posting,row_id=row_id).first()
    if not decision:raise ValidationError('Choose a row from this import.')
    if decision.resolution in ('manual_created','identity_linked'):
        same=(action=='create' and decision.resolution=='manual_created') or (action=='link' and decision.resolution=='identity_linked' and decision.receipt_id==receipt_id)
        if same and decision.receipt and decision.receipt.active:return {'receipt_id':decision.receipt_id,'resolution':decision.resolution}
        raise ConfigurationConflict('This payment identity was already resolved.')
    if expected!=ops.token(company,batch):raise ConfigurationConflict('Payment evidence changed. Refresh the review.')
    source=decision.row.source;numbers,groups=index(company,batch.provider)
    existing=numbers.get(source.get('number'))
    if decision.resolution not in ('invalid','pending') or not needed(source,existing,groups):raise ValidationError('Only complete missing-number payments or their later numbered matches can be reviewed here.')
    matches=candidates(source,groups)
    before={'row_id':row_id,'source':source,'resolution':decision.resolution}
    if action=='link':
        receipt=next((r for r in matches if r.pk==receipt_id),None)
        if not receipt or key(receipt.source)!=key(source):raise ValidationError('Choose a payment with the same invoice, date, customer, currency and amount.')
        if receipt.reconciled:raise ValidationError('Reopen the payment reconciliation before linking another source.')
        if existing and existing.pk!=receipt.pk:raise ConfigurationConflict('That source number already belongs to another payment.')
        decision.resolution='identity_linked'
    elif action=='create':
        from .models import FinancialSale
        sale=FinancialSale.objects.filter(company=company,provider=batch.provider,code=source.get('invoice_code'),active=True).first()
        if sale:
            from .review_workflow import assert_sale_editable
            assert_sale_editable(sale)
        if existing:raise ConfigurationConflict('That source number already exists. Link its payment instead.')
        if matches and not distinct:raise ValidationError('Matching payments exist. Link one or explicitly confirm this is a separate payment.')
        mapping=ops.assignments(company,source)
        from .migration_review import supervised
        if supervised(batch):
            mapping['review_basis']='supervised_migration'
            if mapping['channel']:mapping['channel_review']=False
        snapshot={k:v for k,v in source.items() if k not in ('cells','invoice_payment_total','invoice_payment_rows')}
        receipt=FinancialReceipt.objects.create(company=company,provider=batch.provider,number=source.get('number') or 'manual-'+uuid4().hex,
            source=snapshot,created_from=decision.row,channel=mapping['channel'] or '',studio_id=mapping['studio'],assignments=mapping)
        decision.resolution='manual_created'
    else:raise ValidationError('Choose create or link.')
    decision.receipt=receipt;decision.revision+=1;decision.save(update_fields=['receipt','resolution','revision'])
    posting.revision+=1;posting.save(update_fields=['revision'])
    ops.event(posting,actor,'identity_review',receipt,before,note,
        after={**ops.state(receipt),'row_id':row_id,'resolution':decision.resolution,'distinct_confirmed':distinct})
    ops.refresh_links(company,actor,posting);ops.advance(company)
    return {'receipt_id':receipt.pk,'resolution':decision.resolution}
