"""Finance-only assignments over existing Analytics Mindbody source snapshots."""
from django.db import transaction
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core_data.models import Studio, SaleRawRow, ReportImport
from .access import can_use_finance
from .sales_import_views import SalesPreviewPermission
from .models import Company, MindbodySaleAssignment, MindbodySaleEvent, SourceMapping
from .configuration import ConfigurationConflict
from .workspace_views import companies_for
from . import mindbody


def company_for(user, pk):
    company = get_object_or_404(companies_for(user).filter(site__country_code='ES', default_currency='EUR'), pk=pk)
    if Company.objects.filter(site_id=company.site_id,active=True).exclude(pk=company.pk).exists():
        raise serializers.ValidationError('Choose a single authoritative finance company for this Mindbody site before using its sales.')
    return company


def public_sale(sale, user, payment_access=None):
    if payment_access is None:
        payment_access=can_use_finance(user,'can_view_finance_bank_accounts')
    if payment_access:
        return sale
    source={key:value for key,value in sale['source'].items() if key!='original_methods'}
    previous={key:value for key,value in (sale.get('previous_source') or {}).items() if key!='original_methods'}
    return {**sale,'source':source,'previous_source':previous or None,'payments':[], 'payment_count':None, 'payment_methods':[], 'assignments':{},
            'token':None,'source_hash':None}


def workspace(view, company, f):
    company = company_for(view.request.user, company.pk)
    rows = mindbody.sales(company) if f['kind']=='invoices' else []
    for row in rows:
        row['value'] = mindbody.money(row['source']['invoice_total'])
    if f.get('start'): rows=[r for r in rows if r['source']['date'] and r['source']['date']>=f['start'].isoformat()]
    if f.get('end'): rows=[r for r in rows if r['source']['date'] and r['source']['date']<=f['end'].isoformat()]
    if f.get('search'):
        term=f['search'].casefold()
        rows=[r for r in rows if term in r['code'].casefold() or term in r['source']['customer'].casefold()]
    if f.get('studio'): rows=[r for r in rows if r['studio']==f['studio']]
    if f.get('channel'):
        if not can_use_finance(view.request.user,'can_view_finance_bank_accounts'): raise PermissionDenied()
        rows=[r for r in rows if f['channel'] in r['payment_methods']]
    if f['status'] in ('review','unreviewed','reviewed'): rows=[r for r in rows if r['reviewed']==(f['status']=='reviewed')]
    elif f['status']=='reconciled': rows=[]
    key=f['sort'].lstrip('-')
    def order(row):
        value=row['value'] if key=='amount' else (row['source']['date'] or '') if key=='date' else row['code']
        return value,row['code']
    rows.sort(key=order,reverse=f['sort'].startswith('-'))
    total=sum((r['value'] for r in rows),Decimal(0))
    page=view.paginate_queryset(rows)
    payment_access=can_use_finance(view.request.user,'can_view_finance_bank_accounts')
    response=view.get_paginated_response([public_sale({k:v for k,v in row.items() if k!='value'},view.request.user,payment_access) for row in page])
    response.data.update(total=f'{total:.2f}',currency='EUR',provider='mindbody')
    return response


class MindbodySaleViewSet(viewsets.GenericViewSet):
    permission_classes=[IsAuthenticated,SalesPreviewPermission]
    http_method_names=['get','post','head','options']

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='private, no-store'
        return response

    def selection(self,request):
        class Input(serializers.Serializer):
            company=serializers.IntegerField(min_value=1)
            code=serializers.CharField(max_length=100)
        s=Input(data=request.query_params);s.is_valid(raise_exception=True)
        return company_for(request.user,s.validated_data['company']),s.validated_data['code']

    def current(self,company,code):
        rows=mindbody.sales(company,code)
        if not rows: raise NotFound('This Mindbody sale is not available in completed Analytics imports.')
        return rows[0]

    @action(detail=False,methods=['get'],url_path='detail')
    def sale_detail(self,request):
        company,code=self.selection(request)
        return Response(public_sale(self.current(company,code),request.user))

    @action(detail=False,methods=['get'])
    def history(self,request):
        company,code=self.selection(request)
        rows=SaleRawRow.objects.filter(site_id=company.site_id,report_import__report_type='sales',
            report_import__source_system='mindbody',report_import__status=ReportImport.STATUS_COMPLETED,
            **{'normalized_payload__No. de Venta':code}).select_related('report_import').order_by('report_import__processed_at','report_import_id','row_number')
        groups={}
        for row in rows:
            groups.setdefault(row.report_import_id,{'rows':[],'report':row.report_import_id,'file_name':row.report_import.file_name,
                'processed_at':row.report_import.processed_at,'actor':row.report_import.uploaded_by_id})['rows'].append({
                    'normalized_payload':row.normalized_payload,'is_valid':row.is_valid,'row_number':row.row_number})
        events=[];previous=None;previous_hash=None
        for group in groups.values():
            source,items,payments,_,source_hash=mindbody.build_source(code,group)
            if source_hash==previous_hash: continue
            snapshot={'source':source,'items':items,'payments':payments}
            events.append({'id':f"source-{group['report']}",'action':'source_import','created_at':group['processed_at'],
                'actor':group['actor'],'file_name':group['file_name'],'note':'Analytics source report',
                'before':previous or {},'after':snapshot})
            previous=snapshot;previous_hash=source_hash
        assignment=MindbodySaleAssignment.objects.filter(company=company,code=code).first()
        if assignment:
            events.extend(assignment.events.values('id','action','actor_id','before','after','note','created_at'))
        if not can_use_finance(request.user,'can_view_finance_bank_accounts'):
            for event in events:
                for side in ('before','after'):
                    event[side] = {key:value for key,value in event[side].items() if key!='payments'}
                    if 'source' in event[side]:
                        event[side]['source']={key:value for key,value in event[side]['source'].items() if key!='original_methods'}
        events.sort(key=lambda e:str(e['created_at'] or ''),reverse=True)
        return self.get_paginated_response(self.paginate_queryset(events))

    def write(self,request,operation):
        company,code=self.selection(request)
        cap='can_reopen_finance' if operation=='reopen' else 'can_edit_finance'
        if not can_use_finance(request.user,cap) or not can_use_finance(request.user,'can_view_finance_bank_accounts'):
            raise PermissionDenied()
        class Input(serializers.Serializer):
            expected_token=serializers.CharField(min_length=64,max_length=64)
            studio=serializers.IntegerField(min_value=1,allow_null=True,required=False)
            payments=serializers.DictField(required=False)
            note=serializers.CharField(max_length=2000,allow_blank=True,default='')
        allowed={'expected_token','note'} | ({'studio','payments'} if operation=='assign' else set())
        if set(request.data)-allowed: raise serializers.ValidationError('Source facts are read-only.')
        data=Input(data=request.data);data.is_valid(raise_exception=True);values=data.validated_data
        with transaction.atomic():
            company=Company.objects.select_for_update().get(pk=company.pk)
            if not company.active: raise serializers.ValidationError('Activate this company before editing sales.')
            current=self.current(company,code)
            if current['token']!=values['expected_token']: raise ConfigurationConflict('Mindbody source or assignments changed. Reload before saving.')
            if operation in ('assign','review') and current['locked']: raise ConfigurationConflict('Reopen this sale before editing or reviewing it.')
            if operation=='review' and current['missing_fields']: raise serializers.ValidationError({'missing_fields':current['missing_fields']})
            assignment=MindbodySaleAssignment.objects.filter(company=company,code=code).first()
            if not assignment:
                assignment=MindbodySaleAssignment(company=company,code=code)
            before={k:current[k] for k in ('source','studio','payments','reviewed','source_changed')}
            overrides=dict(assignment.assignments)
            valid_studios=set(Studio.objects.filter(site_id=company.site_id).values_list('pk',flat=True))
            def studio_ok(value):
                if value is not None and (isinstance(value,bool) or not isinstance(value,int) or value not in valid_studios):
                    raise serializers.ValidationError('Choose a studio in this company.')
            if operation=='assign':
                if not {'studio','payments'} & set(values): raise serializers.ValidationError('Choose an assignment to change.')
                if 'studio' in values:
                    studio_ok(values['studio']);overrides['studio']=values['studio']
                overrides['payments']=dict(overrides.get('payments',{}))
                for key,override in values.get('payments',{}).items():
                    if key not in {p['key'] for p in current['payments']} or not isinstance(override,dict) or not override or set(override)-{'channel','studio'}:
                        raise serializers.ValidationError('Choose an existing payment method and business assignments.')
                    if 'studio' in override: studio_ok(override['studio'])
                    if 'channel' in override and override['channel'] not in {'', *dict(SourceMapping.CHANNELS)}:
                        raise serializers.ValidationError('Choose a valid payment channel.')
                    overrides['payments'][key]={**overrides['payments'].get(key,{}),**override}
            assignment.assignments=overrides
            assignment.reviewed=operation=='review'
            assignment.source_hash=current['source_hash']
            assignment.source_snapshot=current['source']
            assignment.revision+=1 if assignment.pk else 0
            assignment.save()
            after=self.current(company,code)
            MindbodySaleEvent.objects.create(assignment=assignment,actor=request.user,action=operation,before=before,
                after={k:after[k] for k in ('source','studio','payments','reviewed','source_changed')},note=values['note'])
            company.sales_revision+=1
            company.save(update_fields=['sales_revision'])
        return Response(public_sale(after,request.user))

    @action(detail=False,methods=['post'])
    def assign(self,request): return self.write(request,'assign')

    @action(detail=False,methods=['post'])
    def review(self,request): return self.write(request,'review')

    @action(detail=False,methods=['post'])
    def reopen(self,request): return self.write(request,'reopen')
