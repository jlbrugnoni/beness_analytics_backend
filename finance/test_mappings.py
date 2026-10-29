from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .models import Company, ConfigurationChange, SourceMapping


@override_settings(FINANCE_ENABLED=True)
class MappingTests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('mapping@example.test')
        self.profile=get_or_create_user_access_profile(self.user)
        for key in ('can_view_money','can_view_finance','can_manage_finance_settings'): setattr(self.profile,key,True)
        self.profile.save()
        self.site=Site.objects.create(name='DO mapping',country_code='DO')
        self.es=Site.objects.create(name='ES mapping',country_code='ES')
        self.company=Company.objects.create(site=self.site,name='DO company',default_currency='DOP')
        self.other=Company.objects.create(site=self.es,name='ES company',default_currency='EUR')
        self.studios={name:Studio.objects.create(site=self.site,name=name) for name in ('Bella Vista','Piantini','Arroyo Hondo')}
        self.foreign=Studio.objects.create(site=self.es,name='Estepona')
        self.profile.allowed_sites.add(self.site)
        self.client.force_authenticate(self.user)

    def setup_defaults(self, **overrides):
        return self.client.post(f'/api/finance/companies/{self.company.pk}/initialize-mappings/',
            {'studios':{k:v.pk for k,v in self.studios.items()},'expected_revision':self.company.revision,**overrides},format='json')

    def create(self, **values):
        return self.client.post('/api/finance/source-mappings/',{'company':self.company.pk,'source_field':'alegra_payment_method',
            'source_value':'Tarjeta débito','channel':'payment_link',**values},format='json')

    def preview(self, **values):
        return self.client.post('/api/finance/mapping-preview/',{'company':self.company.pk,'source':'alegra',
            'cost_center':'Bella Vista','price_list':'General','payment_method':'Efectivo',**values},format='json')

    def update(self,obj,**values):
        return self.client.patch(f'/api/finance/source-mappings/{obj.pk}/',{'expected_revision':obj.revision,**values},format='json')

    def test_approved_initial_payment_rules_and_primary_studio(self):
        response=self.setup_defaults(); self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['created'],11)
        for label,target,review in [('Tarjeta débito','payment_link',False),('Tarjeta crédito','card_terminal',True),('Efectivo','cash',False),('Transferencia','transfer',False)]:
            result=self.preview(payment_method=label)
            self.assertEqual(result.status_code,200,result.data)
            self.assertEqual(result.data['channel'],target)
            self.assertEqual(result.data['requires_review'],review)
            self.assertEqual(result.data['studio'],self.studios['Bella Vista'].pk)
            self.assertEqual(result.data['evidence']['price_list']['status'],'neutral')
        self.assertFalse(self.company.source_mappings.filter(source_field__startswith='mindbody').exists())

    def test_manual_recurring_correction_retains_source_and_rule_evidence(self):
        self.setup_defaults()
        response=self.preview(payment_method='Tarjeta crédito',manual_channel='recurring')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['channel'],'recurring')
        self.assertEqual(response.data['channel_origin'],'manual')
        self.assertFalse(response.data['requires_review'])
        self.assertIn('channel_mapping_requires_review',response.data['warnings'])
        source=response.data['evidence']['payment_method']
        self.assertEqual(source['source_value'],'Tarjeta crédito')
        self.assertEqual(source['channel'],'card_terminal')
        self.assertIsNotNone(source['rule_id'])
        self.assertEqual(source['rule_revision'],1)

    def test_cost_center_price_conflict_and_no_price_fallback(self):
        self.setup_defaults()
        response=self.preview(price_list='Piantini')
        self.assertEqual(response.data['studio'],self.studios['Bella Vista'].pk)
        self.assertTrue(response.data['requires_review'])
        self.assertIn('studio_conflict',response.data['warnings'])
        response=self.preview(cost_center='',price_list='Piantini')
        self.assertIsNone(response.data['studio'])
        self.assertTrue(response.data['requires_review'])
        response=self.preview(price_list='Piantini',manual_studio=self.studios['Arroyo Hondo'].pk)
        self.assertEqual(response.data['studio'],self.studios['Arroyo Hondo'].pk)
        self.assertFalse(response.data['requires_review'])
        self.assertIn('studio_conflict',response.data['warnings'])

    def test_unknown_inactive_and_explicit_review_do_not_fabricate_assignments(self):
        self.setup_defaults()
        response=self.preview(payment_method='New channel',cost_center='Unknown')
        self.assertIsNone(response.data['channel']);self.assertIsNone(response.data['studio'])
        self.assertTrue(response.data['requires_review'])
        obj=self.company.source_mappings.get(source_value='Efectivo')
        self.assertEqual(self.update(obj,active=False).status_code,200)
        self.assertIsNone(self.preview().data['channel'])
        self.assertEqual(self.create(source_value='Needs decision',channel='',behavior='review').status_code,201)
        response=self.preview(payment_method='Needs decision')
        self.assertEqual(response.data['evidence']['payment_method']['status'],'review')
        self.assertTrue(response.data['requires_review'])

    def test_normalization_is_exact_preserves_raw_and_distinguishes_fields(self):
        self.setup_defaults()
        raw='  TARJETA   crédito  '
        response=self.preview(payment_method=raw, cost_center='  bella   vista  ')
        self.assertEqual(response.data['channel'],'card_terminal')
        self.assertEqual(response.data['evidence']['payment_method']['source_value'],raw)
        self.assertEqual(self.create(source_value='ＴＡＲＪＥＴＡ débito').status_code,400)
        response=self.preview(payment_method='Tarjeta credito')
        self.assertIsNone(response.data['channel'])  # Accents are not guessed.
        self.assertEqual(self.create(source_value='Tarjeta débito',source_field='historical_payment_method',channel='card_terminal').status_code,201)

    def test_general_cannot_be_a_studio_and_is_neutral_without_a_rule(self):
        self.assertEqual(self.create(source_field='alegra_price_list',source_value='General',channel='',studio=self.studios['Piantini'].pk).status_code,400)
        self.assertEqual(self.preview().data['evidence']['price_list']['status'],'neutral')
        self.assertEqual(self.create(behavior='neutral',channel='').status_code,400)

    def test_target_validation_same_site_and_correct_target_type(self):
        self.profile.allowed_sites.add(self.es)
        self.assertEqual(self.create(studio=self.studios['Bella Vista'].pk).status_code,400)
        self.assertEqual(self.create(source_field='alegra_cost_center',channel='',studio=self.foreign.pk).status_code,400)
        self.assertEqual(self.create(source_field='alegra_cost_center',channel='').status_code,400)
        self.assertEqual(self.create(behavior='review',channel='cash').status_code,400)
        self.assertEqual(self.create(channel='not-a-channel').status_code,400)

    def test_scope_and_action_gates_without_bank_or_sensitive_grant(self):
        self.setup_defaults()
        self.assertEqual(self.preview().status_code,200)
        self.assertEqual(self.preview(company=self.other.pk).status_code,400)
        self.profile.allowed_studios.add(self.studios['Bella Vista'])
        self.assertEqual(self.preview().status_code,403)
        self.assertEqual(self.create(source_value='New').status_code,403)
        self.assertEqual(self.setup_defaults().status_code,403)
        rows=self.client.get('/api/finance/source-mappings/').data['results']
        self.assertTrue(all(not r['studio'] or r['studio']==self.studios['Bella Vista'].pk for r in rows))
        hidden=self.company.source_mappings.get(source_field='alegra_cost_center',source_value='Piantini')
        self.assertEqual(self.client.get(f'/api/finance/source-mappings/{hidden.pk}/').status_code,404)
        self.profile.allowed_studios.clear(); self.profile.can_manage_finance_settings=False;self.profile.save()
        self.assertEqual(self.preview().status_code,403)
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.client.get('/api/finance/source-mappings/').status_code,200)

    def test_starting_setup_preserves_edited_and_inactive_rules_on_repeat(self):
        self.setup_defaults()
        obj=self.company.source_mappings.get(source_value='Efectivo')
        self.update(obj,behavior='review',channel='',active=False)
        count=ConfigurationChange.objects.count()
        response=self.setup_defaults()  # Repeated request can recover despite old company revision.
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['created'],0)
        self.assertEqual(ConfigurationChange.objects.count(),count)
        obj.refresh_from_db();self.assertFalse(obj.active);self.assertEqual(obj.behavior,'review')
        self.assertEqual(self.company.source_mappings.count(),11)

    def test_initializer_validates_scope_studios_revision_and_country(self):
        self.assertEqual(self.setup_defaults(expected_revision=99).status_code,409)
        self.assertEqual(self.setup_defaults(studios={'Bella Vista':self.foreign.pk}).status_code,400)
        self.profile.allowed_sites.add(self.es)
        response=self.client.post(f'/api/finance/companies/{self.other.pk}/initialize-mappings/',{},format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(SourceMapping.objects.count(),0)

    def test_atomic_setup_and_config_audit_failure_roll_back(self):
        original=ConfigurationChange.objects.create; calls=0
        def fail(**kwargs):
            nonlocal calls
            calls+=1
            if calls==3:raise RuntimeError('audit unavailable')
            return original(**kwargs)
        with patch('finance.mapping.ConfigurationChange.objects.create', side_effect=fail):
            with self.assertRaises(RuntimeError):self.setup_defaults()
        self.assertEqual(SourceMapping.objects.count(),0)
        self.assertEqual(ConfigurationChange.objects.count(),0)
        self.company.refresh_from_db();self.assertEqual(self.company.revision,1)

    def test_revision_identity_and_deletion_protections(self):
        response=self.create();self.assertEqual(response.status_code,201,response.data)
        obj=SourceMapping.objects.get(pk=response.data['id'])
        self.assertEqual(self.update(obj,channel='cash').status_code,200)
        self.assertEqual(self.update(obj,channel='transfer').status_code,409)
        obj.refresh_from_db()
        self.assertEqual(self.update(obj,source_value='Renamed').status_code,400)
        self.assertEqual(self.update(obj,source_field='historical_payment_method').status_code,400)
        self.assertEqual(self.client.delete(f'/api/finance/source-mappings/{obj.pk}/').status_code,405)
        self.assertEqual(ConfigurationChange.objects.count(),2)

    def test_preview_does_not_save_manual_decisions_or_imports(self):
        self.setup_defaults();count=ConfigurationChange.objects.count()
        response=self.preview(manual_channel='recurring',manual_studio=self.studios['Piantini'].pk)
        self.assertEqual(response.status_code,200)
        self.assertEqual(ConfigurationChange.objects.count(),count)
        self.assertEqual(SourceMapping.objects.count(),11)
        response=self.preview(manual_channel=None,manual_studio=None)
        self.assertIsNone(response.data['channel']);self.assertIsNone(response.data['studio'])
        self.assertTrue(response.data['requires_review'])

    def test_manual_targets_and_source_input_validation(self):
        self.profile.allowed_sites.add(self.es)
        self.assertEqual(self.preview(manual_studio=self.foreign.pk).status_code,400)
        self.assertEqual(self.preview(manual_channel='invalid').status_code,400)
        self.assertEqual(self.preview(source='unknown').status_code,400)
        self.assertEqual(self.preview(source='mindbody').status_code,400)
        self.assertEqual(self.preview(studio_label='Unexpected').status_code,400)

    def test_spain_explicit_aliases_use_card_and_cash_without_guessing_names(self):
        self.profile.allowed_sites.add(self.es)
        for label,channel in [('Example card label','card_terminal'),('Example cash label','cash')]:
            self.assertEqual(self.create(company=self.other.pk,source_field='mindbody_payment_method',source_value=label,channel=channel).status_code,201)
        self.assertEqual(self.create(company=self.other.pk,source_field='mindbody_studio',source_value='Example studio',studio=self.foreign.pk,channel='').status_code,201)
        response=self.preview(company=self.other.pk,source='mindbody',cost_center='',price_list='',studio_label='Example studio',payment_method='Example card label')
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data['requires_review']);self.assertEqual(response.data['channel'],'card_terminal')
        self.assertEqual(self.other.source_mappings.count(),3)

    def test_company_with_only_mappings_cannot_change_site(self):
        self.create();self.profile.allowed_sites.add(self.es)
        self.assertEqual(self.client.patch(f'/api/finance/companies/{self.company.pk}/',{'site':self.es.pk,'expected_revision':1}).status_code,400)

    @override_settings(FINANCE_ENABLED=False)
    def test_disabled_feature_blocks_list_setup_preview_and_mutation(self):
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.setup_defaults().status_code,403)
        self.assertEqual(self.preview().status_code,403)
        self.assertEqual(self.client.get('/api/finance/source-mappings/').status_code,403)
