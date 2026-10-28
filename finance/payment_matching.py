"""Invoice-number matching and explicit review of names/aggregate payment differences."""
from decimal import Decimal
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .bank_readers import normalized
from .configuration import ConfigurationConflict
from .models import FinancialSale, FinancialReceipt, SalesPosting


def context(sale,receipts):
    from .payment_posting import digest
    receipts=sorted(receipts,key=lambda r:r.pk)
    total=sum((Decimal(r.source['amount']) for r in receipts),Decimal(0))
    invoice_total=Decimal(sale.source['invoice_total'])
    names_differ=any(r.source.get('customer') and sale.source.get('customer') and
        normalized(r.source['customer'])!=normalized(sale.source['customer']) for r in receipts)
    basis=digest(['invoice-payments-v1',sale.company_id,sale.provider,sale.pk,sale.code,
        sale.active,sale.source,sale.items,[(r.pk,r.provider,r.source) for r in receipts]])
    approved=sale.payment_link_review.get('basis_token')==basis
    valid=sale.active and sale.source.get('status_kind')=='paid' and invoice_total>0 and bool(receipts)
    currency_matches=all(r.source.get('currency',sale.company.default_currency)==sale.source.get('currency',sale.company.default_currency) for r in receipts)
    valid=valid and currency_matches
    return {'invoice_id':sale.pk,'invoice_code':sale.code,'invoice_customer':sale.source.get('customer') or '',
        'invoice_status':sale.source.get('status') or sale.source.get('status_kind'),'currency':sale.source.get('currency',sale.company.default_currency),
        'invoice_total':f'{invoice_total:.2f}','payment_total':f'{total:.2f}',
        'difference':f'{total-invoice_total:.2f}','names_differ':bool(names_differ),
        'currency_matches':currency_matches,
        'amounts_equal':total==invoice_total,'basis_token':basis,'approved':approved,
        'approval':sale.payment_link_review if approved else None,
        'can_accept':bool(valid and not sale.reconciled and not any(r.reconciled for r in receipts)),
        'payment_count':len(receipts),
        'payments':[{'id':r.pk,'number':r.number,'customer':r.source.get('customer') or '',
            'date':r.source.get('date'),'amount':r.source['amount']} for r in receipts]}


def for_receipt(receipt):
    sale=receipt.sale or FinancialSale.objects.filter(company_id=receipt.company_id,provider=receipt.provider,
        code=receipt.source.get('invoice_code'),active=True).select_related('company').first()
    if not sale:return None
    receipts=list(FinancialReceipt.objects.filter(company_id=receipt.company_id,provider=receipt.provider,
        active=True,source__invoice_code=sale.code).order_by('pk'))
    return context(sale,receipts)


def review(receipt,company,actor,expected,decision,note):
    from . import payment_posting as operations
    from . import sales_posting
    sale=receipt.sale or FinancialSale.objects.filter(company=company,provider=receipt.provider,
        code=receipt.source.get('invoice_code'),active=True).select_related('company').first()
    if not sale:raise ValidationError('Import a valid invoice before reviewing its payments.')
    receipts=list(FinancialReceipt.objects.filter(company=company,provider=receipt.provider,
        active=True,source__invoice_code=sale.code).order_by('pk'))
    current=context(sale,receipts)
    if current['basis_token']!=expected:raise ConfigurationConflict('Invoice or payments changed. Refresh the comparison.')
    if not current['can_accept']:raise ValidationError('Resolve invoice status, currency or reconciliation before reviewing this group.')
    if decision=='accept_names' and not current['amounts_equal']:
        raise ValidationError('The aggregate payment amount differs. Review the amount difference explicitly.')
    if decision=='accept_difference' and current['amounts_equal']:
        raise ValidationError('Amounts agree. Use the customer-name review.')
    if decision=='accept_difference' and not note.strip():raise ValidationError({'note':'Explain the amount difference.'})
    if decision=='accept_names' and not current['names_differ']:raise ValidationError('There is no customer-name difference to approve.')
    if decision=='reopen' and not current['approved']:raise ConfigurationConflict('There is no current approval to reopen.')
    before=sales_posting.state(sale)
    saved={'basis_token':expected,'decision':decision,'note':note.strip(),'actor_id':actor.pk,'at':timezone.now().isoformat()}
    if decision!='reopen' and current['approved']:
        return current
    sale.payment_link_review={} if decision=='reopen' else saved
    sale.revision+=1;sale.save(update_fields=['payment_link_review','revision'])
    posting=SalesPosting.objects.filter(batch_id=sale.created_from.batch_id).first()
    if posting:sales_posting.event(posting,actor,'payment_review',sale,before,note.strip())
    old={r.pk:operations.state(r) for r in receipts}
    operations.refresh_links(company,actor)
    for r in FinancialReceipt.objects.filter(pk__in=old).order_by('pk'):
        operations.event(None,actor,'payment_review',r,old[r.pk],note.strip(),
            after={**operations.state(r),'invoice_payment_review':saved,'invoice_code':sale.code})
    sales_posting.advance(company)
    return for_receipt(FinancialReceipt.objects.select_related('sale__company').get(pk=receipt.pk))
