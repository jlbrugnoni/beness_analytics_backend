from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .catalog import CATALOG_VERSION
from .models import Category, Company, ConfigurationChange


@override_settings(FINANCE_ENABLED=True)
class CategoryTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('category-manager@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for capability in ('can_view_money', 'can_view_finance', 'can_manage_finance_settings', 'can_view_sensitive_finance'):
            setattr(self.profile, capability, True)
        self.profile.save()
        self.site = Site.objects.create(name='DO', country_code='DO')
        self.other_site = Site.objects.create(name='ES', country_code='ES')
        self.studio = Studio.objects.create(site=self.site, name='Studio one')
        self.profile.allowed_sites.add(self.site)
        self.company = Company.objects.create(site=self.site, name='DO company', default_currency='DOP')
        self.other = Company.objects.create(site=self.other_site, name='ES company', default_currency='EUR')
        self.client.force_authenticate(self.user)

    def root(self, **values):
        return Category.objects.create(company=self.company, name='Personal', sensitive=True,
            default_treatment='operating', default_allocation='direct', **values)

    def create(self, **values):
        return self.client.post('/api/finance/categories/', {'company': self.company.pk, 'name': 'Servicios',
            'default_treatment': 'operating', 'default_allocation': 'direct', **values}, format='json')

    def update(self, obj, **values):
        return self.client.patch(f'/api/finance/categories/{obj.pk}/', {'expected_revision': obj.revision,
            **({'expected_parent_revision': obj.parent.revision} if obj.parent_id else {}), **values}, format='json')

    def initialize(self, company=None, **values):
        company = company or self.company
        return self.client.post(f'/api/finance/companies/{company.pk}/initialize-categories/',
            {'expected_revision': company.revision, **values}, format='json')

    def test_starting_catalog_has_shared_codes_and_company_local_edits(self):
        response = self.initialize()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 55)
        self.assertEqual(self.company.categories.filter(parent=None).count(), 10)
        self.assertEqual(self.company.categories.exclude(parent=None).count(), 45)
        self.profile.allowed_sites.add(self.other_site)
        self.assertEqual(self.initialize(self.other).status_code, 200)
        do = self.company.categories.get(catalog_code='servicios')
        es = self.other.categories.get(catalog_code='servicios')
        self.assertNotEqual(do.pk, es.pk)
        self.assertEqual(self.update(do, name='Servicios DR').status_code, 200)
        es.refresh_from_db(); self.assertEqual(es.name, 'Servicios')
        self.assertEqual(es.catalog_code, do.catalog_code)
        self.assertFalse(self.company.categories.filter(name='1').exists())
        self.assertTrue(self.company.categories.filter(parent__name='Otros', name='Extraordinarios').exists())

    def test_default_treatment_allocation_and_sensitivity(self):
        self.initialize()
        get = lambda parent, child: self.company.categories.get(parent__name=parent, name=child)
        salary = get('Personal', 'Sueldos')
        self.assertFalse(salary.sensitive)
        self.assertTrue(salary.effective_sensitive)
        self.assertEqual(salary.effective_treatment, 'operating')
        self.assertTrue(get('Administracion', 'Sueldos administración').effective_sensitive)
        self.assertTrue(get('Administracion', 'Seguridad social administración').effective_sensitive)
        self.assertFalse(get('Administracion', 'Contabilidad').effective_sensitive)
        self.assertEqual(get('Administracion', 'Contabilidad').effective_allocation, 'administration')
        self.assertEqual(get('Personal', 'Seguridad social').effective_treatment, 'operating')
        self.assertEqual(get('Administracion', 'Impuestos').effective_treatment, 'extraordinary')
        for parent, child in [('Operacion','Equipamiento'),('Bancos','Intereses'),('Bancos','Devoluciones')]:
            self.assertEqual(get(parent,child).effective_treatment,'review')
        self.assertEqual(get('Otros','Extraordinarios').effective_treatment,'extraordinary')

    def test_initialization_is_idempotent_and_preserves_customization(self):
        self.initialize()
        obj = self.company.categories.get(catalog_code='software')
        self.update(obj, name='Edited by client')
        count = ConfigurationChange.objects.count()
        response = self.initialize()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 0)
        obj.refresh_from_db(); self.assertEqual(obj.name,'Edited by client')
        self.assertEqual(ConfigurationChange.objects.count(), count)
        self.company.refresh_from_db(); self.assertEqual(self.company.category_catalog_version,CATALOG_VERSION)

    def test_initializer_preserves_existing_manual_catalog(self):
        self.root()
        self.assertEqual(self.initialize().status_code,409)
        self.assertEqual(self.company.categories.count(),1)

    def test_initializer_requires_revision_and_sensitive_scope_permissions(self):
        self.assertEqual(self.initialize(expected_revision=99).status_code,409)
        self.profile.can_view_sensitive_finance=False; self.profile.save()
        self.assertEqual(self.initialize().status_code,403)
        self.profile.can_view_sensitive_finance=True; self.profile.save()
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.initialize().status_code,403)
        self.assertEqual(Category.objects.count(),0)

    def test_catalog_and_company_audits_rollback_together(self):
        original = ConfigurationChange.objects.create
        calls=0
        def fail_later(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 4: raise RuntimeError('Audit unavailable')
            return original(**kwargs)
        with patch('finance.catalog.ConfigurationChange.objects.create', side_effect=fail_later):
            with self.assertRaises(RuntimeError): self.initialize()
        self.company.refresh_from_db()
        self.assertEqual(self.company.category_catalog_version,'')
        self.assertEqual(self.company.revision,1)
        self.assertEqual(Category.objects.count(),0)
        self.assertEqual(ConfigurationChange.objects.count(),0)

    def test_names_are_case_and_whitespace_normalized_within_parent(self):
        self.assertEqual(self.create(name=' Servicios ').status_code,201)
        self.assertEqual(self.create(name='ＳＥＲＶＩＣＩＯＳ').status_code,400)
        self.assertEqual(self.create(name='servicios').status_code,400)
        first=self.company.categories.get(name='Servicios')
        second=self.create(name='Otro').data
        self.assertEqual(self.create(name='Internet   y telefono',parent=first.pk,expected_parent_revision=1).status_code,201)
        self.assertEqual(self.create(name='internet y telefono',parent=first.pk,expected_parent_revision=1).status_code,400)
        self.assertEqual(self.create(name='Internet y telefono',parent=second['id'],expected_parent_revision=1).status_code,201)

    def test_maximum_two_levels_and_same_company_parent(self):
        root=self.root()
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos',default_treatment='',default_allocation='')
        self.assertEqual(self.create(parent=child.pk,expected_parent_revision=1).status_code,400)
        self.profile.allowed_sites.add(self.other_site)
        self.assertEqual(self.create(company=self.other.pk,parent=root.pk,expected_parent_revision=1).status_code,400)
        self.assertEqual(self.create(parent=99999,expected_parent_revision=1).status_code,400)

    def test_no_reparenting_or_company_change(self):
        root=self.root()
        other=Category.objects.create(company=self.company,name='Other')
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos')
        self.assertEqual(self.update(child,parent=other.pk).status_code,400)
        self.assertEqual(self.update(root,parent=root.pk,expected_parent_revision=1).status_code,400)
        self.profile.allowed_sites.add(self.other_site)
        self.assertEqual(self.update(root,company=self.other.pk).status_code,400)

    def test_root_requires_defaults_child_can_inherit(self):
        self.assertEqual(self.create(default_treatment='').status_code,400)
        root=self.root()
        response=self.create(parent=root.pk,name='Sueldos',default_treatment='',default_allocation='',expected_parent_revision=1)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['effective_treatment'],'operating')
        self.assertTrue(response.data['effective_sensitive'])

    def test_stale_child_and_stale_parent_do_not_overwrite(self):
        root=self.root()
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos')
        self.assertEqual(self.update(child,name='First').status_code,200)
        self.assertEqual(self.update(child,name='Stale').status_code,409)
        child.refresh_from_db()
        self.assertEqual(self.update(root,name='Personal renamed').status_code,200)
        self.assertEqual(self.update(child,name='Old parent',expected_parent_revision=1).status_code,409)
        child.refresh_from_db(); self.assertEqual(child.name,'First')

    def test_inherited_privacy_cannot_be_removed_by_child_false(self):
        root=self.root()
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos')
        response=self.update(child,sensitive=False)
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['effective_sensitive'])
        child.refresh_from_db()
        self.profile.can_view_sensitive_finance=False; self.profile.save()
        self.assertEqual(self.update(child,name='Attempt').status_code,403)
        self.assertEqual(self.update(root,sensitive=False).status_code,403)
        self.assertEqual(self.create(parent=root.pk,expected_parent_revision=1).status_code,403)

    def test_sensitive_descendant_protects_root_and_new_flag_requires_permission(self):
        root=Category.objects.create(company=self.company,name='Administracion',default_treatment='operating')
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos administración',sensitive=True)
        self.profile.can_view_sensitive_finance=False; self.profile.save()
        self.assertEqual(self.update(root,name='Changed').status_code,403)
        self.assertEqual(self.update(child,sensitive=False).status_code,403)
        self.assertEqual(self.create(name='Private',sensitive=True).status_code,403)
        ordinary=self.create(name='Public')
        self.assertEqual(ordinary.status_code,201)
        obj=Category.objects.get(pk=ordinary.data['id'])
        self.assertEqual(self.update(obj,sensitive=True).status_code,403)

    def test_sensitive_names_visible_but_edit_hints_follow_permissions(self):
        root=self.root()
        self.profile.can_view_sensitive_finance=False; self.profile.save()
        response=self.client.get(f'/api/finance/categories/{root.pk}/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data['effective_sensitive'])
        self.assertFalse(response.data['can_edit'])
        self.assertFalse(response.data['can_add_child'])
        self.assertNotIn('movements',response.data)

    def test_site_and_action_scope_enforced_without_bank_account_grant(self):
        root=self.root()
        self.assertEqual(self.client.get('/api/finance/categories/').status_code,200)
        foreign=Category.objects.create(company=self.other,name='Foreign')
        self.assertEqual(self.client.get(f'/api/finance/categories/{foreign.pk}/').status_code,404)
        self.assertEqual(self.create(company=self.other.pk).status_code,400)
        self.profile.allowed_studios.add(self.studio)
        self.assertEqual(self.update(root,name='No').status_code,403)
        self.assertEqual(self.create().status_code,403)
        self.profile.allowed_studios.clear()
        self.profile.can_manage_finance_settings=False; self.profile.save()
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.client.get('/api/finance/categories/').status_code,200)

    def test_deactivation_preserves_children_and_history(self):
        root=self.root()
        child=Category.objects.create(company=self.company,parent=root,name='Sueldos')
        response=self.update(root,active=False)
        self.assertEqual(response.status_code,200)
        response=self.client.get(f'/api/finance/categories/{child.pk}/')
        self.assertTrue(response.data['active']); self.assertFalse(response.data['effective_active'])
        root.refresh_from_db()
        self.assertEqual(self.create(parent=root.pk,expected_parent_revision=root.revision).status_code,400)
        self.assertEqual(self.client.delete(f'/api/finance/categories/{root.pk}/').status_code,405)
        self.assertEqual(self.update(root,active=True).status_code,200)
        child.refresh_from_db(); self.assertTrue(child.effective_active)
        self.assertEqual(ConfigurationChange.objects.count(),2)

    def test_rename_preserves_reference_and_code_and_audits(self):
        response=self.create()
        self.assertEqual(response.status_code,201,response.data)
        obj=Category.objects.get(pk=response.data['id']); code=obj.catalog_code
        self.assertEqual(self.update(obj,name='New name',catalog_code='attempt').status_code,200)
        obj.refresh_from_db(); self.assertEqual(obj.catalog_code,code)
        self.assertEqual(ConfigurationChange.objects.first().before['name'],'Servicios')
        self.assertEqual(ConfigurationChange.objects.first().after['name'],'New name')

    def test_company_with_only_categories_cannot_change_site(self):
        self.root(); self.profile.allowed_sites.add(self.other_site)
        response=self.client.patch(f'/api/finance/companies/{self.company.pk}/',{'site':self.other_site.pk,'expected_revision':1})
        self.assertEqual(response.status_code,400)

    def test_invalid_company_filter_and_no_scope(self):
        self.root()
        self.assertEqual(self.client.get('/api/finance/categories/?company=oops').status_code,400)
        self.profile.allowed_sites.clear()
        self.assertEqual(self.client.get('/api/finance/categories/').data['results'],[])

    @override_settings(FINANCE_ENABLED=False)
    def test_feature_flag_blocks_category_reads_and_writes_and_setup(self):
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.initialize().status_code,403)
        self.assertEqual(self.client.get('/api/finance/categories/').status_code,403)
