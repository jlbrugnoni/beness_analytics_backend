import hashlib
import io
from django.db import transaction
from django.http import FileResponse
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .access import can_use_finance, can_view_full_account, can_view_sensitive_detail
from .bank_readers import MAX_FILE_BYTES, read_bank_csv
from .models import Account, BankImportBatch, BankImportRow
from .permissions import FinancePermission
from .views import visible_accounts


class BankPreviewPermission(FinancePermission):
    message = 'Bank previews require finance view, money visibility, full bank access and sensitive financial detail.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and can_use_finance(request.user, 'can_view_finance_bank_accounts') and can_view_sensitive_detail(request.user)


class BankBatchSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    company_name = serializers.CharField(source='account.company.name', read_only=True)
    currency = serializers.CharField(source='account.currency', read_only=True)

    class Meta:
        model = BankImportBatch
        fields = ['id', 'account', 'account_name', 'company_name', 'currency', 'provider', 'file_name', 'byte_size',
                  'encoding', 'parser_version', 'status', 'summary', 'file_issues', 'duplicate_of', 'uploaded_by', 'created_at']
        read_only_fields = fields


class BankRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankImportRow
        fields = ['id', 'row_number', 'source_line', 'source_line_end', 'section', 'kind', 'raw', 'parsed', 'issues']
        read_only_fields = fields


class BankUploadSerializer(serializers.Serializer):
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    provider = serializers.ChoiceField(choices=BankImportBatch._meta.get_field('provider').choices)
    file = serializers.FileField(max_length=255, allow_empty_file=False)

    def validate_file(self, file):
        if not file.name.lower().endswith('.csv'):
            raise serializers.ValidationError('Upload a CSV bank report. Excel and enriched migration files are not supported here.')
        if file.size > MAX_FILE_BYTES:
            raise serializers.ValidationError('The bank preview limit is 5 MiB per file.')
        return file

    def validate(self, attrs):
        account = attrs['account']
        country, currency = {'popular': ('DO', 'DOP'), 'caixa': ('ES', 'EUR')}[attrs['provider']]
        if account.kind != 'bank' or account.currency != currency or account.company.site.country_code != country:
            raise serializers.ValidationError({'account': 'Choose a bank account in the report country and currency.'})
        if not account.active or not account.company.active:
            raise serializers.ValidationError({'account': 'Activate the company and account before uploading.'})
        return attrs


class BankImportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, BankPreviewPermission]
    serializer_class = BankBatchSerializer
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        queryset = BankImportBatch.objects.filter(account__in=visible_accounts(self.request.user)).select_related('account__company').defer('original_file')
        account = self.request.query_params.get('account')
        if account:
            if not account.isdecimal():
                raise serializers.ValidationError({'account': 'Use an account ID.'})
            queryset = queryset.filter(account_id=account)
        return queryset

    def create(self, request):
        if not can_use_finance(request.user, 'can_import_finance'):
            raise PermissionDenied('Financial import permission is required.')
        serializer = BankUploadSerializer(data=request.data)
        serializer.fields['account'].queryset = visible_accounts(request.user)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        content = data['file'].read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise serializers.ValidationError({'file': 'The bank preview limit is 5 MiB per file.'})
        parsed = read_bank_csv(content, data['provider'])
        digest = hashlib.sha256(content).hexdigest()
        file_name = ''.join(c for c in data['file'].name.replace('\\', '/').split('/')[-1] if ord(c) >= 32)[:255] or 'bank-report.csv'
        with transaction.atomic():
            # Same lock order as financial configuration; recheck scope and state after parsing.
            from .models import Company
            company = Company.objects.select_for_update().get(pk=data['account'].company_id)
            account = Account.objects.select_for_update().get(pk=data['account'].pk)
            if not can_view_full_account(request.user, account) or not can_view_sensitive_detail(request.user) or not can_use_finance(request.user, 'can_import_finance'):
                raise PermissionDenied('Financial import access changed. Reload before uploading.')
            if not account.active or not company.active:
                raise serializers.ValidationError({'account': 'Activate the company and account before uploading.'})
            prior = BankImportBatch.objects.filter(account=account, provider=data['provider'], file_hash=digest).order_by('pk').first()
            batch = BankImportBatch.objects.create(account=account, provider=data['provider'], file_name=file_name,
                file_hash=digest, byte_size=len(content), original_file=content, encoding=parsed['encoding'],
                parser_version=parsed['parser_version'], status='failed' if parsed['file_issues'] else 'preview',
                summary=parsed['summary'], file_issues=parsed['file_issues'], duplicate_of=prior, uploaded_by=request.user)
            BankImportRow.objects.bulk_create([BankImportRow(batch=batch, **row) for row in parsed['rows']], batch_size=500)
        return Response(BankBatchSerializer(batch).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def rows(self, request, pk=None):
        batch = self.get_object()
        kind = request.query_params.get('kind', 'data')
        if kind not in ('data', 'invalid', 'all'):
            raise serializers.ValidationError({'kind': 'Choose data, invalid or all.'})
        rows = batch.rows.all()
        if kind != 'all':
            rows = rows.filter(kind='data')
        if kind == 'invalid':
            rows = rows.exclude(issues=[])
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(BankRowSerializer(page, many=True).data)

    @action(detail=True, methods=['get'])
    def original(self, request, pk=None):
        if not can_use_finance(request.user, 'can_import_finance'):
            raise PermissionDenied('Financial import permission is required to retrieve source files.')
        batch = self.get_object()
        response = FileResponse(io.BytesIO(bytes(batch.original_file)), as_attachment=True, filename=batch.file_name, content_type='text/csv')
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
