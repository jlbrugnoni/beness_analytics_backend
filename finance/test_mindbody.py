from copy import deepcopy
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio, ReportImport, SaleRawRow
from .models import Company, SourceMapping, MindbodySaleAssignment, MindbodySaleEvent


@override_settings(FINANCE_ENABLED=True)
class MindbodyFinanceTests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('spain-finance@example.test')
        self.profile=get_or_create_user_access_profile(self.user)
        for cap in ('can_view_money','can_view_finance','can_view_sensitive_finance','can_view_finance_bank_accounts','can_edit_finance','can_reopen_finance'):
            setattr(self.profile,cap,True)
        self.profile.save()
        self.site=Site.objects.create(name='Spain bridge',country_code='ES')
        self.other_site=Site.objects.create(name='Other Spain',country_code='ES')
        self.studio=Studio.objects.create(site=self.site,name='Beness Pilates Estepona')
        self.other_studio=Studio.objects.create(site=self.site,name='Second studio')
        self.foreign=Studio.objects.create(site=self.other_site,name='Foreign studio')
        self.company=Company.objects.create(site=self.site,name='Spain bridge company',default_currency='EUR')
        self.profile.allowed_sites.add(self.site)
        self.client.force_authenticate(self.user)
        SourceMapping.objects.create(company=self.company,source_field='mindbody_studio',source_value=self.studio.name,studio=self.studio)
        for label,channel in [('Efectivo','cash'),('Card','card_terminal')]:
            SourceMapping.objects.create(company=self.company,source_field='mindbody_payment_method',source_value=label,channel=channel)

    def row(self,code='100',amount=50,method='Card',**extra):
        return {'No. de Venta':code,'_sale_date':'2026-10-06','ID del Cliente':'12','Cliente':'Test customer',
            'Localidad':self.studio.name,'Forma de Pago':method,'Nombre del artículo':'Test item',
            '_item_total':amount,'_paid_total':amount,'_quantity':1,'_item_price':amount,'_tax':0,**extra}

    def report(self,rows=None,status='completed',site=None,invalid=False):
        report=ReportImport.objects.create(report_type='sales',source_system='mindbody',file_name='sales.xlsx',status=status,
            processed_at=timezone.now(),uploaded_by=self.user)
        for n,payload in enumerate(rows or [self.row()],2):
            SaleRawRow.objects.create(report_import=report,site=site or self.site,row_number=n,row_hash=str(n),
                normalized_payload=payload,raw_payload=payload,is_valid=not invalid,validation_errors=['invalid'] if invalid else [])
        return report

    def detail(self,code='100',**params):
        return self.client.get('/api/finance/mindbody-sales/detail/',{'company':self.company.pk,'code':code,**params})

    def write(self,operation='reopen',code='100',token=None,**values):
        return self.client.post(f'/api/finance/mindbody-sales/{operation}/?company={self.company.pk}&code={code}',
            {'expected_token':token or self.detail(code).data['token'],**values},format='json')

    def listing(self,**params):
        return self.client.get('/api/finance/workspace/',{'company':self.company.pk,'kind':'invoices',**params})

    def test_multi_item_sales_group_payments_and_do_not_write_on_reads(self):
        self.report([self.row(amount=15),self.row(amount=55,**{'Nombre del artículo':'Second item'}),self.row(code='101',amount=20,method='Efectivo')])
        response=self.listing()
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['count'],2)
        self.assertEqual(response.data['total'],'90.00')
        sale=self.detail().data
        self.assertEqual(len(sale['items']),2)
        self.assertEqual(sale['payments'][0]['amount'],'70.00')
        self.assertTrue(sale['reviewed']);self.assertTrue(sale['locked'])
        self.assertFalse(MindbodySaleAssignment.objects.exists())
        self.assertEqual(self.listing(channel='cash').data['count'],1)
        self.assertEqual(self.listing(start='2026-11-01').data['count'],0)

    def test_repeat_uploads_stable_tokens_and_revised_source_replaces_whole_sale(self):
        self.report([self.row(amount=15),self.row(amount=55,**{'Nombre del artículo':'Second item'})])
        original=self.detail().data
        self.report([self.row(amount=15),self.row(amount=55,**{'Nombre del artículo':'Second item'})])
        self.assertEqual(original['token'],self.detail().data['token'])
        self.report([self.row(amount=80,method='Efectivo',_sale_date='2026-10-07')])
        sale=self.detail().data
        self.assertEqual(sale['source']['invoice_total'],'80.00')
        self.assertEqual(len(sale['items']),1)
        self.assertEqual(sale['source']['date'],'2026-10-07')
        self.assertEqual(sale['payments'][0]['channel'],'cash')
        self.assertFalse(sale['reviewed']);self.assertTrue(sale['source_changed']);self.assertTrue(sale['locked'])
        self.assertEqual(self.listing().data['count'],1)
        self.assertEqual(self.listing().data['total'],'80.00')
        self.report([self.row(code='101',amount=20)])
        self.assertEqual(self.detail().data['source']['invoice_total'],'80.00')

    def test_assignments_survive_changed_reports_and_review_locks_require_reopen(self):
        self.report()
        self.assertEqual(self.write('assign',studio=self.other_studio.pk).status_code,409)
        self.assertEqual(self.write().status_code,200)
        response=self.write('assign',studio=self.other_studio.pk,payments={'card':{'channel':'cash'}})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.write('review').status_code,200)
        self.report([self.row(amount=80)])
        sale=self.detail().data
        self.assertTrue(sale['source_changed']);self.assertFalse(sale['reviewed']);self.assertTrue(sale['locked'])
        self.assertEqual(sale['studio'],self.other_studio.pk)
        self.assertEqual(sale['payments'][0]['channel'],'cash')
        self.assertEqual(sale['previous_source']['invoice_total'],'50.00')
        self.assertEqual(self.write('review').status_code,409)
        self.profile.can_reopen_finance=False;self.profile.save()
        self.assertEqual(self.write().status_code,403)
        self.profile.can_reopen_finance=True;self.profile.save()
        self.assertEqual(self.write().status_code,200)
        self.assertEqual(self.write('review').status_code,200)
        self.assertTrue(self.detail().data['reviewed'])
        self.report([self.row(amount=80)])
        self.assertTrue(self.detail().data['reviewed'])
        self.assertEqual(MindbodySaleAssignment.objects.count(),1)
        self.assertEqual(MindbodySaleEvent.objects.count(),5)

    def test_stale_source_and_mapping_tokens_rejected(self):
        self.report();token=self.detail().data['token']
        self.report([self.row(amount=80)])
        self.assertEqual(self.write(token=token).status_code,409)
        token=self.detail().data['token']
        rule=SourceMapping.objects.get(company=self.company,source_value='Card')
        rule.channel='cash';rule.save()
        self.assertEqual(self.write(token=token).status_code,409)

    def test_explicit_reopen_never_relocks_on_repeat_and_source_facts_protected(self):
        self.report();self.assertEqual(self.write().status_code,200)
        self.report()
        self.assertFalse(self.detail().data['reviewed'])
        self.assertEqual(self.write('assign',source={'invoice_total':'1.00'}).status_code,400)
        self.assertEqual(self.write('assign',studio=self.foreign.pk).status_code,400)
        self.assertEqual(self.write('assign',payments={'not-a-method':{'channel':'cash'}}).status_code,400)
        self.assertEqual(self.detail().data['source']['invoice_total'],'50.00')

    def test_unknown_mapping_needs_review_and_manual_assignment_resolves_it(self):
        self.report([self.row(method='Unknown',Localidad='Unknown studio')])
        sale=self.detail().data
        self.assertFalse(sale['reviewed']);self.assertIn('studio',sale['missing_fields'])
        self.assertIn('payment_method',sale['missing_fields'])
        response=self.write('assign',studio=self.studio.pk,payments={'unknown':{'channel':'cash'}})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['missing_fields'],[])
        self.assertEqual(self.write('review').status_code,200)

    def test_completed_invalid_latest_group_blocks_review_and_failed_report_ignored(self):
        self.report();self.report([self.row(amount=999)],status='failed')
        self.assertEqual(self.detail().data['source']['invoice_total'],'50.00')
        self.report([self.row(amount=80)],invalid=True)
        sale=self.detail().data
        self.assertFalse(sale['reviewed']);self.assertIn('invalid_source_rows',sale['missing_fields'])
        self.assertEqual(self.write().status_code,200)
        self.assertEqual(self.write('review').status_code,400)

    def test_split_payment_rows_count_item_once_and_keep_two_methods(self):
        self.report([self.row(amount=50,_paid_total=30),self.row(amount=50,_paid_total=20,method='Efectivo')])
        sale=self.detail().data
        self.assertEqual(sale['source']['invoice_total'],'50.00')
        self.assertEqual(len(sale['items']),1);self.assertEqual(len(sale['payments']),2)
        self.assertEqual(sale['missing_fields'],[])
        self.assertEqual({p['amount'] for p in sale['payments']},{'30.00','20.00'})

    def test_mismatch_conflicting_customers_and_refunds_remain_pending(self):
        self.report([self.row(_paid_total=30),self.row(amount=10,**{'ID del Cliente':'other'})])
        sale=self.detail().data
        self.assertIn('source_customer_conflict',sale['missing_fields'])
        self.assertIn('item_payment_mismatch',sale['missing_fields'])
        self.assertEqual(self.write('review').status_code,400)
        self.report([self.row(amount=-50)])
        self.assertIn('refund_requires_review',self.detail().data['missing_fields'])

    def test_history_collapses_unchanged_imports_and_includes_finance_actions(self):
        self.report();self.report();self.write();self.report([self.row(amount=80)])
        response=self.client.get('/api/finance/mindbody-sales/history/',{'company':self.company.pk,'code':'100'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['count'],3)
        self.assertEqual(sum(e['action']=='source_import' for e in response.data['results']),2)

    def test_site_sensitive_bank_and_edit_permissions_enforced(self):
        self.report();self.report([self.row(code='foreign')],site=self.other_site)
        self.assertEqual(self.detail('foreign').status_code,404)
        self.assertEqual(self.write().status_code,200)
        self.profile.can_view_finance_bank_accounts=False;self.profile.save()
        self.assertEqual(self.detail().data['payments'],[])
        self.assertNotIn('original_methods',self.detail().data['source'])
        history=self.client.get('/api/finance/mindbody-sales/history/',{'company':self.company.pk,'code':'100'})
        self.assertTrue(all('payments' not in event['after'] and 'payments' not in event['before'] for event in history.data['results']))
        self.assertEqual(self.write(token='a'*64).status_code,403)
        self.assertEqual(self.listing(channel='cash').status_code,403)
        self.profile.can_view_sensitive_finance=False;self.profile.save()
        self.assertEqual(self.detail().status_code,403)
        self.profile.can_view_sensitive_finance=True;self.profile.save()
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.detail().status_code,404)
        self.assertEqual(self.listing().status_code,404)

    def test_multiple_companies_cannot_count_same_site_sales(self):
        self.report();Company.objects.create(site=self.site,name='Ambiguous company',default_currency='EUR')
        self.assertEqual(self.detail().status_code,400)
