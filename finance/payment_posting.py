"""Shared receipt operations. Callers hold the company lock and check source privacy."""
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from rest_framework import serializers
from core_data.models import Studio
from .bank_readers import normalized
from .configuration import ConfigurationConflict
from .mapping import resolve_source_values
from .models import FinancialReceipt, FinancialSale, PaymentPosting, PaymentDecision, PaymentEvent

VERSION='alegra-receipts-v1'
CHANNELS={'cierre':'card_terminal','recurrente':'recurring','link':'payment_link','transferencia':'transfer','efectivo':'cash'}
FATAL={'currency_review','invalid_date','invalid_amount','missing_payment_number','invalid_payment_number','duplicate_payment_number',
       'unsupported_payment_kind','payment_status_review','invoice_reference_review','invoice_reference_conflict'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def token(company,batch,purpose='plan'):
    rules=list(company.source_mappings.order_by('pk').values_list('pk','revision'))
    return digest([VERSION,company.pk,company.payment_revision,company.sales_revision,company.revision,rules,batch.pk,purpose])


def advance(company):
    company.payment_revision+=1;company.save(update_fields=['payment_revision'])


def facts(source):
    return {k:source.get(k) for k in ('number','date','amount','currency','invoice_code','kind','original_method','account','customer','customer_id')}


def state(receipt):
    return {'id':receipt.pk,'number':receipt.number,'source':receipt.source,'sale':receipt.sale_id,
        'link_issue':receipt.link_issue,'channel':receipt.channel,'studio':receipt.studio_id,
        'assignments':receipt.assignments,'revision':receipt.revision,'active':receipt.active,
        'edited':receipt.edited,'reconciled':receipt.reconciled}


def event(posting,actor,action,receipt=None,before=None,note='',after=None):
    PaymentEvent.objects.create(posting=posting,actor=actor,action=action,receipt=receipt,
        before=before or {},after=state(receipt) if receipt else after or {},note=note)


def assignments(company,source):
    mapping=resolve_source_values(company,'alegra',{'payment_method':source.get('original_method') or ''})
    channel=CHANNELS.get(normalized(source.get('method') or ''))
    result={'channel':channel or mapping['channel'],'channel_origin':'manual' if channel else 'rule',
        'channel_review':not bool(channel) and ('channel_requires_review' in mapping['review_reasons']),
        'studio_label':source.get('location'),'studio_origin':'invoice','studio':None}
    if source.get('location'):
        matches=[s.pk for s in Studio.objects.filter(site_id=company.site_id) if normalized(s.name)==normalized(source['location'])]
        result.update(studio=matches[0] if len(matches)==1 else None,studio_origin='manual' if len(matches)==1 else 'manual_pending')
    return result


def outcome(source,receipt):
    if any(i['code'] in FATAL or (i['field'] in ('number','date','amount','associations','original_method','kind') and i['code'] in ('formula_error','cell_error','formula_cache_missing')) for i in source['issues']):return 'invalid'
    if not source.get('number') or len(source['number'])>64:return 'invalid'
    if not receipt:return 'new'
    if facts(source)!=facts(receipt.source):return 'conflict'
    for field in ('method','location'):
        if source.get(field) and source[field]!=receipt.source.get(field):return 'assignment_conflict'
    return 'unchanged'


def plan(batch,company):
    posting=PaymentPosting.objects.filter(batch=batch).first()
    receipts={r.number:r for r in FinancialReceipt.objects.filter(company=company,provider=batch.provider,active=True)}
    decisions={d.row_id:d for d in posting.decisions.select_related('receipt')} if posting else {}
    rows=[];counts=Counter()
    for row in batch.rows.all():
        receipt=receipts.get(row.source.get('number'));decision=decisions.get(row.pk)
        status=outcome(row.source,receipt);counts[decision.resolution if decision else status]+=1
        rows.append({'row_id':row.pk,'source_row':row.source_row,'number':row.source.get('number'),
            'date':row.source.get('date'),'amount':row.source.get('amount'),'invoice_code':row.source.get('invoice_code'),
            'kind':row.source.get('kind'),'customer':row.source.get('customer'),
            'method':row.source.get('method'),'original_method':row.source.get('original_method'),
            'location':row.source.get('location'),'issues':row.source['issues'],'outcome':status,
            'decision_id':decision.pk if decision else None,'decision_revision':decision.revision if decision else None,
            'resolution':decision.resolution if decision else None,'receipt':state(receipt) if receipt else None})
    return {'token':token(company,batch),'counts':dict(counts),'rows':rows,'posting':posting}


def refresh_links(company,actor,posting=None):
    """Exact invoice links; no bank matching, synthetic sale or revenue change."""
    receipts=list(FinancialReceipt.objects.filter(company=company,active=True).select_related('sale').order_by('pk'))
    sales={(s.provider,s.code):s for s in FinancialSale.objects.filter(company=company,active=True)}
    totals=defaultdict(Decimal)
    # Existing allocations take priority; a new overpayment cannot detach them.
    for r in receipts:
        if r.sale_id:totals[r.sale_id]+=Decimal(r.source['amount'])
    changed=False
    for r in receipts:
        before=state(r);sale=r.sale
        if sale:
            issue='invoice_inactive' if not sale.active else 'invoice_cancelled' if sale.source.get('status_kind')=='cancelled' else 'invoice_status_review' if sale.source.get('status_kind')!='paid' else 'overallocated' if totals[sale.pk]>Decimal(sale.source['invoice_total']) else ''
        else:
            candidate=sales.get((r.provider,r.source['invoice_code']))
            if not candidate:issue='invoice_missing'
            elif candidate.source.get('status_kind')!='paid':issue='invoice_cancelled' if candidate.source.get('status_kind')=='cancelled' else 'invoice_status_review'
            elif r.source.get('customer') and candidate.source.get('customer') and normalized(r.source['customer'])!=normalized(candidate.source['customer']):issue='customer_conflict'
            elif totals[candidate.pk]+Decimal(r.source['amount'])>Decimal(candidate.source['invoice_total']):issue='overallocated'
            else:r.sale=candidate;totals[candidate.pk]+=Decimal(r.source['amount']);issue=''
        r.link_issue=issue
        if before['sale']!=r.sale_id or before['link_issue']!=issue:
            r.revision+=1;r.save(update_fields=['sale','link_issue','revision'])
            event(posting,actor,'invoice_link_review' if issue else 'invoice_link',r,before);changed=True
    if changed:advance(company)


def commit(batch,company,actor,expected):
    posting=PaymentPosting.objects.filter(batch=batch).first()
    if posting:
        if posting.status=='active':return posting
        raise ConfigurationConflict('Prepare a fresh source import after undo.')
    if expected!=token(company,batch):raise ConfigurationConflict('Payments, sales or mappings changed. Reload the plan.')
    if batch.file_issues or not batch.rows.exists():raise serializers.ValidationError('An empty or failed source cannot be posted.')
    posting=PaymentPosting.objects.create(batch=batch,actor=actor)
    for row in batch.rows.all():
        source=row.source;receipt=FinancialReceipt.objects.filter(company=company,provider=batch.provider,number=source.get('number'),active=True).first()
        status=outcome(source,receipt);resolution='pending'
        if status=='new':
            mapping=assignments(company,source)
            # Keep compact original normalized evidence, separately from current assignments.
            snapshot={k:v for k,v in source.items() if k not in ('cells','invoice_payment_total','invoice_payment_rows')}
            receipt=FinancialReceipt.objects.create(company=company,provider=batch.provider,number=source['number'],
                source=snapshot,created_from=row,channel=mapping['channel'] or '',studio_id=mapping['studio'],assignments=mapping)
            resolution='created';event(posting,actor,'create',receipt)
        elif status=='unchanged':resolution='linked';event(posting,actor,'source_link',receipt)
        elif status=='invalid':resolution='invalid';receipt=None
        PaymentDecision.objects.create(posting=posting,row=row,receipt=receipt,resolution=resolution)
    refresh_links(company,actor,posting);event(posting,actor,'commit',after={'version':VERSION});advance(company)
    return posting


def retain(decision,company,actor,note,expected_revision):
    if decision.posting.status!='active' or decision.resolution!='pending' or decision.revision!=expected_revision:
        raise ConfigurationConflict('The payment decision changed.')
    if not decision.receipt or not decision.receipt.active:raise ConfigurationConflict('The current payment is no longer active.')
    decision.resolution='retained';decision.revision+=1;decision.save(update_fields=['resolution','revision'])
    decision.posting.revision+=1;decision.posting.save(update_fields=['revision'])
    event(decision.posting,actor,'retain',decision.receipt,note=note);advance(company)


def undo_plan(posting,company):
    eligible=[];protected=[];reused=0
    for d in posting.decisions.select_related('receipt'):
        r=d.receipt
        if d.resolution!='created':
            if r:reused+=1
        elif r.active:
            reason='reconciled' if r.reconciled else 'changed' if r.edited else 'other_import' if r.decisions.filter(posting__status__in=['active','partial_undo']).exclude(posting=posting).exists() else None
            if reason:protected.append({'receipt_id':r.pk,'reason':reason})
            else:eligible.append(r.pk)
    return {'token':token(company,posting.batch,f'undo:{posting.pk}:{posting.revision}'),
        'eligible':eligible,'protected':protected,'reused':reused}


def undo(posting,company,actor,expected,note):
    previous=posting.events.filter(action='undo',after__request_token=expected).first()
    if previous:return previous.after
    result=undo_plan(posting,company)
    if posting.status not in ('active','partial_undo') or result['token']!=expected:raise ConfigurationConflict('Undo changed. Reload the preview.')
    for r in FinancialReceipt.objects.filter(pk__in=result['eligible']):
        before=state(r);r.active=False;r.sale=None;r.revision+=1;r.save(update_fields=['active','sale','revision'])
        event(posting,actor,'reverse',r,before,note)
    refresh_links(company,actor,posting)
    posting.status='partial_undo' if result['protected'] else 'undone';posting.revision+=1;posting.save(update_fields=['status','revision'])
    result.update(request_token=expected,status=posting.status)
    event(posting,actor,'undo',note=note,after=result);advance(company);return result
