import hashlib
import io
import zipfile
from xml.etree.ElementTree import ParseError
from datetime import date, datetime
from django.db import transaction
from django.http import FileResponse
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .access import can_use_finance
from .sales_import_views import SalesPreviewPermission, sales_preview_companies
from .migration_reader import MAX_BYTES, read_migration_xlsx, totals
from .migration_source import source_headers, readable_cells
from .payment_preview import read_payment_preview, payment_totals
from .models import Company, MigrationImportBatch, MigrationImportRow


def migration_companies(user):
    companies=sales_preview_companies(user)
    return companies if can_use_finance(user,'can_view_finance_bank_accounts') else companies.none()


class MigrationPermission(SalesPreviewPermission):
    def has_permission(self,request,view):
        return super().has_permission(request,view) and can_use_finance(request.user,'can_view_finance_bank_accounts')


class MigrationBatchSerializer(serializers.ModelSerializer):
    bank_imports=serializers.SerializerMethodField()
    def get_bank_imports(self,obj):
        from .import_views import BankBatchSerializer
        return BankBatchSerializer(obj.bank_imports.select_related('account__company','posting').defer('original_file').order_by('-pk')[:5],many=True).data
    company_name=serializers.CharField(source='company.name',read_only=True)
    class Meta:
        model=MigrationImportBatch
        fields=['id','company','company_name','selected_month','file_name','byte_size','parser_version','status',
            'summary','file_issues','sheets','mappings','bank_imports','duplicate_of','uploaded_by','created_at']
        read_only_fields=fields


class MigrationRowSerializer(serializers.ModelSerializer):
    bank_issue=serializers.SerializerMethodField()
    def get_bank_issue(self,obj):
        from .migration_bank import bank_issue
        return bank_issue(obj)
    class Meta:
        model=MigrationImportRow
        fields=['id','sheet','source_row','kind','bank_date','operation_date','expense_period','amount','parsed','issues','bank_issue']
        read_only_fields=fields


class MigrationUploadSerializer(serializers.Serializer):
    company=serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())
    month=serializers.RegexField(r'^\d{4}-(?:0[1-9]|1[0-2])$',required=False)
    file=serializers.FileField(max_length=255,allow_empty_file=False)

    def validate_month(self,value):
        try:datetime.strptime(value,'%Y-%m')
        except ValueError:raise serializers.ValidationError('Use a valid year and month.')
        return value

    def validate_file(self,value):
        if not value.name.lower().endswith('.xlsx') or value.size>MAX_BYTES:
            raise serializers.ValidationError('Choose the DR enriched XLSX workbook, up to 5 MiB.')
        return value


class MigrationImportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes=[IsAuthenticated,MigrationPermission]
    serializer_class=MigrationBatchSerializer
    parser_classes=[MultiPartParser,FormParser,JSONParser]
    http_method_names=['get','post','head','options']

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='private, no-store';return response

    def get_queryset(self):
        qs=MigrationImportBatch.objects.filter(company__in=migration_companies(self.request.user)).select_related('company').defer('original_file')
        company=self.request.query_params.get('company')
        if company:
            if not company.isdecimal():raise serializers.ValidationError({'company':'Use a company ID.'})
            qs=qs.filter(company_id=company)
        return qs

    @action(detail=False,methods=['get'])
    def companies(self,request):
        return Response(list(migration_companies(request.user).values('id','name','active','default_currency')))

    def create(self,request):
        if not can_use_finance(request.user,'can_import_finance'):raise PermissionDenied('Financial import permission is required.')
        serializer=MigrationUploadSerializer(data=request.data)
        serializer.fields['company'].queryset=migration_companies(request.user)
        serializer.is_valid(raise_exception=True);values=serializer.validated_data
        content=values['file'].read(MAX_BYTES+1)
        if len(content)>MAX_BYTES:raise serializers.ValidationError({'file':'The file exceeds 5 MiB.'})
        parsed=read_migration_xlsx(content,values.get('month',''))
        month=values.get('month') or (parsed['summary'].get('first_bank_date') or datetime.now().date().isoformat())[:7]
        parsed['summary']['selected_month']=month
        parsed['summary']['selected_bank_month']=parsed['summary'].get('bank_date_months',{}).get(month,parsed['summary']['all_rows'])
        digest=hashlib.sha256(content).hexdigest()
        name=''.join(c for c in values['file'].name.replace('\\','/').split('/')[-1] if ord(c)>=32)[:255] or 'migration.xlsx'
        with transaction.atomic():
            company=Company.objects.select_for_update().get(pk=values['company'].pk)
            if not migration_companies(request.user).filter(pk=company.pk).exists() or not can_use_finance(request.user,'can_import_finance'):
                raise PermissionDenied('Migration access changed. Reload before uploading.')
            if not company.active:raise serializers.ValidationError({'company':'Activate the company before uploading.'})
            prior=MigrationImportBatch.objects.filter(company=company,file_hash=digest).order_by('pk').first()
            batch=MigrationImportBatch.objects.create(company=company,selected_month=month+'-01',
                file_name=name,file_hash=digest,byte_size=len(content),original_file=content,
                parser_version=parsed['parser_version'],status='failed' if parsed['file_issues'] else 'preview',
                summary=parsed['summary'],file_issues=parsed['file_issues'],sheets=parsed['sheets'],mappings=parsed['mappings'],
                duplicate_of=prior,uploaded_by=request.user)
            MigrationImportRow.objects.bulk_create([MigrationImportRow(batch=batch,**row) for row in parsed['rows']],batch_size=500)
        return Response(MigrationBatchSerializer(batch).data,status=status.HTTP_201_CREATED)

    @action(detail=True,methods=['post'],url_path='copy-to-company')
    def copy_to_company(self,request,pk=None):
        source=self.get_object()
        if not can_use_finance(request.user,'can_import_finance'):raise PermissionDenied()
        class Input(serializers.Serializer):
            company=serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())
        data=Input(data=request.data);data.fields['company'].queryset=migration_companies(request.user)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            company=Company.objects.select_for_update().get(pk=data.validated_data['company'].pk)
            if not migration_companies(request.user).filter(pk=company.pk).exists() or not migration_companies(request.user).filter(pk=source.company_id).exists() or not can_use_finance(request.user,'can_import_finance'):raise PermissionDenied()
            if not company.active or company.pk==source.company_id:raise serializers.ValidationError('Choose another active company.')
            prior=MigrationImportBatch.objects.filter(company=company,file_hash=source.file_hash).order_by('pk').first()
            batch=MigrationImportBatch.objects.create(company=company,selected_month=source.selected_month,
                file_name=source.file_name,file_hash=source.file_hash,byte_size=source.byte_size,original_file=source.original_file,
                parser_version=source.parser_version,status=source.status,summary={**source.summary,'copied_from_preview':source.pk},
                file_issues=source.file_issues,sheets=source.sheets,mappings=source.mappings,duplicate_of=prior,uploaded_by=request.user)
            fields=['sheet','source_row','kind','bank_date','operation_date','expense_period','amount','raw','parsed','issues']
            MigrationImportRow.objects.bulk_create([MigrationImportRow(batch=batch,**{field:getattr(row,field) for field in fields}) for row in source.rows.all()],batch_size=500)
        return Response(MigrationBatchSerializer(batch).data,status=201)

    @action(detail=True,methods=['get'],url_path='bank-candidates')
    def bank_candidates(self,request,pk=None):
        from .migration_bank import bank_issue
        batch=self.get_object()
        rows=list(batch.rows.all())
        return Response({'row_ids':[row.pk for row in rows if not bank_issue(row)],
            'cash_rows':sum(bank_issue(row)=='cash_entry' for row in rows),
            'invalid_rows':sum(bank_issue(row)=='invalid_bank_facts' for row in rows)})

    @action(detail=True,methods=['post'],url_path='prepare-bank')
    def prepare_bank(self,request,pk=None):
        from .posting_views import locked_account
        from .migration_bank import prepare
        from .import_views import BankBatchSerializer
        from .views import visible_accounts
        from .models import Account
        class Input(serializers.Serializer):
            account=serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
            row_ids=serializers.ListField(child=serializers.IntegerField(min_value=1),min_length=1,max_length=20000)
            confirm_bank_origin=serializers.BooleanField()
        batch=self.get_object();data=Input(data=request.data)
        data.fields['account'].queryset=visible_accounts(request.user).filter(company=batch.company,kind='bank')
        data.is_valid(raise_exception=True)
        if not data.validated_data['confirm_bank_origin']:raise serializers.ValidationError('Confirm that selected rows were paid through the chosen bank account.')
        with locked_account(request.user,data.validated_data['account'].pk,['can_import_finance']) as account:
            if not migration_companies(request.user).filter(pk=batch.company_id).exists():raise PermissionDenied()
            derived=prepare(batch,account,request.user,data.validated_data['row_ids'])
        return Response(BankBatchSerializer(derived).data,status=201)

    def cash_account(self,request,batch,value):
        from .views import visible_accounts
        from django.shortcuts import get_object_or_404
        if not str(value).isdecimal():raise serializers.ValidationError('Choose a cash account.')
        return get_object_or_404(visible_accounts(request.user),pk=value,company_id=batch.company_id,kind='cash',currency=batch.company.default_currency)

    @action(detail=True,methods=['get'],url_path='cash-preview')
    def cash_preview(self,request,pk=None):
        from .migration_cash import cash_plan
        batch=self.get_object();account=self.cash_account(request,batch,request.query_params.get('account',''))
        return Response(cash_plan(batch,account))

    @action(detail=True,methods=['post'],url_path='import-cash')
    def import_cash(self,request,pk=None):
        from .posting_views import locked_account
        from .migration_cash import import_cash
        class Input(serializers.Serializer):
            account=serializers.IntegerField(min_value=1)
            expected_plan=serializers.CharField(min_length=64,max_length=64)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        selected=self.cash_account(request,batch,data.validated_data['account'])
        with locked_account(request.user,selected.pk,['can_import_finance'],bank_only=False) as account:
            if not migration_companies(request.user).filter(pk=batch.company_id).exists():raise PermissionDenied()
            if batch.status!='preview' or batch.file_issues:raise serializers.ValidationError('Use a readable workbook.')
            result=import_cash(batch,account,request.user,data.validated_data['expected_plan'])
        return Response(result)

    @action(detail=True,methods=['get','post'],url_path='cash-recovery')
    def cash_recovery(self,request,pk=None):
        from .migration_cash import recovery_plan,recover_cash
        from .posting_views import locked_account
        class Input(serializers.Serializer):
            account=serializers.IntegerField(min_value=1)
            mode=serializers.ChoiceField(choices=['undo','restore'])
            expected_plan=serializers.CharField(min_length=64,max_length=64,required=False)
            note=serializers.CharField(max_length=2000,allow_blank=False,required=False)
        data=Input(data=request.data if request.method=='POST' else request.query_params);data.is_valid(raise_exception=True)
        v=data.validated_data;batch=self.get_object();selected=self.cash_account(request,batch,v['account'])
        if request.method=='GET':return Response(recovery_plan(batch,selected,request.user,v['mode']))
        if not v.get('expected_plan') or not v.get('note'):raise serializers.ValidationError('Review the preview and provide a reason.')
        with locked_account(request.user,selected.pk,['can_import_finance','can_edit_finance'],bank_only=False) as account:
            if not migration_companies(request.user).filter(pk=batch.company_id).exists():raise PermissionDenied()
            return Response(recover_cash(batch,account,request.user,v['mode'],v['expected_plan'],v['note']))

    @action(detail=True,methods=['get'],url_path='alegra')
    def alegra(self,request,pk=None):
        from .migration_sales import read_workbook_sales
        from .sales_import_views import SalesBatchSerializer
        from .payment_views import PaymentBatchSerializer
        from .models import PaymentImportBatch
        batch=self.get_object()
        invoices=read_workbook_sales(bytes(batch.original_file))
        payments=read_payment_preview(bytes(batch.original_file))
        sales_batch=batch.sales_imports.select_related('company','posting').order_by('-pk').first()
        payment_batch=PaymentImportBatch.objects.filter(migration_batch=batch,selected_month__isnull=True).select_related('company','posting').order_by('-pk').first()
        return Response({'invoices':{'summary':invoices['summary'],'file_issues':invoices['file_issues']},
            'payments':{'summary':payments['summary'],'file_issues':payments['file_issues']},
            'sales_batch':SalesBatchSerializer(sales_batch).data if sales_batch else None,
            'payment_batch':PaymentBatchSerializer(payment_batch).data if payment_batch else None})

    @action(detail=True,methods=['post'],url_path='prepare-alegra')
    def prepare_alegra(self,request,pk=None):
        from .sales_posting_views import locked_company
        from .sales_import_views import SalesBatchSerializer
        from .payment_views import store,PaymentBatchSerializer
        from .migration_sales import read_workbook_sales
        from .models import SalesImportBatch,SalesImportRow,SalesImportInvoice,PaymentImportBatch
        source=self.get_object()
        with locked_company(request.user,source.company_id,['can_import_finance']) as company:
            if not migration_companies(request.user).filter(pk=company.pk).exists():raise PermissionDenied()
            sales=source.sales_imports.select_related('company','posting').order_by('-pk').first()
            payments=PaymentImportBatch.objects.filter(migration_batch=source,selected_month__isnull=True).select_related('company','posting').order_by('-pk').first()
            if not sales:
                content=bytes(source.original_file);parsed=read_workbook_sales(content)
                prior=SalesImportBatch.objects.filter(company=company,file_hash=source.file_hash).order_by('pk').first()
                sales=SalesImportBatch.objects.create(company=company,migration_batch=source,file_name=source.file_name,
                    file_hash=source.file_hash,byte_size=source.byte_size,original_file=content,encoding='xlsx',
                    parser_version=parsed['parser_version'],status='failed' if parsed['file_issues'] else 'preview',
                    summary=parsed['summary'],file_issues=parsed['file_issues'],duplicate_of=prior,uploaded_by=request.user)
                SalesImportRow.objects.bulk_create([SalesImportRow(batch=sales,**row) for row in parsed['rows']],batch_size=500)
                SalesImportInvoice.objects.bulk_create([SalesImportInvoice(batch=sales,**row) for row in parsed['invoices']],batch_size=500)
            if not payments:
                content=bytes(source.original_file)
                payments=store(company,request.user,content,read_payment_preview(content),source.file_name,source)
        return Response({'sales_batch':SalesBatchSerializer(sales).data,'payment_batch':PaymentBatchSerializer(payments).data})

    @action(detail=True,methods=['get'])
    def rows(self,request,pk=None):
        batch=self.get_object();qs=batch.rows.all()
        basis=request.query_params.get('basis','bank_date')
        if basis not in ('bank_date','operation_date','expense_period'):raise serializers.ValidationError({'basis':'Choose bank_date, operation_date or expense_period.'})
        scope=request.query_params.get('scope','selected')
        if scope not in ('selected','all'):raise serializers.ValidationError({'scope':'Choose selected or all.'})
        if scope=='selected':
            start=batch.selected_month;end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
            qs=qs.filter(**{basis+'__gte':start,basis+'__lt':end})
        start=serializers.DateField().run_validation(request.query_params['start']) if request.query_params.get('start') else None
        end=serializers.DateField().run_validation(request.query_params['end']) if request.query_params.get('end') else None
        if start and end and start>end:raise serializers.ValidationError('Start date must not follow end date.')
        if start:qs=qs.filter(**{basis+'__gte':start})
        if end:qs=qs.filter(**{basis+'__lte':end})
        kind=request.query_params.get('kind','all')
        if kind in ('credit','debit'):qs=qs.filter(kind=kind)
        elif kind!='all':raise serializers.ValidationError({'kind':'Choose credit, debit or all.'})
        included=list(qs.values('bank_date','amount','kind','issues'))
        review_count=sum(any(issue['code']!='payment_origin_unknown' for issue in row['issues']) for row in included)
        response=self.get_paginated_response(MigrationRowSerializer(self.paginate_queryset(qs),many=True).data)
        response.data['review_count']=review_count
        response.data['filtered_totals']=totals(included)
        return response

    @action(detail=True,methods=['get'],url_path='payments')
    def payments(self,request,pk=None):
        batch=self.get_object()
        scope=request.query_params.get('scope','selected')
        if scope not in ('selected','all'):raise serializers.ValidationError({'scope':'Choose selected or all.'})
        invoice=request.query_params.get('invoice','').strip().upper()
        import re
        if invoice and not re.fullmatch(r'B0[12]\d{8}',invoice):
            raise serializers.ValidationError({'invoice':'Use a complete B01/B02 invoice code.'})
        review=request.query_params.get('review','all')
        if review not in ('all','issues'):raise serializers.ValidationError({'review':'Choose all or issues.'})
        parsed=read_payment_preview(bytes(batch.original_file))
        rows=parsed['rows']
        if scope=='selected':rows=[r for r in rows if (r['date'] or '').startswith(batch.selected_month.strftime('%Y-%m'))]
        if invoice:rows=[r for r in rows if r['invoice_code']==invoice]
        if review=='issues':rows=[r for r in rows if r['issues']]
        response=self.get_paginated_response(self.paginate_queryset(rows))
        response.data.update(parser_version=parsed['parser_version'],file_issues=parsed['file_issues'],
            summary=parsed['summary'],filtered_summary=payment_totals(rows),selected_month=batch.selected_month.strftime('%Y-%m'))
        return response

    @action(detail=True,methods=['get'],url_path='source-row')
    def source_row(self,request,pk=None):
        batch=self.get_object();row_id=request.query_params.get('row','')
        if not row_id.isdecimal():raise serializers.ValidationError({'row':'Use a row ID.'})
        from django.shortcuts import get_object_or_404
        row=get_object_or_404(batch.rows,pk=row_id)
        try:
            labels,epoch1904=source_headers(bytes(batch.original_file),row.sheet)
        except (ValueError,KeyError,RuntimeError,OverflowError,zipfile.BadZipFile,ParseError):
            raise serializers.ValidationError('Could not read the saved source column labels.')
        return Response({**MigrationRowSerializer(row).data,'raw':row.raw,'cells':readable_cells(row,labels,epoch1904)})

    @action(detail=True,methods=['get'])
    def original(self,request,pk=None):
        if not can_use_finance(request.user,'can_import_finance'):raise PermissionDenied('Import permission is required to retrieve originals.')
        batch=self.get_object()
        response=FileResponse(io.BytesIO(bytes(batch.original_file)),as_attachment=True,filename=batch.file_name,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['X-Content-Type-Options']='nosniff';return response
