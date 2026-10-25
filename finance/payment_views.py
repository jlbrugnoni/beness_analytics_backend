import hashlib
import io
from contextlib import contextmanager
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core_data.models import Studio
from .access import can_use_finance
from .configuration import ConfigurationConflict
from .migration_views import MigrationPermission, migration_companies
from .payment_preview import read_payment_preview, read_payment_csv, payment_totals
from .migration_reader import MAX_BYTES
from .models import Company, MigrationImportBatch, PaymentImportBatch, PaymentImportRow, PaymentPosting, PaymentDecision, FinancialReceipt, SourceMapping
from .posting_views import may_undo
from . import payment_posting as operations


@contextmanager
def locked(user,company_id,capabilities=(),active=True):
    with transaction.atomic():
        company=get_object_or_404(Company.objects.select_for_update(),pk=company_id)
        if not migration_companies(user).filter(pk=company.pk).exists() or any(not can_use_finance(user,c) for c in capabilities):
            raise PermissionDenied('Payment permissions or company scope changed.')
        if active and not company.active:raise serializers.ValidationError('Activate the company before changing payments.')
        yield company


class PrivatePayments(viewsets.ReadOnlyModelViewSet):
    permission_classes=[IsAuthenticated,MigrationPermission]
    http_method_names=['get','post','head','options']
    parser_classes=[JSONParser,MultiPartParser,FormParser]

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs);response['Cache-Control']='private, no-store';return response


class PaymentBatchSerializer(serializers.ModelSerializer):
    company_name=serializers.CharField(source='company.name',read_only=True)
    posting_status=serializers.SerializerMethodField()
    def get_posting_status(self,obj):
        posting=getattr(obj,'posting',None)
        return posting.status if posting else 'not_imported'
    class Meta:
        model=PaymentImportBatch
        fields=['id','company','company_name','origin','migration_batch','selected_month','file_name','file_hash',
            'parser_version','summary','file_issues','duplicate_of','uploaded_by','created_at','posting_status']


def store(company,actor,content,parsed,file_name,migration=None,month=None):
    digest=hashlib.sha256(content).hexdigest()
    prior=PaymentImportBatch.objects.filter(company=company,file_hash=digest,selected_month=month).order_by('pk').first()
    rows=parsed['rows']
    if month:rows=[r for r in rows if (r['date'] or '').startswith(month.strftime('%Y-%m'))]
    batch=PaymentImportBatch.objects.create(company=company,origin='migration' if migration else 'report',migration_batch=migration,
        selected_month=month,file_name=file_name,file_hash=digest,original_file=b'' if migration else content,
        parser_version=parsed['parser_version'],summary=payment_totals(rows),file_issues=parsed['file_issues'],duplicate_of=prior,uploaded_by=actor)
    PaymentImportRow.objects.bulk_create([PaymentImportRow(batch=batch,source_row=r['source_row'],source=r) for r in rows],batch_size=500)
    return batch


class PaymentImportViewSet(PrivatePayments):
    serializer_class=PaymentBatchSerializer
    def get_queryset(self):
        qs=PaymentImportBatch.objects.filter(company__in=migration_companies(self.request.user)).select_related('company','posting').defer('original_file')
        company=self.request.query_params.get('company')
        if company:
            if not company.isdecimal():raise serializers.ValidationError({'company':'Use a company ID.'})
            qs=qs.filter(company_id=company)
        return qs

    @action(detail=False,methods=['get'])
    def companies(self,request):
        return Response(list(migration_companies(request.user).values('id','name','active','default_currency')))

    def create(self,request):
        class Input(serializers.Serializer):
            company=serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())
            file=serializers.FileField(max_length=255,allow_empty_file=False)
        data=Input(data=request.data);data.fields['company'].queryset=migration_companies(request.user);data.is_valid(raise_exception=True)
        file=data.validated_data['file']
        if not file.name.lower().endswith('.csv') or file.size>MAX_BYTES:raise serializers.ValidationError('Choose a payment CSV up to 5 MiB.')
        content=file.read(MAX_BYTES+1);parsed=read_payment_csv(content)
        name=''.join(c for c in file.name.replace('\\','/').split('/')[-1] if ord(c)>=32)[:255]
        with locked(request.user,data.validated_data['company'].pk,['can_import_finance']) as company:
            batch=store(company,request.user,content,parsed,name)
        return Response(PaymentBatchSerializer(batch).data,status=201)

    @action(detail=False,methods=['post'],url_path='from-migration')
    def from_migration(self,request):
        class Input(serializers.Serializer):
            migration_batch=serializers.IntegerField(min_value=1)
            scope=serializers.ChoiceField(choices=['selected','all'],default='selected')
        data=Input(data=request.data);data.is_valid(raise_exception=True)
        source=get_object_or_404(MigrationImportBatch.objects.filter(company__in=migration_companies(request.user)),pk=data.validated_data['migration_batch'])
        with locked(request.user,source.company_id,['can_import_finance']) as company:
            parsed=read_payment_preview(bytes(source.original_file))
            month=source.selected_month if data.validated_data['scope']=='selected' else None
            batch=store(company,request.user,bytes(source.original_file),parsed,source.file_name,source,month)
        return Response(PaymentBatchSerializer(batch).data,status=201)

    @action(detail=True,methods=['get'])
    def processing(self,request,pk=None):
        batch=self.get_object()
        with locked(request.user,batch.company_id,active=False) as company:
            result=operations.plan(batch,company);posting=result.pop('posting')
            result['rows']=self.get_paginated_response(self.paginate_queryset(result['rows'])).data
            result.update(posting={'id':posting.pk,'status':posting.status,'revision':posting.revision} if posting else None,
                can_commit=bool(not posting and not batch.file_issues and batch.rows.exists() and company.active and can_use_finance(request.user,'can_import_finance')),
                can_review=bool(posting and posting.status=='active' and company.active and can_use_finance(request.user,'can_import_finance') and can_use_finance(request.user,'can_edit_finance')),
                can_undo=bool(posting and posting.status in ('active','partial_undo') and company.active and may_undo(request.user,posting)))
            return Response(result)

    @action(detail=True,methods=['post'])
    def commit(self,request,pk=None):
        class Input(serializers.Serializer):expected_plan=serializers.CharField(min_length=64,max_length=64)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        with locked(request.user,batch.company_id,['can_import_finance']) as company:
            posting=operations.commit(batch,company,request.user,data.validated_data['expected_plan'])
            return Response({'posting_id':posting.pk,'status':posting.status})

    @action(detail=True,methods=['get'],url_path='source-row')
    def source_row(self,request,pk=None):
        batch=self.get_object();row=request.query_params.get('row','')
        if not row.isdecimal():raise serializers.ValidationError('Use a source row ID.')
        return Response(get_object_or_404(batch.rows,pk=row).source)

    @action(detail=True,methods=['post'])
    def retain(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_plan=serializers.CharField(min_length=64,max_length=64)
            decision_id=serializers.IntegerField(min_value=1)
            expected_revision=serializers.IntegerField(min_value=1)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);v=data.validated_data;batch=self.get_object()
        with locked(request.user,batch.company_id,['can_import_finance','can_edit_finance']) as company:
            if v['expected_plan']!=operations.token(company,batch):raise ConfigurationConflict('Payments changed. Reload the plan.')
            d=get_object_or_404(PaymentDecision,posting__batch=batch,pk=v['decision_id'])
            operations.retain(d,company,request.user,v['note'],v['expected_revision']);return Response({'resolution':d.resolution})

    @action(detail=True,methods=['get'],url_path='undo-preview')
    def undo_preview(self,request,pk=None):
        batch=self.get_object()
        with locked(request.user,batch.company_id,active=False) as company:
            posting=get_object_or_404(PaymentPosting,batch=batch)
            if not may_undo(request.user,posting):raise PermissionDenied('Undo requires ownership or financial settings authority and import/edit access.')
            return Response(operations.undo_plan(posting,company))

    @action(detail=True,methods=['post'])
    def undo(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_plan=serializers.CharField(min_length=64,max_length=64)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        with locked(request.user,batch.company_id,['can_import_finance','can_edit_finance']) as company:
            posting=get_object_or_404(PaymentPosting,batch=batch)
            if not may_undo(request.user,posting):raise PermissionDenied('You cannot undo this posting.')
            return Response(operations.undo(posting,company,request.user,data.validated_data['expected_plan'],data.validated_data['note']))

    @action(detail=True,methods=['get'])
    def original(self,request,pk=None):
        if not can_use_finance(request.user,'can_import_finance'):raise PermissionDenied('Import permission is required.')
        batch=self.get_object();content=bytes(batch.migration_batch.original_file) if batch.migration_batch_id else bytes(batch.original_file)
        response=FileResponse(io.BytesIO(content),as_attachment=True,filename=batch.file_name)
        response['X-Content-Type-Options']='nosniff';return response


class FinancialReceiptViewSet(PrivatePayments):
    def get_queryset(self):
        qs=FinancialReceipt.objects.filter(company__in=migration_companies(self.request.user)).select_related('sale__studio','studio')
        company=self.request.query_params.get('company')
        if company:
            if not company.isdecimal():raise serializers.ValidationError('Use a company ID.')
            qs=qs.filter(company_id=company)
        return qs

    @staticmethod
    def serialize(receipt):
        result=operations.state(receipt)
        inherited=receipt.sale.studio_id if receipt.sale_id and receipt.assignments.get('studio_origin')=='invoice' else receipt.studio_id
        studio_name=(receipt.sale.studio.name if receipt.sale_id and receipt.sale.studio_id else None) if receipt.assignments.get('studio_origin')=='invoice' else receipt.studio.name if receipt.studio_id else None
        result.update(company=receipt.company_id,effective_studio=inherited,effective_studio_name=studio_name,invoice_code=receipt.source['invoice_code'])
        return result

    def list(self,request):
        qs=self.get_queryset();view=request.query_params.get('state','active')
        if view not in ('active','all'):raise serializers.ValidationError('Choose active or all.')
        if view=='active':qs=qs.filter(active=True)
        number=request.query_params.get('number')
        if number:qs=qs.filter(number=number)
        return self.get_paginated_response([self.serialize(r) for r in self.paginate_queryset(qs)])

    def retrieve(self,request,pk=None):return Response(self.serialize(self.get_object()))

    @action(detail=False,methods=['get'])
    def options(self,request):
        return Response({'channels':[{'value':v,'label':label} for v,label in SourceMapping.CHANNELS]})

    @action(detail=True,methods=['post'])
    def assign(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_revision=serializers.IntegerField(min_value=1)
            channel=serializers.ChoiceField(choices=[v for v,label in SourceMapping.CHANNELS],allow_null=True)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        original=self.get_object();data=Input(data=request.data);data.is_valid(raise_exception=True);v=data.validated_data
        with locked(request.user,original.company_id,['can_edit_finance']) as company:
            receipt=get_object_or_404(self.get_queryset(),pk=original.pk,active=True)
            if receipt.revision!=v['expected_revision']:raise ConfigurationConflict('Payment changed. Reload before saving.')
            if receipt.reconciled:raise serializers.ValidationError('Resolve the bank reconciliation before changing this payment.')
            before=operations.state(receipt);receipt.channel=v['channel'] or ''
            receipt.assignments={**receipt.assignments,'channel':v['channel'],'channel_origin':'manual','channel_review':not bool(v['channel'])}
            receipt.edited=True;receipt.revision+=1;receipt.save(update_fields=['channel','assignments','edited','revision'])
            operations.event(PaymentPosting.objects.get(batch=receipt.created_from.batch),request.user,'assign',receipt,before,v['note'])
            operations.advance(company);return Response(self.serialize(receipt))

    @action(detail=True,methods=['get'])
    def history(self,request,pk=None):
        receipt=self.get_object()
        events=receipt.events.values('id','posting__batch_id','actor_id','action','before','after','note','created_at')
        return self.get_paginated_response(self.paginate_queryset(events))
