from contextlib import contextmanager
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from .access import can_use_finance, can_view_full_account, can_view_sensitive_detail
from . import bank_posting as operations
from .configuration import ConfigurationConflict
from .import_views import BankImportViewSet, BankPreviewPermission
from core_data.access import get_or_create_user_access_profile, user_has_global_access
from core_data.models import Studio
from .bank_classification import snapshot, presentation, missing_fields, effective_kind
from .models import BankMovementClassification, Category, Terminal, SourceMapping, Account, BankDecision, BankEvent, BankMovement, BankPosting, Company
from .views import visible_accounts, visible_studios


@contextmanager
def locked_account(user, account_id, capabilities=(), active=True, bank_only=True):
    with transaction.atomic():
        original = Account.objects.get(pk=account_id)
        company = Company.objects.select_for_update().get(pk=original.company_id)
        account = Account.objects.select_for_update().get(pk=account_id)
        if not can_view_full_account(user, account) or not can_view_sensitive_detail(user) or any(not can_use_finance(user, cap) for cap in capabilities):
            raise PermissionDenied('Bank action permission or account access is unavailable.')
        if active and bank_only and account.kind != 'bank':
            raise serializers.ValidationError('Bank transactions require a bank account.')
        if active and (not account.active or not company.active):
            raise serializers.ValidationError('Activate the company and account before changing transactions.')
        yield account


def may_undo(user, posting):
    return (can_use_finance(user, 'can_import_finance') and can_use_finance(user, 'can_edit_finance') and
            (posting.actor_id == user.pk or can_use_finance(user, 'can_manage_finance_settings')))


class BankPostingImportViewSet(BankImportViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=True, methods=['get'])
    def processing(self, request, pk=None):
        batch = self.get_object()
        with locked_account(request.user, batch.account_id, active=False) as account:
            result = operations.plan(batch, account)
            posting = result.pop('posting')
            page = self.paginate_queryset(result.pop('rows'))
            result['rows'] = self.get_paginated_response(page).data
            result['posting'] = {'id': posting.pk, 'status': posting.status, 'revision': posting.revision,
                'actor': posting.actor_id} if posting else None
            result['can_commit'] = bool(not posting and batch.status == 'preview' and batch.summary.get('valid_rows')
                and account.kind == 'bank' and account.active and account.company.active and can_use_finance(request.user, 'can_import_finance'))
            result['can_review'] = bool(posting and posting.status == 'active' and account.kind == 'bank' and account.active and account.company.active
                and can_use_finance(request.user, 'can_import_finance') and can_use_finance(request.user, 'can_edit_finance'))
            result['can_undo'] = bool(posting and posting.status in ('active', 'partial_undo') and account.kind == 'bank' and account.active and account.company.active and may_undo(request.user, posting))
            return Response(result)

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        class Input(serializers.Serializer):
            expected_plan = serializers.CharField(min_length=64, max_length=64)
        data = Input(data=request.data); data.is_valid(raise_exception=True)
        batch = self.get_object()
        with locked_account(request.user, batch.account_id, ['can_import_finance']) as account:
            posting = operations.commit(batch, account, request.user, data.validated_data['expected_plan'])
            return Response({'posting_id': posting.pk, 'status': posting.status})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        class Input(serializers.Serializer):
            expected_plan = serializers.CharField(min_length=64, max_length=64)
            decision_id = serializers.IntegerField(min_value=1)
            expected_revision = serializers.IntegerField(min_value=1)
            action = serializers.ChoiceField(choices=['create', 'link', 'correct', 'ignore'])
            movement_id = serializers.IntegerField(min_value=1, required=False)
            expected_movement_revision = serializers.IntegerField(min_value=1, required=False)
            note = serializers.CharField(max_length=2000, allow_blank=False)
        data = Input(data=request.data); data.is_valid(raise_exception=True); values = data.validated_data
        batch = self.get_object()
        with locked_account(request.user, batch.account_id, ['can_import_finance', 'can_edit_finance']) as account:
            if values['expected_plan'] != operations.token(account, batch):
                raise ConfigurationConflict('The ledger changed. Reload the review plan.')
            decision = get_object_or_404(BankDecision.objects.select_related('posting__batch', 'row'),
                pk=values['decision_id'], posting__batch=batch)
            target = BankMovement.objects.filter(pk=values.get('movement_id'), account=account).first()
            operations.resolve(decision, account, request.user, values['action'], values['expected_revision'], values['note'],
                target, values.get('expected_movement_revision'))
            return Response({'decision_id': decision.pk, 'resolution': decision.resolution})

    @action(detail=True, methods=['get'], url_path='undo-preview')
    def undo_preview(self, request, pk=None):
        batch = self.get_object()
        with locked_account(request.user, batch.account_id, active=False) as account:
            posting = get_object_or_404(BankPosting, batch=batch)
            if not may_undo(request.user, posting): raise PermissionDenied('Undo requires import/edit access and ownership, or financial settings authority.')
            return Response({**operations.undo_plan(posting, account), 'status': posting.status})

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        batch = self.get_object()
        posting = get_object_or_404(BankPosting, batch=batch)
        page = self.paginate_queryset(posting.events.select_related('posting').all())
        return self.get_paginated_response(BankEventSerializer(page, many=True).data)

    @action(detail=True, methods=['post'])
    def undo(self, request, pk=None):
        class Input(serializers.Serializer):
            expected_plan = serializers.CharField(min_length=64, max_length=64)
            note = serializers.CharField(max_length=2000, allow_blank=False)
        data = Input(data=request.data); data.is_valid(raise_exception=True)
        batch = self.get_object()
        with locked_account(request.user, batch.account_id, ['can_import_finance', 'can_edit_finance']) as account:
            posting = get_object_or_404(BankPosting, batch=batch)
            if not may_undo(request.user, posting): raise PermissionDenied('Only your own imports may be undone without financial settings authority.')
            result = operations.undo(posting, account, request.user, data.validated_data['expected_plan'], data.validated_data['note'])
            return Response({**result, 'status': posting.status})


def movement_origin(obj):
    row=obj.created_from if obj.created_from_id else None
    historical=obj.historical_row if obj.historical_row_id else None
    return {'origin':'migration' if historical or row and row.batch.migration_batch_id else 'report' if row else 'manual',
        'account_kind':obj.account.kind,'file_name':row.batch.file_name if row else historical.batch.file_name if historical else None,
        'batch':row.batch_id if row else None,'source_row':row.source_line if row else historical.source_row if historical else None,
        'manual':bool(obj.manual_key),'can_edit_facts':bool(obj.manual_key and obj.active and not obj.reconciled and not obj.decisions.filter(posting__status__in=['active','partial_undo']).exists())}


class BankMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankMovement
        fields = ['id', 'account', 'provider', 'source', 'created_from', 'revision', 'active', 'reconciled', 'created_at', 'updated_at']
        read_only_fields = fields


class BankEventSerializer(serializers.ModelSerializer):
    batch_id = serializers.IntegerField(source='posting.batch_id', read_only=True,allow_null=True)

    class Meta:
        model = BankEvent
        fields = ['id', 'posting', 'batch_id', 'movement', 'row', 'actor', 'action', 'before', 'after', 'note', 'created_at']
        read_only_fields = fields


class BankMovementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = BankImportViewSet.permission_classes
    serializer_class = BankMovementSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [JSONParser]
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        queryset = BankMovement.objects.filter(account__in=visible_accounts(self.request.user)).select_related('classification__category','classification__subcategory','classification__studio','classification__terminal','account__company','created_from__batch','created_from__migration_row','historical_row__batch').prefetch_related('classification__category__children')
        account = self.request.query_params.get('account')
        if account:
            if not account.isdecimal(): raise serializers.ValidationError({'account': 'Use an account ID.'})
            queryset = queryset.filter(account_id=account)
        if self.action == 'list':
            state = self.request.query_params.get('state', 'active')
            if state not in ('active', 'all', 'reversed'): raise serializers.ValidationError({'state': 'Choose active, all or reversed.'})
            if state != 'all': queryset = queryset.filter(active=state == 'active')
        return queryset

    def retrieve(self,request,pk=None):
        obj=self.get_object()
        historical=obj.historical_row if obj.historical_row_id else obj.created_from.migration_row if obj.created_from_id and obj.created_from.migration_row_id else None
        if historical is None:
            evidence=obj.decisions.filter(row__migration_row__isnull=False,posting__status__in=['active','partial_undo']).select_related('row__migration_row').first()
            historical=evidence.row.migration_row if evidence else None
        return Response({**BankMovementSerializer(obj).data,**presentation(obj),
            **movement_origin(obj),
            'historical_source':historical.parsed if historical else None,
            'can_edit':bool(can_use_finance(request.user,'can_edit_finance') and obj.active and not obj.reconciled and obj.account.active and obj.account.company.active)})

    @action(detail=True,methods=['get'])
    def options(self,request,pk=None):
        obj=self.get_object();company=obj.account.company
        studios=visible_studios(request.user).filter(site_id=company.site_id)
        if obj.account.studios.exists():studios=studios.filter(pk__in=obj.account.studios.values('pk'))
        return Response({'categories':[{'id':c.pk,'name':c.name,'parent':c.parent_id,'active':c.effective_active}
            for c in Category.objects.filter(company=company).select_related('parent')] if obj.source.get('direction')=='debit' else [],
            'studios':list(studios.values('id','name')),
            'terminals':list(Terminal.objects.filter(account=obj.account,studio__in=visible_studios(request.user)).filter(Q(active=True)|Q(pk=snapshot(obj).get('terminal'))).values('id','identifier','channel','studio_id')),
            'channels':[{'value':v,'label':label} for v,label in SourceMapping.CHANNELS],
            'kinds':[{'value':v,'label':label} for v,label in BankMovementClassification.KINDS if v in (BankMovementClassification.DEBIT_KINDS if obj.source.get('direction')=='debit' else BankMovementClassification.CREDIT_KINDS)]})

    @action(detail=True,methods=['post'])
    def assign(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_revision=serializers.IntegerField(min_value=1)
            note=serializers.CharField(max_length=2000,allow_blank=True,required=False,default="")
            description=serializers.CharField(max_length=2000,allow_blank=True,required=False)
            operation_date=serializers.DateField(allow_null=True,required=False)
            expense_period=serializers.DateField(allow_null=True,required=False)
            category=serializers.IntegerField(min_value=1,allow_null=True,required=False)
            subcategory=serializers.IntegerField(min_value=1,allow_null=True,required=False)
            studio=serializers.IntegerField(min_value=1,allow_null=True,required=False)
            administration=serializers.BooleanField(required=False)
            channel=serializers.ChoiceField(choices=SourceMapping.CHANNELS,allow_blank=True,required=False)
            terminal=serializers.IntegerField(min_value=1,allow_null=True,required=False)
            movement_kind=serializers.ChoiceField(choices=BankMovementClassification.KINDS,allow_blank=True,required=False)
            reviewed=serializers.BooleanField(required=False)
        original=self.get_object();data=Input(data=request.data)
        if set(request.data)-set(data.fields):raise serializers.ValidationError('Original bank facts are read-only.')
        data.is_valid(raise_exception=True);values=dict(data.validated_data)
        revision=values.pop('expected_revision');note=values.pop('note')
        if not values:raise serializers.ValidationError('Choose a business field to change.')
        with locked_account(request.user,original.account_id,['can_edit_finance'],bank_only=False) as account:
            obj=get_object_or_404(self.get_queryset().select_for_update(of=('self',)),pk=original.pk,active=True)
            if obj.revision!=revision:raise ConfigurationConflict('The bank record changed. Reload before saving.')
            if obj.reconciled:raise serializers.ValidationError('Review bank reconciliation before editing this movement.')
            before=operations.movement_data(obj)
            from .movement_validation import validate_assignments
            values=validate_assignments(request.user,account,obj.source['direction'],before['classification'],values)
            item,_=BankMovementClassification.objects.get_or_create(movement=obj)
            for field,value in values.items():setattr(item,field+'_id' if field in ('category','subcategory','studio','terminal') else field,value)
            item.save();obj.classification=item
            obj.revision+=1;obj.save(update_fields=['revision','updated_at'])
            operations.event(BankPosting.objects.get(batch=obj.created_from.batch) if obj.created_from_id else None,request.user,'classify',obj,before=before,note=note)
            operations.advance(account)
            return Response({**BankMovementSerializer(obj).data,**presentation(obj)})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        movement = self.get_object()
        page = self.paginate_queryset(movement.events.select_related('posting').all())
        return self.get_paginated_response(BankEventSerializer(page, many=True).data)
