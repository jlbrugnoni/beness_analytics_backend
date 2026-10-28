from contextlib import contextmanager
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from core_data.models import Studio
from . import sales_posting as operations
from .access import can_use_finance
from .configuration import ConfigurationConflict
from .models import Company, FinancialSale, SalesPosting, SalesDecision, SalesEvent, SourceMapping
from .posting_views import may_undo
from .sales_import_views import SalesImportViewSet, SalesPreviewPermission, sales_preview_companies
from rest_framework.permissions import IsAuthenticated


@contextmanager
def locked_company(user, company_id, capabilities=(), active=True):
    with transaction.atomic():
        company = get_object_or_404(Company.objects.select_for_update(), pk=company_id)
        if not sales_preview_companies(user).filter(pk=company.pk).exists() or any(not can_use_finance(user, cap) for cap in capabilities):
            raise PermissionDenied('Sales action permission or company scope is unavailable.')
        if active and not company.active:
            raise serializers.ValidationError('Activate the company before changing sales.')
        yield company


class SalesEventSerializer(serializers.ModelSerializer):
    batch_id = serializers.IntegerField(source='posting.batch_id', read_only=True)
    class Meta:
        model = SalesEvent
        fields = ['id','batch_id','sale','actor','action','before','after','note','created_at']


class SalesPostingImportViewSet(SalesImportViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=True, methods=['get'])
    def processing(self, request, pk=None):
        class Filters(serializers.Serializer):
            outcome=serializers.ChoiceField(choices=['all','invalid'],default='all')
            search=serializers.CharField(required=False,allow_blank=True,max_length=100,default='')
        filters=Filters(data=request.query_params);filters.is_valid(raise_exception=True);f=filters.validated_data
        batch = self.get_object()
        with locked_company(request.user, batch.company_id, active=False) as company:
            result = operations.plan(batch, company); posting = result.pop('posting')
            pending=[row for row in result['rows'] if row['resolution']=='pending']
            result['pending_count']=len(pending)
            result['ready_count']=sum(row['outcome']=='unchanged' for row in pending)
            rows=result.pop('rows')
            result['invalid_count']=sum(row['outcome']=='invalid' for row in rows)
            if f['outcome']=='invalid':rows=[row for row in rows if row['outcome']=='invalid']
            if f['search']:rows=[row for row in rows if f['search'].casefold() in row['code'].casefold()]
            result['rows'] = self.get_paginated_response(self.paginate_queryset(rows)).data
            result['posting'] = {'id': posting.pk, 'status': posting.status, 'revision': posting.revision, 'actor':posting.actor_id} if posting else None
            result['can_commit'] = bool(not posting and batch.status == 'preview' and company.active and can_use_finance(request.user, 'can_import_finance'))
            result['can_review'] = bool(posting and posting.status == 'active' and company.active and can_use_finance(request.user,'can_import_finance') and can_use_finance(request.user,'can_edit_finance'))
            result['can_undo'] = bool(posting and posting.status in ('active','partial_undo') and company.active and may_undo(request.user,posting))
            return Response(result)

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        class Input(serializers.Serializer):
            expected_plan = serializers.CharField(min_length=64,max_length=64)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        with locked_company(request.user,batch.company_id,['can_import_finance']) as company:
            posting=operations.commit(batch,company,request.user,data.validated_data['expected_plan'])
            return Response({'posting_id':posting.pk,'status':posting.status})

    @action(detail=True,methods=['post'],url_path='apply-pending')
    def apply_pending(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_plan=serializers.CharField(min_length=64,max_length=64)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        with locked_company(request.user,batch.company_id,['can_import_finance','can_edit_finance']) as company:
            count=operations.apply_pending(batch,company,request.user,data.validated_data['expected_plan'])
        return Response({'linked':count,'status':'active'})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        class Input(serializers.Serializer):
            expected_plan=serializers.CharField(min_length=64,max_length=64)
            decision_id=serializers.IntegerField(min_value=1)
            expected_revision=serializers.IntegerField(min_value=1)
            action=serializers.ChoiceField(choices=['cancel','retain','correct_date'])
            note=serializers.CharField(max_length=2000,allow_blank=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);values=data.validated_data;batch=self.get_object()
        with locked_company(request.user,batch.company_id,['can_import_finance','can_edit_finance']) as company:
            if values['expected_plan'] != operations.token(company,batch): raise ConfigurationConflict('Sales changed. Reload the plan.')
            decision=get_object_or_404(SalesDecision.objects.select_related('sale','posting__batch'),pk=values['decision_id'],posting__batch=batch)
            operations.resolve(decision,company,request.user,values['action'],values['note'],values['expected_revision'])
            return Response({'resolution':decision.resolution})

    @action(detail=True, methods=['get'],url_path='undo-preview')
    def undo_preview(self,request,pk=None):
        batch=self.get_object()
        with locked_company(request.user,batch.company_id,active=False) as company:
            posting=get_object_or_404(SalesPosting,batch=batch)
            if not may_undo(request.user,posting):raise PermissionDenied('Undo requires import/edit access and ownership or financial settings authority.')
            return Response(operations.undo_plan(posting,company))

    @action(detail=True,methods=['post'])
    def undo(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_plan=serializers.CharField(min_length=64,max_length=64)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);batch=self.get_object()
        with locked_company(request.user,batch.company_id,['can_import_finance','can_edit_finance']) as company:
            posting=get_object_or_404(SalesPosting,batch=batch)
            if not may_undo(request.user,posting):raise PermissionDenied('You cannot undo this posting.')
            return Response(operations.undo(posting,company,request.user,data.validated_data['expected_plan'],data.validated_data['note']))


class FinancialSaleViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes=[IsAuthenticated,SalesPreviewPermission]
    http_method_names=['get','post','head','options']

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs);response['Cache-Control']='private, no-store';return response

    def get_queryset(self):
        qs=FinancialSale.objects.filter(company__in=sales_preview_companies(self.request.user)).select_related('company','studio')
        company=self.request.query_params.get('company')
        if company:
            if not company.isdecimal():raise serializers.ValidationError({'company':'Use a company ID.'})
            qs=qs.filter(company_id=company)
        code=self.request.query_params.get('code')
        if code:qs=qs.filter(code=code)
        return qs

    def list(self,request,*args,**kwargs):
        qs=self.get_queryset();state=request.query_params.get('state','active')
        if state not in ('active','all','reversed'):raise serializers.ValidationError('Choose active, all or reversed.')
        if state!='all':qs=qs.filter(active=state=='active')
        page=self.paginate_queryset(qs)
        return self.get_paginated_response([self.serialize(sale) for sale in page])

    @staticmethod
    def serialize(sale):
        result=operations.state(sale)
        result.update(company=sale.company_id,studio_name=sale.studio.name if sale.studio else None,
            contribution=sale.source['invoice_total'] if sale.active and sale.source['status_kind']=='paid' else '0.00')
        return result

    def retrieve(self,request,*args,**kwargs):
        return Response(self.serialize(self.get_object()))

    @action(detail=True,methods=['get'])
    def history(self,request,pk=None):
        sale=self.get_object();page=self.paginate_queryset(sale.events.select_related('posting'))
        return self.get_paginated_response(SalesEventSerializer(page,many=True).data)

    @action(detail=False,methods=['get'],url_path='options')
    def assignment_options(self,request):
        company=request.query_params.get('company','')
        if not company.isdecimal():raise serializers.ValidationError({'company':'Use a company ID.'})
        company=get_object_or_404(sales_preview_companies(request.user),pk=company)
        return Response({'studios':list(Studio.objects.filter(site_id=company.site_id).values('id','name')),
            'channels':[{'value':value,'label':label} for value,label in SourceMapping.CHANNELS]})

    @action(detail=True,methods=['post'])
    def assign(self,request,pk=None):
        class Input(serializers.Serializer):
            expected_revision=serializers.IntegerField(min_value=1)
            studio=serializers.PrimaryKeyRelatedField(queryset=Studio.objects.none(),allow_null=True,required=False)
            channel=serializers.ChoiceField(choices=[value for value,label in SourceMapping.CHANNELS],allow_null=True,required=False)
            cancellation_treatment=serializers.ChoiceField(choices=['pending','refund','no_refund','replacement'],required=False)
            replacement=serializers.PrimaryKeyRelatedField(queryset=FinancialSale.objects.none(),allow_null=True,required=False)
            note=serializers.CharField(max_length=2000,allow_blank=False)
        if set(request.data)-{'expected_revision','studio','channel','cancellation_treatment','replacement','note'}:raise serializers.ValidationError('Source facts are read-only.')
        original=self.get_object()
        with locked_company(request.user,original.company_id,['can_edit_finance']) as company:
            sale=get_object_or_404(self.get_queryset().select_for_update(of=('self',)),pk=original.pk,active=True)
            data=Input(data=request.data)
            data.fields['studio'].queryset=Studio.objects.filter(site_id=company.site_id)
            data.fields['replacement'].queryset=FinancialSale.objects.filter(company=company,active=True)
            data.is_valid(raise_exception=True);values=dict(data.validated_data)
            if values.pop('expected_revision')!=sale.revision:raise ConfigurationConflict('Sale changed. Reload before saving.')
            note=values.pop('note')
            if not any(key in values for key in ('studio','channel','cancellation_treatment')):raise serializers.ValidationError('Choose an assignment to change.')
            posting=get_object_or_404(SalesPosting,batch=sale.created_from.batch)
            operations.edit_sale(sale,posting,company,request.user,values,note)
            return Response(self.serialize(sale))
