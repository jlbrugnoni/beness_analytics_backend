"""General actual-money entries. Invoices/payments are independent sales evidence."""
from contextlib import ExitStack
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .models import BankMovement,BankMovementClassification,Account,SourceMapping
from .posting_views import BankMovementViewSet,locked_account,movement_origin
from .bank_classification import snapshot,presentation
from .movement_validation import validate_assignments
from .views import visible_accounts
from .access import can_use_finance
from .configuration import ConfigurationConflict
from . import bank_posting as ledger


class EntryInput(serializers.Serializer):
    account=serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    date=serializers.DateField()
    direction=serializers.ChoiceField(choices=['debit','credit'])
    amount=serializers.DecimalField(max_digits=18,decimal_places=2,min_value=Decimal('0.01'))
    description=serializers.CharField(max_length=2000,allow_blank=True)
    studio=serializers.IntegerField(min_value=1,allow_null=True,required=False)
    administration=serializers.BooleanField(default=False)
    category=serializers.IntegerField(min_value=1,allow_null=True,required=False)
    subcategory=serializers.IntegerField(min_value=1,allow_null=True,required=False)
    expense_period=serializers.DateField(allow_null=True,required=False)
    operation_date=serializers.DateField(allow_null=True,required=False)
    movement_kind=serializers.ChoiceField(choices=BankMovementClassification.KINDS,required=False)
    channel=serializers.ChoiceField(choices=SourceMapping.CHANNELS,allow_blank=True,required=False)
    reviewed=serializers.BooleanField(default=False)
    request_key=serializers.UUIDField(required=False)
    expected_revision=serializers.IntegerField(min_value=1,required=False)


def entry_values(user,data,account):
    direction=data['direction'];day=data['date']
    source={'bank_date':day.isoformat(),'direction':direction,'amount':f"{data['amount']*(-1 if direction=='debit' else 1):.2f}",
        'currency':account.currency,'description':data['description'],'short_description':'','reference':'','serial':'','balance':None}
    fields={key:value for key,value in data.items() if key not in ('account','date','direction','amount','request_key','expected_revision')}
    if direction=='debit':fields.setdefault('expense_period',day.replace(day=1))
    else:fields.setdefault('operation_date',day)
    return source,validate_assignments(user,account,direction,{},fields)


def store_assignments(movement,values):
    item,_=BankMovementClassification.objects.get_or_create(movement=movement)
    for key,value in values.items():setattr(item,key+'_id' if key in ('studio','category','subcategory','terminal') else key,value)
    item.save();movement.classification=item


class MoneyMovementViewSet(BankMovementViewSet):
    def create(self,request):
        if not can_use_finance(request.user,'can_edit_finance'):raise PermissionDenied()
        data=EntryInput(data=request.data);data.fields['account'].queryset=visible_accounts(request.user)
        if set(request.data)-set(data.fields):raise serializers.ValidationError('Unsupported entry fields.')
        data.is_valid(raise_exception=True);v=data.validated_data
        if 'request_key' not in v:raise serializers.ValidationError({'request_key':'Provide a request identifier to prevent duplicate submissions.'})
        with locked_account(request.user,v['account'].pk,['can_edit_finance'],bank_only=False) as account:
            source,values=entry_values(request.user,v,account)
            signature=ledger.fingerprint({key:str(value.pk if key=='account' else value) for key,value in v.items() if key not in ('request_key','expected_revision')})
            existing=BankMovement.objects.filter(manual_key=v['request_key']).first()
            if existing:
                if existing.account_id!=account.pk or existing.manual_request_hash!=signature:raise ConfigurationConflict('This request identifier belongs to another entry.')
                return Response({'id':existing.pk,'active':existing.active,'reused':True})
            obj=BankMovement.objects.create(account=account,provider='manual',source=source,fingerprint=ledger.fingerprint(source),
                manual_key=v['request_key'],manual_actor=request.user,manual_request_hash=signature)
            store_assignments(obj,values)
            ledger.event(None,request.user,'manual_create',obj)
            ledger.advance(account)
        return Response({'id':obj.pk,'revision':obj.revision,**movement_origin(obj),**presentation(obj)},status=201)

    @action(detail=True,methods=['post'],url_path='edit-entry')
    def edit_entry(self,request,pk=None):
        original=self.get_object()
        data=EntryInput(data=request.data);data.fields['account'].queryset=visible_accounts(request.user).filter(company=original.account.company)
        if set(request.data)-set(data.fields):raise serializers.ValidationError('Unsupported entry fields.')
        data.is_valid(raise_exception=True);v=data.validated_data
        with ExitStack() as stack:
            accounts={account_id:stack.enter_context(locked_account(request.user,account_id,['can_edit_finance'],bank_only=False))
                for account_id in sorted({original.account_id,v['account'].pk})}
            obj=get_object_or_404(self.get_queryset().select_for_update(of=('self',)),pk=original.pk,active=True)
            if not obj.manual_key or obj.historical_row_id or obj.created_from_id:raise serializers.ValidationError('Imported financial facts are read-only.')
            from .review_workflow import assert_bank_editable
            assert_bank_editable(obj)
            if obj.reconciled or obj.decisions.filter(posting__status__in=['active','partial_undo']).exists():raise serializers.ValidationError('This entry has linked evidence. Review that linkage first.')
            if v.get('expected_revision')!=obj.revision or obj.account_id!=original.account_id:raise ConfigurationConflict('The entry changed. Reload before saving.')
            if v['direction']!=obj.source['direction']:raise serializers.ValidationError('Void an incorrect entry and create one in the correct direction.')
            account=accounts[v['account'].pk];source,values=entry_values(request.user,v,account)
            before=ledger.movement_data(obj);obj.account=account;obj.source=source;obj.fingerprint=ledger.fingerprint(source)
            # The full edit replaces manual assignments intentionally and is audited.
            obj.classification.delete();store_assignments(obj,values)
            obj.revision+=1;obj.save()
            ledger.event(None,request.user,'manual_edit',obj,before=before)
            for account in accounts.values():ledger.advance(account)
        return Response({'id':obj.pk,'revision':obj.revision,**presentation(obj)})

    @action(detail=True,methods=['post'])
    def void(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_revision=serializers.IntegerField(min_value=1)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);original=self.get_object()
        with locked_account(request.user,original.account_id,['can_edit_finance'],bank_only=False) as account:
            obj=get_object_or_404(self.get_queryset().select_for_update(of=('self',)),pk=original.pk)
            if not obj.manual_key:raise serializers.ValidationError('Use the source import review/undo for imported entries.')
            if obj.revision!=data.validated_data['expected_revision']:raise ConfigurationConflict('The entry changed.')
            from .review_workflow import assert_bank_editable
            assert_bank_editable(obj)
            if obj.reconciled or obj.decisions.filter(posting__status__in=['active','partial_undo']).exists():raise serializers.ValidationError('Linked or reconciled entries cannot be voided here.')
            before=ledger.movement_data(obj);obj.active=False;obj.revision+=1;obj.save(update_fields=['active','revision','updated_at'])
            ledger.event(None,request.user,'manual_void',obj,before=before,note=data.validated_data['note']);ledger.advance(account)
        return Response({'id':obj.pk,'active':False})
