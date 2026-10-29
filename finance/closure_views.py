"""Company-wide read-only monthly closure views with the existing finance gates."""
from datetime import date
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .access import can_use_finance
from .sales_import_views import SalesPreviewPermission
from .workspace_views import companies_for
from .views import visible_accounts
from .closures import CHANNELS,compare
from .closure_checks import attach_checks


RECORD_ISSUES = ('payment_link', 'payment_method', 'invalid_facts', 'source_currency',
    'studio_missing', 'method_review', 'studio_review', 'invoice_review',
    'movement_type', 'operation_date', 'unreviewed', 'cash_account', 'invoice_without_payments')


class ClosureViewSet(viewsets.GenericViewSet):
    permission_classes=[IsAuthenticated,SalesPreviewPermission]
    http_method_names=['get','post','head','options']

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='private, no-store';return response

    def comparison(self,request):
        if not can_use_finance(request.user,'can_view_finance_bank_accounts'):raise PermissionDenied()
        class Filters(serializers.Serializer):
            company=serializers.IntegerField(min_value=1)
            month=serializers.RegexField(r'^\d{4}-(0[1-9]|1[0-2])$')
            studio=serializers.IntegerField(min_value=1,required=False)
            channel=serializers.ChoiceField(choices=CHANNELS,required=False)
            day=serializers.DateField(required=False)
            side=serializers.ChoiceField(choices=['expected','actual','review','excluded'],required=False)
            issue=serializers.ChoiceField(choices=RECORD_ISSUES,required=False)
            def validate_month(self,value):
                try:date.fromisoformat(value+'-01')
                except ValueError:raise serializers.ValidationError('Use a valid month.')
                return value
        data=Filters(data=request.query_params);data.is_valid(raise_exception=True);f=data.validated_data
        company=get_object_or_404(companies_for(request.user),pk=f['company'])
        if f.get('studio'):
            from core_data.models import Studio
            get_object_or_404(Studio,pk=f['studio'],site_id=company.site_id)
        if f.get('day') and f['day'].isoformat()[:7]!=f['month']:raise serializers.ValidationError('Day must belong to selected month.')
        if company.site.country_code!='DO' or company.default_currency!='DOP':
            return {'supported':False,'company':company.pk,'month':f['month'],'currency':company.default_currency,'methods':[]},[],f
        accounts=visible_accounts(request.user).filter(company=company)
        # Never compare company-wide sales against a silently partial set of accounts.
        if company.accounts.exclude(pk__in=accounts.values('pk')).exists():raise PermissionDenied('Full company account visibility is required for closures.')
        summary,rows=compare(company,accounts,f['month'],f.get('studio'))
        attach_checks(company,summary,rows,f.get('studio'))
        summary['can_check']=company.active and can_use_finance(request.user,'can_edit_finance') and not f.get('studio')
        summary['can_reopen']=company.active and can_use_finance(request.user,'can_reopen_finance') and not f.get('studio')
        return summary,rows,f

    def list(self,request):
        summary,_,_=self.comparison(request)
        return Response(summary)

    @action(detail=False,methods=['get'])
    def evidence(self,request):
        _,rows,f=self.comparison(request)
        if f.get('issue'):rows=[r for r in rows if f['issue'] in r['issues']]
        if f.get('channel'):rows=[r for r in rows if r['channel']==f['channel']]
        if f.get('day'):rows=[r for r in rows if r['date']==f['day'].isoformat()]
        if f.get('side')=='review':rows=[r for r in rows if r['issues']]
        elif f.get('side')=='excluded':rows=[r for r in rows if r.get('excluded_kind')]
        elif f.get('side'):rows=[r for r in rows if r['side']==f['side'] and not r.get('excluded_kind')]
        return self.get_paginated_response(self.paginate_queryset(rows))

    def write_check(self,request,operation):
        from django.db import transaction
        from .models import Company
        from .closure_checks import save_check,reopen
        if not can_use_finance(request.user,'can_reopen_finance' if operation=='reopen' else 'can_edit_finance') or not can_use_finance(request.user,'can_view_finance_bank_accounts'):raise PermissionDenied()
        class Input(serializers.Serializer):
            company=serializers.IntegerField(min_value=1)
            day=serializers.DateField()
            channel=serializers.ChoiceField(choices=CHANNELS)
            expected_revision=serializers.IntegerField(min_value=0)
            expected_token=serializers.CharField(min_length=64,max_length=64,required=False)
            note=serializers.CharField(max_length=2000,allow_blank=True,required=False)
        data=Input(data=request.data);data.is_valid(raise_exception=True);v=data.validated_data
        with transaction.atomic():
            company=get_object_or_404(companies_for(request.user),pk=v['company'])
            company=Company.objects.select_for_update().get(pk=company.pk)
            if not company.active or company.site.country_code!='DO' or company.default_currency!='DOP':raise serializers.ValidationError('Choose an active Dominican company.')
            from .access import can_view_sensitive_detail
            if not can_view_sensitive_detail(request.user):raise PermissionDenied()
            accounts=visible_accounts(request.user).filter(company=company)
            if company.accounts.exclude(pk__in=accounts.values('pk')).exists():raise PermissionDenied()
            if operation=='check':
                if 'expected_token' not in v:raise serializers.ValidationError({'expected_token':'Refresh the comparison before checking.'})
                summary,rows=compare(company,accounts,v['day'].isoformat()[:7])
                item=save_check(company,request.user,summary,rows,v)
            else:item=reopen(company,request.user,v)
        return Response({'id':item.pk,'revision':item.revision,'state':item.state})

    @action(detail=False,methods=['post'],url_path='check')
    def check(self,request):return self.write_check(request,'check')

    @action(detail=False,methods=['post'])
    def reopen(self,request):return self.write_check(request,'reopen')

    @action(detail=False,methods=['get'])
    def history(self,request):
        from .models import ClosureCheckEvent
        _,_,f=self.comparison(request)
        if not f.get('day') or not f.get('channel'):raise serializers.ValidationError('Choose a day and payment method.')
        events=ClosureCheckEvent.objects.filter(closure__company_id=f['company'],closure__day=f['day'],closure__channel=f['channel']).select_related('actor')
        rows=[{'id':e.pk,'action':e.action,'actor':e.actor_id,'actor_name':((' '.join([e.actor.first_name,e.actor.last_name]).strip() or e.actor.email) if e.actor else None),'note':e.note,'created_at':e.created_at,'before':e.before,'after':e.after} for e in self.paginate_queryset(events)]
        return self.get_paginated_response(rows)
