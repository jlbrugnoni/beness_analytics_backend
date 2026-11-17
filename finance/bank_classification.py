"""Manual bank assignments, separate from immutable reported facts and matching."""
from .models import BankMovementClassification


def caixa_operation_date(source, identifier):
    """Recognize only an exact ON settlement within seven preceding calendar days."""
    import re
    from datetime import date
    match = re.fullmatch(r'ON\s+' + re.escape(identifier.strip()) + r'\s+(\d{2})(\d{2})',
                         str(source.get('description') or '').strip(), re.IGNORECASE)
    if not match:
        return None
    try:
        bank_date = date.fromisoformat(source['bank_date'])
    except (KeyError, TypeError, ValueError):
        return None
    candidates = []
    for year in (bank_date.year - 1, bank_date.year):
        try:
            candidate = date(year, int(match[2]), int(match[1]))
        except ValueError:
            continue
        if 0 <= (bank_date - candidate).days <= 7:
            candidates.append(candidate)
    return candidates[0] if len(candidates) == 1 else None


def snapshot(movement):
    try: item=movement.classification
    except BankMovementClassification.DoesNotExist: return {}
    return {key:(getattr(item,key).isoformat() if getattr(item,key) else None) for key in ('operation_date','expense_period')} | {
        'description':item.description,'category':item.category_id,'subcategory':item.subcategory_id,
        'studio':item.studio_id,'administration':item.administration,'channel':item.channel,
        'terminal':item.terminal_id,'movement_kind':item.movement_kind,'reviewed':item.reviewed}


def effective_kind(direction,kind):
    """Compatibility for older classifications; preserve the raw audit snapshot."""
    if not kind:return 'expense' if direction=='debit' else 'customer_receipt'
    if direction=='debit' and kind in ('fee','extraordinary'):return 'expense'
    if direction=='credit' and kind=='fee_reimbursement':return 'refund'
    return kind


def missing_fields(direction,values,has_subcategories=False):
    """Applicable completion requirements; optional notes/terminals are not gates."""
    fields=[];kind=effective_kind(direction,values.get('movement_kind'))
    if not kind:fields.append('movement_kind')
    if kind!='internal_transfer' and not values.get('studio') and not values.get('administration'):
        fields.append('studio')
    if direction=='debit' and kind=='expense':
        if not values.get('category'):fields.append('category')
        elif has_subcategories and not values.get('subcategory'):fields.append('subcategory')
        if not values.get('expense_period'):fields.append('expense_period')
    if direction=='credit' and kind=='customer_receipt':
        if not values.get('channel'):fields.append('channel')
        if not values.get('operation_date'):fields.append('operation_date')
    return fields


def presentation(movement):
    values=snapshot(movement);has_classification=bool(values)
    if not values:values={'movement_kind':effective_kind(movement.source.get('direction'),None),'reviewed':False}
    else:values['movement_kind']=effective_kind(movement.source.get('direction'),values.get('movement_kind'))
    children=bool(values.get('category') and any(child.active for child in movement.classification.category.children.all()))
    missing=missing_fields(movement.source.get('direction'),values,children)
    reason_codes={'movement_kind':'missing_kind','studio':'missing_studio','category':'missing_category',
        'subcategory':'missing_subcategory','expense_period':'missing_period','channel':'missing_method','operation_date':'missing_operation_date'}
    reasons=[reason_codes[field] for field in missing]
    # Old incomplete review flags are pending until their required data is completed.
    if values:values['reviewed']=bool(values.get('reviewed') and not missing)
    if not values.get('reviewed'):reasons.append('not_reviewed')
    labels={}
    if has_classification:
        item=movement.classification
        labels={key+'_name':getattr(item,key).name if getattr(item,key+'_id') else None for key in ('category','subcategory','studio')}
        labels['terminal_name']=item.terminal.identifier if item.terminal_id else None
    return {'classification':values,'classification_labels':labels,'review_reasons':reasons,'needs_review':bool(reasons),'missing_fields':missing}


def initialize_classification(movement):
    item=BankMovementClassification.objects.create(movement=movement,
        movement_kind=effective_kind(movement.source.get('direction'),None))
    movement.classification=item


def terminal_patterns(account,actor):
    """Load eligible account mappings once per operation, including actor scope."""
    import re
    from .models import Terminal
    from .views import visible_studios
    studios=set(account.studios.values_list('pk',flat=True))
    terminals=Terminal.objects.filter(account=account,active=True,studio__site_id=account.company.site_id,
        studio__in=visible_studios(actor)).select_related('studio')
    if studios:terminals=terminals.filter(studio_id__in=studios)
    return [(terminal,re.compile(r'(?<!\w)'+re.escape(terminal.identifier.strip())+r'(?!\w)',re.IGNORECASE))
        for terminal in terminals if terminal.identifier.strip()]


def recognize_terminal(movement, actor, existing=False, patterns=None):
    """Apply one exact account terminal match; caller holds company/account locks.

    Only fill compatible, unreviewed credit assignments. Never change source facts,
    overwrite manual choices, or mark recognition/reconciliation. Caixa ON dates
    may fill an empty operation date; the audit note records the inference.
    New movements include this snapshot in their create event; existing ones get
    a separate audited revision so undo and stale-edit protection remain effective.
    """
    from .models import BankPosting
    from . import bank_posting as operations
    if not movement.active or movement.reconciled or movement.source.get('direction') != 'credit':
        return False
    values=snapshot(movement)
    if values.get('reviewed') or values.get('administration'):
        return False
    if values.get('movement_kind') not in (None,'','customer_receipt'):
        return False
    account=movement.account
    if not account.active or not account.company.active:
        return False
    text=' '.join(str(movement.source.get(field) or '') for field in ('description','short_description'))
    if patterns is None:patterns=terminal_patterns(account,actor)
    matches=[terminal for terminal,pattern in patterns if pattern.search(text)]
    if len(matches)!=1:
        return False
    terminal=matches[0]
    # Existing terminal assignments can receive a missing Caixa date, but cannot
    # be remapped by this operation. Other providers retain their original behavior.
    if values.get('terminal') and (movement.provider != 'caixa' or values['terminal'] != terminal.pk):
        return False
    if values.get('studio') not in (None,terminal.studio_id) or values.get('channel') not in (None,'',terminal.channel):
        return False
    before=operations.movement_data(movement) if existing else None
    item,_=BankMovementClassification.objects.get_or_create(movement=movement)
    inferred = caixa_operation_date(movement.source, terminal.identifier) if movement.provider == 'caixa' and not item.operation_date else None
    if values.get('terminal') and not inferred:
        return False
    item.terminal=terminal;item.studio_id=terminal.studio_id;item.channel=terminal.channel
    if inferred:
        item.operation_date = inferred
    note = 'Automatic terminal recognition: ' + terminal.identifier
    if inferred:
        note += '; operation date inferred from Caixa ON description: ' + inferred.isoformat()
    # The caller's create event records provenance for newly imported movements.
    movement._terminal_recognition_note = note
    item.save();movement.classification=item
    if existing:
        movement.revision+=1;movement.save(update_fields=['revision','updated_at'])
        operations.event(BankPosting.objects.get(batch=movement.created_from.batch) if movement.created_from_id else None,actor,'classify',movement,
            before=before,note=note)
    return True
