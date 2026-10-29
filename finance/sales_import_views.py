"""Company-scoped source previews. No sales posting endpoint exists yet."""
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
from core_data.access import get_or_create_user_access_profile, user_has_global_access
from .access import can_use_finance, can_view_sensitive_detail, scoped_companies
from .alegra_reader import MAX_FILE_BYTES, read_alegra_csv
from .models import Company, SalesImportBatch, SalesImportInvoice, SalesImportRow
from .permissions import FinancePermission


def sales_preview_companies(user):
    # Unclassified raw files may contain multiple studios and private notes.
    # Partial studio grants cannot expose the entire company source.
    companies = scoped_companies(Company.objects.select_related('site'), user)
    if not can_view_sensitive_detail(user):
        return companies.none()
    if not user_has_global_access(user) and get_or_create_user_access_profile(user).allowed_studios.exists():
        return companies.none()
    return companies.filter(site__country_code='DO', default_currency='DOP')


class SalesPreviewPermission(FinancePermission):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and can_view_sensitive_detail(request.user)


class SalesBatchSerializer(serializers.ModelSerializer):
    processing_status = serializers.SerializerMethodField()

    def get_processing_status(self, obj):
        posting = getattr(obj, 'posting', None)
        return posting.status if posting else 'not_imported'

    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = SalesImportBatch
        fields = ['id', 'company', 'company_name', 'provider', 'migration_batch', 'file_name', 'byte_size', 'encoding',
                  'parser_version', 'status', 'processing_status', 'summary', 'file_issues', 'duplicate_of', 'uploaded_by', 'created_at']
        read_only_fields = fields


class SalesInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesImportInvoice
        fields = ['id', 'occurrence', 'code', 'source', 'item_count', 'row_numbers', 'issues']
        read_only_fields = fields


class SalesRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesImportRow
        fields = ['id', 'row_number', 'source_line', 'source_line_end', 'kind', 'raw', 'parsed', 'issues']
        read_only_fields = fields


class SalesUploadSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())
    file = serializers.FileField(max_length=255, allow_empty_file=False)

    def validate_file(self, value):
        if not value.name.lower().endswith('.csv') or value.size > MAX_FILE_BYTES:
            raise serializers.ValidationError('Choose an Alegra item CSV no larger than 5 MiB.')
        return value


class SalesImportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, SalesPreviewPermission]
    serializer_class = SalesBatchSerializer
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        qs = SalesImportBatch.objects.filter(company__in=sales_preview_companies(self.request.user)).select_related('company', 'posting').defer('original_file')
        company = self.request.query_params.get('company')
        if company:
            if not company.isdecimal():
                raise serializers.ValidationError({'company': 'Use a company ID.'})
            qs = qs.filter(company_id=company)
        return qs

    @action(detail=False, methods=['get'])
    def companies(self, request):
        return Response(list(sales_preview_companies(request.user).values('id', 'name', 'active', 'default_currency')))

    def create(self, request):
        if not can_use_finance(request.user, 'can_import_finance'):
            raise PermissionDenied('Financial import permission is required.')
        serializer = SalesUploadSerializer(data=request.data)
        serializer.fields['company'].queryset = sales_preview_companies(request.user)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        content = data['file'].read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise serializers.ValidationError({'file': 'The file exceeds 5 MiB.'})
        parsed = read_alegra_csv(content)
        digest = hashlib.sha256(content).hexdigest()
        file_name = ''.join(c for c in data['file'].name.replace('\\', '/').split('/')[-1] if ord(c) >= 32)[:255] or 'alegra.csv'
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=data['company'].pk)
            if not can_use_finance(request.user, 'can_import_finance') or not sales_preview_companies(request.user).filter(pk=company.pk).exists():
                raise PermissionDenied('Financial import access changed. Reload before uploading.')
            if not company.active:
                raise serializers.ValidationError({'company': 'Activate the company before uploading.'})
            prior = SalesImportBatch.objects.filter(company=company, provider='alegra', file_hash=digest).order_by('pk').first()
            batch = SalesImportBatch.objects.create(company=company, file_name=file_name, file_hash=digest,
                byte_size=len(content), original_file=content, encoding=parsed['encoding'], parser_version=parsed['parser_version'],
                status='failed' if parsed['file_issues'] else 'preview', summary=parsed['summary'],
                file_issues=parsed['file_issues'], duplicate_of=prior, uploaded_by=request.user)
            SalesImportRow.objects.bulk_create([SalesImportRow(batch=batch, **row) for row in parsed['rows']], batch_size=500)
            SalesImportInvoice.objects.bulk_create([SalesImportInvoice(batch=batch, **invoice) for invoice in parsed['invoices']], batch_size=500)
        return Response(SalesBatchSerializer(batch).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def invoices(self, request, pk=None):
        qs = self.get_object().invoices.all()
        kind = request.query_params.get('kind', 'all')
        if kind == 'review':
            qs = qs.exclude(issues=[])
        elif kind != 'all':
            raise serializers.ValidationError({'kind': 'Choose all or review.'})
        return self.get_paginated_response(SalesInvoiceSerializer(self.paginate_queryset(qs), many=True).data)

    @action(detail=True, methods=['get'])
    def rows(self, request, pk=None):
        qs = self.get_object().rows.all()
        invoice = request.query_params.get('invoice')
        if invoice:
            if not invoice.isdecimal():
                raise serializers.ValidationError({'invoice': 'Use an invoice preview ID.'})
            obj = self.get_object().invoices.filter(pk=invoice).first()
            if obj is None:
                from rest_framework.exceptions import NotFound
                raise NotFound()
            qs = qs.filter(row_number__in=obj.row_numbers)
        return self.get_paginated_response(SalesRowSerializer(self.paginate_queryset(qs), many=True).data)

    @action(detail=True, methods=['get'])
    def original(self, request, pk=None):
        from .review_workflow import import_capability
        batch = self.get_object()
        if not can_use_finance(request.user, import_capability(batch)):
            raise PermissionDenied('Import permission is required to retrieve source files.')
        batch = self.get_object()
        response = FileResponse(io.BytesIO(bytes(batch.original_file)), as_attachment=True, filename=batch.file_name,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if batch.migration_batch_id else 'text/csv')
        response['X-Content-Type-Options'] = 'nosniff'
        return response
