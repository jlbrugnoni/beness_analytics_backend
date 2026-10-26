"""Manual bank assignments, separate from immutable reported facts and matching."""
from .models import BankMovementClassification


def snapshot(movement):
    try: item=movement.classification
    except BankMovementClassification.DoesNotExist: return {}
    return {key:(getattr(item,key).isoformat() if getattr(item,key) else None) for key in ('operation_date','expense_period')} | {
        'description':item.description,'category':item.category_id,'subcategory':item.subcategory_id,
        'studio':item.studio_id,'administration':item.administration,'channel':item.channel,
        'terminal':item.terminal_id,'movement_kind':item.movement_kind,'reviewed':item.reviewed}


def presentation(movement):
    values=snapshot(movement);reasons=[]
    kind=values.get('movement_kind') or ''
    if not kind: reasons.append('missing_kind')
    if kind not in ('internal_transfer',):
        if not values.get('studio') and not values.get('administration'):reasons.append('missing_studio')
    if movement.source.get('direction')=='debit' and kind in ('expense','fee','extraordinary'):
        if not values.get('category'):reasons.append('missing_category')
        elif any(child.active for child in movement.classification.category.children.all()) and not values.get('subcategory'):reasons.append('missing_subcategory')
        if not values.get('expense_period'):reasons.append('missing_period')
    if movement.source.get('direction')=='credit' and kind=='customer_receipt':
        if not values.get('channel'):reasons.append('missing_method')
        if not values.get('operation_date'):reasons.append('missing_operation_date')
    if not values.get('reviewed'):reasons.append('not_reviewed')
    labels={}
    if values:
        item=movement.classification
        labels={key+'_name':getattr(item,key).name if getattr(item,key+'_id') else None for key in ('category','subcategory','studio')}
        labels['terminal_name']=item.terminal.identifier if item.terminal_id else None
    return {'classification':values,'classification_labels':labels,'review_reasons':reasons,'needs_review':bool(reasons)}
