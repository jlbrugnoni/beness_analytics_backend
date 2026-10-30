import csv
import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from core_data.access import get_or_create_user_access_profile
from core_data.models import Site, Studio
from .catalog import create_starting_catalog
from .catalog_transfer import FIELDS, export_catalog, starting_rows
from .models import Account, BankMovement, BankMovementClassification, Category, Company, ConfigurationChange


@override_settings(FINANCE_ENABLED=True)
class CatalogTransferTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('catalog-transfer@example.test')
        self.profile = get_or_create_user_access_profile(self.user)
        for flag in ['can_view_money', 'can_view_finance', 'can_import_finance_migration', 'can_view_sensitive_finance']:
            setattr(self.profile, flag, True)
        self.profile.save()
        self.site = Site.objects.create(name='Catalog DO', country_code='DO')
        self.profile.allowed_sites.add(self.site)
        self.company = Company.objects.create(name='Beness Dominicana', site=self.site, default_currency='DOP')
        self.url = f'/api/finance/category-catalog/{self.company.pk}/'
        self.client.force_authenticate(self.user)

    def upload(self, rows=None, raw=None):
        if raw is None:
            output = io.StringIO(newline='')
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows or []:
                writer.writerow({key: str(value).lower() if isinstance(value, bool) else value for key, value in row.items()})
            raw = output.getvalue().encode('utf-8-sig')
        return SimpleUploadedFile('catalog.csv', raw, content_type='text/csv')

    def transfer(self, rows=None, token=None, **options):
        body = {'source': 'csv', 'mode': 'merge', **options}
        if body['source'] == 'csv':
            body['file'] = self.upload(rows=rows)
        if token:
            body['expected_plan'] = token
        return self.client.post(self.url, body, format='multipart')

    def apply(self, rows=None, **options):
        preview = self.transfer(rows=rows, **options)
        self.assertEqual(preview.status_code, 200, preview.data)
        response = self.transfer(rows=rows, token=preview.data['token'], **options)
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_restore_preview_changes_nothing_and_apply_is_repeatable(self):
        preview = self.transfer(source='starting')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['counts']['created'], 55)
        self.assertFalse(self.company.categories.exists())
        self.assertFalse(ConfigurationChange.objects.exists())
        self.company.refresh_from_db()
        self.assertEqual(self.company.revision, 1)
        applied = self.transfer(source='starting', token=preview.data['token'])
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertTrue(applied.data['applied'])
        self.assertEqual(self.company.categories.count(), 55)
        count = ConfigurationChange.objects.count()
        self.assertEqual(self.apply(source='starting').data['counts']['unchanged'], 55)
        self.assertEqual(ConfigurationChange.objects.count(), count)

    def test_csv_export_and_import_across_companies_preserve_every_configuration_field(self):
        self.apply(source='starting')
        exported = self.client.get(self.url)
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn('attachment', exported['Content-Disposition'])
        other = Company.objects.create(name='Other destination', site=self.site, default_currency='DOP')
        self.url = f'/api/finance/category-catalog/{other.pk}/'
        preview = self.client.post(self.url, {'file': self.upload(raw=exported.content)}, format='multipart')
        self.assertEqual(preview.status_code, 200, preview.data)
        response = self.client.post(self.url, {'file': self.upload(raw=exported.content), 'expected_plan': preview.data['token']}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        def facts(company):
            return sorted((obj.catalog_code, obj.parent.catalog_code if obj.parent_id else '', obj.name,
                obj.default_treatment, obj.default_allocation, obj.sensitive, obj.active)
                for obj in company.categories.select_related('parent'))
        self.assertEqual(facts(self.company), facts(other))
        self.assertNotEqual(self.company.categories.first().pk, other.categories.first().pk)

    def test_starting_defaults_equal_existing_initializer(self):
        create_starting_catalog(self.company, self.user)
        response = self.apply(source='starting')
        self.assertEqual(response.data['counts']['unchanged'], 55)

    def test_merge_and_replace_preserve_category_ids_and_classified_expenses(self):
        self.apply(source='starting')
        root = self.company.categories.get(catalog_code='servicios')
        child = self.company.categories.get(catalog_code='servicios-01')
        extra = Category.objects.create(company=self.company, name='Extra custom category')
        account = Account.objects.create(company=self.company, name='Cash', kind='cash', currency='DOP')
        movement = BankMovement.objects.create(account=account, provider='manual', fingerprint='existing', source={'amount': '-100.00'})
        classification = BankMovementClassification.objects.create(movement=movement, category=root, subcategory=child, reviewed=True)
        before = BankMovementClassification.objects.filter(pk=classification.pk).values().get()
        rows = [row for row in starting_rows() if row['catalog_code'] in ('servicios', 'servicios-01')]
        rows[1]['name'] = 'Electricidad actualizada'
        self.apply(rows=rows)
        extra.refresh_from_db()
        self.assertTrue(extra.active)
        response = self.apply(rows=rows, mode='replace')
        self.assertGreater(response.data['counts']['archived'], 0)
        extra.refresh_from_db()
        self.assertFalse(extra.active)
        self.assertEqual(Category.objects.get(pk=child.pk).name, 'Electricidad actualizada')
        self.assertEqual(BankMovementClassification.objects.filter(pk=classification.pk).values().get(), before)
        self.assertEqual(self.company.categories.count(), 56)

    def test_manual_categories_reused_by_name_without_changing_their_codes(self):
        root = Category.objects.create(company=self.company, name='Servicios')
        child = Category.objects.create(company=self.company, parent=root, name='Electricidad')
        codes = (root.catalog_code, child.catalog_code)
        rows = [row for row in starting_rows() if row['catalog_code'] in ('servicios', 'servicios-01')]
        result = self.apply(rows=rows)
        self.assertEqual(result.data['counts']['created'], 0)
        self.assertEqual(self.company.categories.count(), 2)
        root.refresh_from_db(); child.refresh_from_db()
        self.assertEqual((root.catalog_code, child.catalog_code), codes)
        self.assertEqual(child.parent_id, root.pk)

    def test_stale_preview_or_changed_file_or_options_requires_preview_again(self):
        preview = self.transfer(source='starting')
        extra = Category.objects.create(company=self.company, name='Concurrent category')
        result = self.transfer(source='starting', token=preview.data['token'])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.company.categories.count(), 1)
        rows = starting_rows()
        preview = self.transfer(rows=rows)
        rows[-1]['name'] = 'Changed after preview'
        self.assertEqual(self.transfer(rows=rows, token=preview.data['token']).status_code, 409)
        self.assertEqual(self.transfer(rows=starting_rows(), mode='replace', token=preview.data['token']).status_code, 409)
        self.assertTrue(Category.objects.filter(pk=extra.pk).exists())

    def test_wrong_actor_or_invalid_token_denied(self):
        self.assertEqual(self.transfer(source='starting', token='invalid').status_code, 409)
        preview = self.transfer(source='starting')
        second = get_user_model().objects.create_superuser('other-root@example.test', 'TestPassword123!')
        self.client.force_authenticate(second)
        self.assertEqual(self.transfer(source='starting', token=preview.data['token']).status_code, 409)
        self.assertFalse(self.company.categories.exists())

    def test_permissions_require_migration_sensitive_and_company_wide_scope(self):
        self.profile.can_import_finance_migration = False
        self.profile.can_manage_finance_settings = True
        self.profile.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.transfer(source='starting').status_code, 403)
        self.profile.can_import_finance_migration = True
        self.profile.can_view_sensitive_finance = False
        self.profile.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.profile.can_view_sensitive_finance = True
        self.profile.save()
        self.profile.allowed_studios.add(Studio.objects.create(site=self.site, name='Partial studio'))
        self.assertEqual(self.transfer(source='starting').status_code, 403)
        self.assertFalse(self.company.categories.exists())

    def test_other_company_and_anonymous_denied(self):
        other_site = Site.objects.create(name='Other country', country_code='ES')
        other = Company.objects.create(name='No scope', site=other_site, default_currency='EUR')
        self.assertEqual(self.client.get(f'/api/finance/category-catalog/{other.pk}/').status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_invalid_files_and_duplicate_codes_rejected_without_partial_changes(self):
        raw_files = [b'bad,headers\n1,2\n', b'\xff\xfe\x00', b'', b'a' * (2 * 1024 * 1024 + 1)]
        for raw in raw_files:
            with self.subTest(raw_length=len(raw)):
                result = self.client.post(self.url, {'file': self.upload(raw=raw)}, format='multipart')
                self.assertEqual(result.status_code, 400)
        rows = starting_rows()
        rows[-1]['catalog_code'] = rows[0]['catalog_code']
        self.assertEqual(self.transfer(rows=rows).status_code, 400)
        self.assertFalse(self.company.categories.exists())

    def test_invalid_hierarchy_names_booleans_and_late_validation_rollback(self):
        for mutate in [lambda rows: rows[-1].update(parent_code='absent'),
                       lambda rows: rows[-1].update(name=''),
                       lambda rows: rows[-1].update(sensitive='not-a-boolean'),
                       lambda rows: rows[-1].update(default_treatment='invalid')]:
            rows = starting_rows(); mutate(rows)
            self.assertEqual(self.transfer(rows=rows).status_code, 400)
            self.assertFalse(self.company.categories.exists())
            self.assertFalse(ConfigurationChange.objects.exists())

    def test_parent_changes_refused_and_audit_failure_rolls_back(self):
        self.apply(source='starting')
        rows = starting_rows(); rows[-1]['parent_code'] = 'bancos'
        result = self.transfer(rows=rows)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.company.categories.get(catalog_code='otros-02').parent.catalog_code, 'otros')
        preview = self.transfer(source='starting')
        # Force an update so an audit write occurs.
        obj = self.company.categories.get(catalog_code='servicios'); obj.name = 'Renamed'; obj.save()
        preview = self.transfer(source='starting')
        with patch('finance.catalog_transfer.ConfigurationChange.objects.create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.transfer(source='starting', token=preview.data['token'])
        obj.refresh_from_db(); self.assertEqual(obj.name, 'Renamed')

    def test_formula_like_names_export_safely_and_round_trip(self):
        root = Category.objects.create(company=self.company, name='=HYPERLINK("bad")')
        exported = export_catalog(self.company)
        self.assertIn("'=HYPERLINK", exported.content.decode('utf-8-sig'))
        raw = exported.content.replace(b',', b';')
        preview = self.client.post(self.url, {'file': self.upload(raw=raw)}, format='multipart')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['rows'][0]['name'], root.name)
        self.assertEqual(preview.data['counts']['unchanged'], 1)

    def test_inactive_company_cannot_import(self):
        self.company.active = False; self.company.save()
        self.assertEqual(self.transfer(source='starting').status_code, 400)
