"""Read-only daily workspace over the existing ledgers; no import interpretation."""
from decimal import Decimal
from django.db.models import Q, Count, Sum, DecimalField, Exists, OuterRef, Subquery, IntegerField, Prefetch
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core_data.access import get_or_create_user_access_profile, user_has_global_access
from core_data.models import Studio
from .access import can_use_finance, scoped_companies
from .sales_import_views import SalesPreviewPermission, sales_preview_companies
from .views import visible_accounts
from .bank_classification import presentation
from .models import Category, Company, BankMovement, FinancialSale, FinancialReceipt
from .sales_posting_views import FinancialSaleViewSet
from .payment_views import FinancialReceiptViewSet


def companies_for(user):
    qs=scoped_companies(Company.objects.select_related('site'),user)
    if not user_has_global_access(user) and get_or_create_user_access_profile(user).allowed_studios.exists():
        return qs.none()
    return qs


class WorkspaceViewSet(viewsets.GenericViewSet):
    permission_classes=[IsAuthenticated,SalesPreviewPermission]
    http_method_names=['get','head','options']

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='private, no-store'
        return response

    @action(detail=False,methods=['get'])
    def options(self,request):
        companies=companies_for(request.user)
        accounts=visible_accounts(request.user).filter(company__in=companies)
        return Response({'companies':[{'id':c.pk,'name':c.name,'country':c.site.country_code,
            'currency':c.default_currency,'active':c.active,'site':c.site_id} for c in companies],
            'accounts':list(accounts.values('id','company_id','name','currency','active','kind')),
            'studios':list(Studio.objects.filter(site_id__in=companies.values('site_id')).values('id','site_id','name')),
            'categories':[{'id':c.pk,'company':c.company_id,'parent':c.parent_id,'name':c.name,'active':c.effective_active} for c in Category.objects.filter(company__in=companies).select_related('parent')]})

    def list(self,request):
        class Filters(serializers.Serializer):
            company=serializers.IntegerField(min_value=1)
            kind=serializers.ChoiceField(choices=['debit','credit','invoices','unlinked'])
            start=serializers.DateField(required=False)
            end=serializers.DateField(required=False)
            search=serializers.CharField(required=False,allow_blank=True,max_length=200)
            account=serializers.IntegerField(required=False,min_value=1)
            studio=serializers.IntegerField(required=False,min_value=1)
            channel=serializers.CharField(required=False,allow_blank=True,max_length=24)
            category=serializers.IntegerField(required=False,min_value=1)
            subcategory=serializers.IntegerField(required=False,min_value=1)
            status=serializers.ChoiceField(choices=['all','review','missing_category','method_review','reviewed','unreviewed','reconciled','unreconciled'],default='all')
            sort=serializers.ChoiceField(choices=['date','-date','amount','-amount','number','-number'],default='-date')
        data=Filters(data=request.query_params);data.is_valid(raise_exception=True);f=data.validated_data
        company=get_object_or_404(companies_for(request.user),pk=f['company'])
        if f.get('start') and f.get('end') and f['start']>f['end']:
            raise serializers.ValidationError('Start must precede end.')
        kind=f['kind'];bank=kind in ('debit','credit')
        if not bank and f['status'] in ('missing_category','method_review','reviewed','unreviewed'):raise serializers.ValidationError('Choose a supported invoice status.')
        if bank:
            if not can_use_finance(request.user,'can_view_finance_bank_accounts'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            qs=BankMovement.objects.filter(account__in=visible_accounts(request.user).filter(company=company),active=True,source__direction=kind).select_related('account','created_from__batch','classification__category','classification__subcategory','classification__studio','classification__terminal').prefetch_related('classification__category__children')
            if f.get('account'):qs=qs.filter(account_id=f['account'])
            date_key='bank_date';amount_key='amount';number_key='reference'
            if f.get('search'):qs=qs.filter(Q(source__description__icontains=f['search'])|Q(source__reference__icontains=f['search'])|Q(source__serial__icontains=f['search'])|Q(classification__description__icontains=f['search']))
            for field in ('studio','channel','category','subcategory'):
                if f.get(field):qs=qs.filter(**{f'classification__{field}':f[field]})
            if f['status']=='review':
                children=Category.objects.filter(parent_id=OuterRef('classification__category_id'),active=True)
                qs=qs.annotate(has_subcategories=Exists(children))
                review=Q(classification__isnull=True)|Q(classification__movement_kind='')|Q(classification__reviewed=False)
                review|=(~Q(classification__movement_kind='internal_transfer')&Q(classification__studio__isnull=True,classification__administration=False))
                if kind=='debit':
                    review|=Q(classification__movement_kind__in=['expense','fee','extraordinary'])&(Q(classification__category__isnull=True)|Q(classification__expense_period__isnull=True)|Q(has_subcategories=True,classification__subcategory__isnull=True))
                else:review|=Q(classification__movement_kind='customer_receipt')&(Q(classification__channel='')|Q(classification__operation_date__isnull=True))
                qs=qs.filter(review)
            elif f['status']=='missing_category':qs=qs.filter(classification__category__isnull=True).exclude(classification__movement_kind='internal_transfer')
            elif f['status']=='method_review':qs=qs.filter(Q(classification__isnull=True)|Q(classification__channel=''))
            elif f['status']=='reviewed':qs=qs.filter(classification__reviewed=True)
            elif f['status']=='unreviewed':qs=qs.filter(Q(classification__isnull=True)|Q(classification__reviewed=False))
        elif kind=='invoices':
            get_object_or_404(sales_preview_companies(request.user),pk=company.pk)
            trouble=FinancialReceipt.objects.filter(sale_id=OuterRef('pk'),active=True).filter(~Q(link_issue='')|Q(assignments__channel_review=True)|Q(assignments__studio_origin='manual_pending'))
            counts=FinancialReceipt.objects.filter(sale_id=OuterRef('pk'),active=True).values('sale_id').annotate(n=Count('pk')).values('n')
            qs=FinancialSale.objects.filter(company=company,active=True).select_related('studio','created_from__batch').annotate(payment_count=Coalesce(Subquery(counts,output_field=IntegerField()),0),payment_review=Exists(trouble))
            if can_use_finance(request.user,'can_view_finance_bank_accounts'):
                qs=qs.prefetch_related(Prefetch('receipts',queryset=FinancialReceipt.objects.filter(active=True).only('id','sale_id','channel'),to_attr='workspace_receipts'))
            date_key='date';amount_key='invoice_total';number_key=None
            if f.get('search'):qs=qs.filter(Q(code__icontains=f['search'])|Q(source__customer__icontains=f['search']))
            if f.get('studio'):qs=qs.filter(studio_id=f['studio'])
            if f.get('channel'):
                if not can_use_finance(request.user,'can_view_finance_bank_accounts'):
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied()
                qs=qs.filter(Q(receipts__active=True,receipts__channel=f['channel'])|Q(channel=f['channel'])).distinct()
            if f['status']=='review':
                review=Q(assignments__requires_review=True)|Q(source__status_kind='cancelled',cancellation_treatment='pending')
                if can_use_finance(request.user,'can_view_finance_bank_accounts'):review|=Q(payment_review=True)|Q(payment_count=0)
                qs=qs.filter(review)
        else:
            if not can_use_finance(request.user,'can_view_finance_bank_accounts'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            get_object_or_404(sales_preview_companies(request.user),pk=company.pk)
            qs=FinancialReceipt.objects.filter(company=company,active=True,sale__isnull=True).select_related('studio','sale','created_from__batch')
            date_key='date';amount_key='amount';number_key=None
            if f.get('search'):qs=qs.filter(Q(number__icontains=f['search'])|Q(source__customer__icontains=f['search'])|Q(source__invoice_code__icontains=f['search']))
            if f.get('studio'):qs=qs.filter(studio_id=f['studio'])
            if f.get('channel'):qs=qs.filter(channel=f['channel'])
        if f.get('start'):qs=qs.filter(**{f'source__{date_key}__gte':f['start'].isoformat()})
        if f.get('end'):qs=qs.filter(**{f'source__{date_key}__lte':f['end'].isoformat()})
        if f['status'] in ('reconciled','unreconciled'):qs=qs.filter(reconciled=f['status']=='reconciled')
        qs=qs.annotate(value=Cast(KeyTextTransform(amount_key,'source'),DecimalField(max_digits=24,decimal_places=2)),record_date=KeyTextTransform(date_key,'source'))
        sort=f['sort'];field={'date':'record_date','amount':'value','number':'record_number'}[sort.lstrip('-')]
        if bank:qs=qs.annotate(record_number=KeyTextTransform(number_key,'source'))
        elif kind=='invoices':field='code' if field=='record_number' else field
        else:field='number' if field=='record_number' else field
        total=qs.aggregate(total=Sum('value'))['total'] or Decimal(0)
        qs=qs.order_by(('-' if sort.startswith('-') else '')+field,'-pk')
        rows=[]
        for obj in self.paginate_queryset(qs):
            if bank:
                rows.append({'id':obj.pk,'source':obj.source,'account':obj.account_id,'account_name':obj.account.name,
                    'reconciled':obj.reconciled,'file_name':obj.created_from.batch.file_name,'batch':obj.created_from.batch_id,
                    'source_row':obj.created_from.row_number,'revision':obj.revision,**presentation(obj)})
            elif kind=='invoices':
                item=FinancialSaleViewSet.serialize(obj)
                # Receipt detail requires the same bank/sensitive gate as before.
                item.update(payment_count=obj.payment_count if can_use_finance(request.user,'can_view_finance_bank_accounts') else None,
                    payment_methods=sorted({r.channel for r in getattr(obj,'workspace_receipts',[]) if r.channel}),
                    needs_review=bool(obj.assignments.get('requires_review') or (obj.payment_review or obj.payment_count==0 if can_use_finance(request.user,'can_view_finance_bank_accounts') else False) or (obj.source.get('status_kind')=='cancelled' and obj.cancellation_treatment=='pending')),
                    file_name=obj.created_from.batch.file_name,batch=obj.created_from.batch_id)
                rows.append(item)
            else:
                item=FinancialReceiptViewSet.serialize(obj);item.update(file_name=obj.created_from.batch.file_name,batch=obj.created_from.batch_id);rows.append(item)
        response=self.get_paginated_response(rows)
        response.data.update(total=f'{total:.2f}',currency=company.default_currency)
        return response
