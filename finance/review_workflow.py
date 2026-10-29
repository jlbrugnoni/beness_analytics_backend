"""Operational completion and explicit review locks, independent of source warnings."""
from collections import defaultdict
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import FinancialSale,FinancialReceipt,SalesPosting


def import_capability(batch):
    return 'can_import_finance_migration' if getattr(batch,'migration_batch_id',None) or batch._meta.model_name=='migrationimportbatch' else 'can_import_finance'


def bank_locked(movement):
    from .bank_classification import presentation
    return bool(presentation(movement)['classification'].get('reviewed'))


def assert_bank_editable(movement):
    if bank_locked(movement):raise ValidationError('This entry is reviewed. An authorized user must reopen it before editing.')


def assert_sale_editable(sale):
    if sale.reviewed:raise ValidationError('This invoice is reviewed. An authorized user must reopen it before editing.')


def assert_receipt_editable(receipt):
    if receipt.reviewed or (receipt.sale_id and receipt.sale.reviewed):raise ValidationError('This payment is reviewed. An authorized user must reopen its invoice before editing.')


def receipt_missing(receipt,sale=None):
    sale=sale or receipt.sale
    missing=[]
    if not receipt.source.get('date'):missing.append('date')
    if not receipt.channel:missing.append('channel')
    studio=sale.studio_id if sale and receipt.assignments.get('studio_origin')=='invoice' else receipt.studio_id
    if not studio:missing.append('studio')
    if receipt.link_issue:missing.append('invoice_link')
    return missing


def invoice_receipts(sale):
    return FinancialReceipt.objects.filter(company_id=sale.company_id,provider=sale.provider,active=True).filter(Q(sale_id=sale.pk)|Q(sale__isnull=True,source__invoice_code=sale.code))


def sale_missing(sale,receipts=None):
    receipts=list(receipts if receipts is not None else invoice_receipts(sale))
    missing=[]
    if not sale.studio_id:missing.append('studio')
    if 'studio_conflict' in sale.assignments.get('warnings',[]) and sale.assignments.get('studio_origin')!='manual':missing.append('studio_conflict')
    if not sale.source.get('date'):missing.append('date')
    if sale.source.get('status_kind')=='cancelled':
        if sale.cancellation_treatment=='pending':missing.append('cancellation_treatment')
    elif not receipts:missing.append('payments')
    if any(receipt_missing(r,sale) for r in receipts):missing.append('payments')
    return list(dict.fromkeys(missing))


def refresh_supervised(company,actor):
    """Normalize trusted historical assignments; never relock explicitly reopened work."""
    from . import sales_posting,payment_posting
    from .payment_matching import context
    changed=0
    sales=list(FinancialSale.objects.filter(company=company,active=True).select_related('created_from__batch__migration_batch').defer('created_from__batch__original_file','created_from__batch__migration_batch__original_file'))
    receipts=list(FinancialReceipt.objects.filter(company=company,active=True).select_related('created_from__batch__migration_batch').defer('created_from__batch__original_file','created_from__batch__migration_batch__original_file'))
    by_code=defaultdict(list);by_sale=defaultdict(list)
    for r in receipts:
        by_code[(r.provider,r.source.get('invoice_code'))].append(r)
        if r.sale_id:by_sale[r.sale_id].append(r)
    rules={(r.source_field,r.normalized_value):r for r in company.source_mappings.filter(active=True)}
    from .models import normalized_source_value
    for sale in sales:
        batch=sale.created_from.batch
        if not batch.migration_batch_id or not batch.migration_batch.supervised:continue
        if sale.reviewed or sale.assignments.get('review_reopened'):continue
        before=sales_posting.state(sale);group=by_code[(sale.provider,sale.code)]
        if any(r.assignments.get('review_reopened') for r in group):continue
        if not sale.studio_id and sale.assignments.get('studio_origin')!='manual':
            studios={r.studio_id for r in group if r.studio_id}
            rule=rules.get(('alegra_price_list',normalized_source_value(sale.source.get('price_list') or '')))
            if len(studios)==1:sale.studio_id=next(iter(studios))
            elif rule and rule.studio_id and rule.behavior=='map':sale.studio_id=rule.studio_id
            if sale.studio_id:sale.assignments={**sale.assignments,'studio':sale.studio_id,'studio_origin':'supervised_migration'}
        # Supervision is an explicit business declaration: equal total/name aliases
        # in that workbook are already reviewed. Amount/status errors remain open.
        if group and sale.source.get('status_kind')=='paid' and all(r.created_from.batch.migration_batch_id and r.created_from.batch.migration_batch.supervised for r in group):
            sale.company=company;comparison=context(sale,group)
            if comparison['amounts_equal'] and comparison['names_differ'] and comparison['currency_matches']:
                sale.payment_link_review={'basis_token':comparison['basis_token'],'decision':'accept_names','note':'Supervised historical workbook','actor_id':actor.pk if actor else None,'at':timezone.now().isoformat()}
                for r in group:
                    if r.link_issue=='customer_conflict':
                        prior=payment_posting.state(r);r.sale=sale;r.link_issue='';r.revision+=1;r.save(update_fields=['sale','link_issue','revision'])
                        payment_posting.event(None,actor,'supervised_review',r,prior)
                        if r not in by_sale[sale.pk]:by_sale[sale.pk].append(r)
        linked=by_sale[sale.pk]
        missing=sale_missing(sale,linked)
        sale.assignments={**sale.assignments,'requires_review':bool(missing),'review_reasons':missing}
        sale.reviewed=not missing
        if before!=sales_posting.state(sale):
            changed+=1;sale.revision+=1;sale.save(update_fields=['studio','assignments','reviewed','payment_link_review','revision'])
            posting=SalesPosting.objects.filter(batch=batch).first()
            if posting:sales_posting.event(posting,actor,'supervised_review',sale,before)
        for r in linked:
            if r.reviewed or r.assignments.get('review_reopened'):continue
            if not r.created_from.batch.migration_batch_id or not r.created_from.batch.migration_batch.supervised:continue
            prior=payment_posting.state(r);r.sale=sale
            r.reviewed=sale.reviewed and not receipt_missing(r,sale)
            if r.channel:r.assignments={**r.assignments,'channel_review':False}
            if prior!=payment_posting.state(r):
                r.revision+=1;r.save(update_fields=['reviewed','assignments','revision'])
                payment_posting.event(None,actor,'supervised_review',r,prior)

    if changed:sales_posting.advance(company)
    return changed


def review_invoice(sale,company,actor,reopen=False):
    from . import sales_posting,payment_posting
    receipts=list(invoice_receipts(sale).select_for_update())
    if not reopen:
        missing=sale_missing(sale,receipts)
        if missing:raise ValidationError({'missing_fields':missing})
    if sale.reviewed == (not reopen):return
    before=sales_posting.state(sale)
    sale.reviewed=not reopen
    sale.assignments={**sale.assignments,'review_reopened':reopen,'requires_review':reopen,'review_reasons':[]}
    sale.revision+=1;sale.save(update_fields=['reviewed','assignments','revision'])
    sales_posting.event(SalesPosting.objects.get(batch=sale.created_from.batch),actor,'reopen' if reopen else 'review',sale,before)
    for r in receipts:
        prior=payment_posting.state(r);r.reviewed=not reopen
        r.assignments={**r.assignments,'review_reopened':reopen,**({'channel_review':False} if not reopen and r.channel else {})}
        r.revision+=1;r.save(update_fields=['reviewed','assignments','revision'])
        payment_posting.event(None,actor,'reopen' if reopen else 'review',r,prior)
    sales_posting.advance(company);payment_posting.advance(company)
    if reopen:payment_posting.refresh_links(company,actor)
