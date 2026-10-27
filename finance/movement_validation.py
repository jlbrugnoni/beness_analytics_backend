"""Shared assignment validation for imported and manually recorded money."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from core_data.access import user_has_global_access,get_or_create_user_access_profile
from .models import Category,Terminal,BankMovementClassification
from .views import visible_studios
from .bank_classification import effective_kind,missing_fields

def validate_assignments(user,account,direction,before,values):
    values=dict(values)
    if account.kind=='cash':
        if values.get('terminal') or values.get('channel') not in (None,'','cash'):
            raise serializers.ValidationError('Cash accounts require the cash method and no terminal.')
        if direction=='credit':values['channel']='cash'
    merged={**before,**values}
    allowed_kinds=BankMovementClassification.DEBIT_KINDS if direction=='debit' else BankMovementClassification.CREDIT_KINDS
    if values.get('movement_kind') and values['movement_kind'] not in allowed_kinds:
        raise serializers.ValidationError({'movement_kind':'Choose a supported type for this direction.'})
    values['movement_kind']=effective_kind(direction,merged.get('movement_kind'))
    merged['movement_kind']=values['movement_kind']
    if isinstance(merged.get('expense_period'),str):
        from datetime import date
        merged['expense_period']=date.fromisoformat(merged['expense_period'])
    if merged.get('expense_period') and merged['expense_period'].day!=1:raise serializers.ValidationError({'expense_period':'Use the first day of the expense month.'})
    if direction=='debit' and merged.get('operation_date'):raise serializers.ValidationError({'operation_date':'Operation date is assigned to bank credits.'})
    if direction=='credit' and any(values.get(field) is not None for field in ('category','subcategory')):
        raise serializers.ValidationError({'category':'Categories apply only to bank debits.'})
    if direction=='credit' and merged.get('expense_period'):raise serializers.ValidationError({'expense_period':'Expense month is assigned to bank debits.'})
    for field in ('category','subcategory'):
        if merged.get(field):
            category=get_object_or_404(Category.objects.select_related('parent'),pk=merged[field],company=account.company)
            if merged.get(field)!=before.get(field) and not category.effective_active:raise serializers.ValidationError({field:'Choose an active category.'})
            if field=='category' and category.parent_id:raise serializers.ValidationError({field:'Choose a main category.'})
            if field=='subcategory' and category.parent_id!=merged.get('category'):raise serializers.ValidationError({field:'Subcategory must belong to the selected category.'})
    if merged.get('subcategory') and not merged.get('category'):raise serializers.ValidationError({'category':'Choose the parent category.'})
    if merged.get('studio') and not visible_studios(user).filter(pk=merged['studio'],site_id=account.company.site_id).exists():raise serializers.ValidationError({'studio':'Choose a studio in this company.'})
    if merged.get('studio') and account.studios.exists() and not account.studios.filter(pk=merged['studio']).exists():raise serializers.ValidationError({'studio':'Choose a participating studio for this account.'})
    if merged.get('administration') and not user_has_global_access(user) and get_or_create_user_access_profile(user).allowed_studios.exists():raise PermissionDenied('Company-wide administration requires whole-company scope.')
    if merged.get('administration') and merged.get('studio'):raise serializers.ValidationError({'studio':'Administration is company-wide; leave studio empty.'})
    if merged.get('terminal'):
        terminal=get_object_or_404(Terminal,pk=merged['terminal'],account=account)
        if not terminal.active and terminal.pk!=before.get('terminal'):raise serializers.ValidationError({'terminal':'Choose an active terminal.'})
        if terminal.studio_id!=merged.get('studio') or terminal.channel!=merged.get('channel'):raise serializers.ValidationError({'terminal':'Terminal, studio and payment method must agree.'})
    if merged['movement_kind'] not in allowed_kinds:raise serializers.ValidationError({'movement_kind':'Choose a supported type for this direction.'})
    missing=missing_fields(direction,merged,Category.objects.filter(parent_id=merged.get('category'),active=True).exists() if merged.get('category') else False)
    if missing and values.get('reviewed'):
        raise serializers.ValidationError({field:'Complete this field before marking the movement reviewed.' for field in missing})
    if missing:values['reviewed']=False
    return values
