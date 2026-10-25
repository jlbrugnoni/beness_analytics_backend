from contextlib import contextmanager
from django.db import transaction
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
from .models import Account, BankDecision, BankEvent, BankMovement, BankPosting, Company
from .views import visible_accounts


@contextmanager
def locked_account(user, account_id, capabilities=(), active=True):
    with transaction.atomic():
        original = Account.objects.get(pk=account_id)
        company = Company.objects.select_for_update().get(pk=original.company_id)
        account = Account.objects.select_for_update().get(pk=account_id)
        if not can_view_full_account(user, account) or not can_view_sensitive_detail(user) or any(not can_use_finance(user, cap) for cap in capabilities):
            raise PermissionDenied('Bank action permission or account access is unavailable.')
        if active and account.kind != 'bank':
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


class BankMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankMovement
        fields = ['id', 'account', 'provider', 'source', 'created_from', 'revision', 'active', 'reconciled', 'created_at', 'updated_at']
        read_only_fields = fields


class BankEventSerializer(serializers.ModelSerializer):
    batch_id = serializers.IntegerField(source='posting.batch_id', read_only=True)

    class Meta:
        model = BankEvent
        fields = ['id', 'posting', 'batch_id', 'movement', 'row', 'actor', 'action', 'before', 'after', 'note', 'created_at']
        read_only_fields = fields


class BankMovementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = BankImportViewSet.permission_classes
    serializer_class = BankMovementSerializer
    http_method_names = ['get', 'head', 'options']
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        queryset = BankMovement.objects.filter(account__in=visible_accounts(self.request.user))
        account = self.request.query_params.get('account')
        if account:
            if not account.isdecimal(): raise serializers.ValidationError({'account': 'Use an account ID.'})
            queryset = queryset.filter(account_id=account)
        if self.action == 'list':
            state = self.request.query_params.get('state', 'active')
            if state not in ('active', 'all', 'reversed'): raise serializers.ValidationError({'state': 'Choose active, all or reversed.'})
            if state != 'all': queryset = queryset.filter(active=state == 'active')
        return queryset

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        movement = self.get_object()
        page = self.paginate_queryset(movement.events.select_related('posting').all())
        return self.get_paginated_response(BankEventSerializer(page, many=True).data)
