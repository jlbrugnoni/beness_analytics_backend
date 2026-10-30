from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core_data.models import Site, Studio
from finance.configuration_presets.loader import install_preset, load_preset
from finance.models import (
    Account, BankMovement, Category, Company, ConfigurationChange, FeePolicy,
    SourceMapping, Terminal,
)


class DominicanConfigurationPresetTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="Existing Dominican site", country_code="DO")
        self.actor = get_user_model().objects.create_superuser("preset-root@example.test", "LocalTest123!")
        for suffix in ["Arroyo Hondo", "Bella Vista", "Piantini"]:
            Studio.objects.create(site=self.site, name=f"Beness Pilates - {suffix}")

    def install(self, **kwargs):
        return install_preset(site=self.site, actor=self.actor, **kwargs)

    def test_default_dry_run_saves_no_configuration_or_audit(self):
        before = (Company.objects.count(), Account.objects.count(), ConfigurationChange.objects.count())
        counts = self.install()
        self.assertEqual(counts["terminals"]["created"], 9)
        self.assertEqual(before, (Company.objects.count(), Account.objects.count(), ConfigurationChange.objects.count()))

    def test_apply_preserves_links_and_financial_parameters_and_is_idempotent(self):
        original_studios = list(Studio.objects.values_list("pk", "name", "site_id"))
        first = self.install(apply=True)
        company = Company.objects.get(name="Beness Dominicana", site=self.site)
        self.assertEqual(company.default_currency, "DOP")
        self.assertEqual(Account.objects.filter(company=company).count(), 3)
        self.assertFalse(Account.objects.filter(company=company, name__icontains="QA").exists())
        savings = company.accounts.get(name__contains="ahorro")
        self.assertEqual(savings.opening_balance, 0)
        self.assertEqual(str(savings.opening_balance_date), "2026-01-01")
        self.assertFalse(savings.statement_imports_expected)
        self.assertEqual(company.accounts.get(kind="cash").opening_balance, None)
        terminal = Terminal.objects.get(account__company=company, identifier="39618800001")
        self.assertEqual(terminal.studio.site_id, self.site.pk)
        self.assertEqual(terminal.studio.name, "Beness Pilates - Piantini")
        self.assertEqual(terminal.channel, "card_terminal")
        self.assertEqual(Category.objects.filter(company=company).count(), 56)
        self.assertEqual(SourceMapping.objects.filter(company=company).count(), 11)
        self.assertEqual(str(FeePolicy.objects.get(company=company, channel="payment_link").percentage), "5.0000")
        self.assertEqual(ConfigurationChange.objects.filter(actor=self.actor).count(), 87)
        self.assertEqual(list(Studio.objects.values_list("pk", "name", "site_id")), original_studios)
        self.assertFalse(BankMovement.objects.exists())
        movement = BankMovement.objects.create(account=savings, provider="manual",
            source={"date": "2026-09-01", "amount": "1250.00", "description": "Existing destination record"},
            fingerprint="existing-destination-record", reconciled=True)
        movement_before = BankMovement.objects.filter(pk=movement.pk).values().get()
        audit_count = ConfigurationChange.objects.count()
        second = self.install(apply=True)
        self.assertEqual(BankMovement.objects.filter(pk=movement.pk).values().get(), movement_before)
        for section, result in second.items():
            self.assertEqual(result["created"], 0, section)
            self.assertEqual(result["unchanged"], first[section]["created"], section)
        self.assertEqual(ConfigurationChange.objects.count(), audit_count)

    def test_existing_conflicting_settings_are_not_overwritten(self):
        self.install(apply=True)
        fee = FeePolicy.objects.get(channel="payment_link")
        fee.percentage = 6
        fee.save()
        audit_count = ConfigurationChange.objects.count()
        with self.assertRaisesMessage(ValidationError, "percentage"):
            self.install(apply=True)
        fee.refresh_from_db()
        self.assertEqual(fee.percentage, 6)
        self.assertEqual(ConfigurationChange.objects.count(), audit_count)

    def test_missing_studios_and_wrong_country_fail_without_creating_company(self):
        studio = Studio.objects.get(site=self.site, name__contains="Piantini")
        studio.name = "Different name"
        studio.save()
        with self.assertRaisesMessage(ValidationError, "Piantini"):
            self.install(apply=True)
        self.site.country_code = "ES"
        self.site.save()
        with self.assertRaisesMessage(ValidationError, "Dominican Republic"):
            self.install(apply=True)
        self.assertFalse(Company.objects.filter(name="Beness Dominicana").exists())

    def test_late_failure_rolls_back_all_settings_and_audit(self):
        preset = deepcopy(load_preset())
        preset["fee_policies"][-1]["percentage"] = "200"
        with self.assertRaises(ValidationError):
            self.install(apply=True, preset=preset)
        self.assertFalse(Company.objects.filter(name="Beness Dominicana").exists())
        self.assertFalse(ConfigurationChange.objects.exists())
        with patch("finance.configuration_presets.loader.ConfigurationChange.objects.create", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.install(apply=True)
        self.assertFalse(Company.objects.filter(name="Beness Dominicana").exists())

    def test_requires_active_superuser_and_never_grants_permissions(self):
        self.actor.is_superuser = False
        self.actor.save()
        with self.assertRaisesMessage(ValidationError, "active superuser"):
            self.install(apply=True)
        self.assertFalse(Company.objects.filter(name="Beness Dominicana").exists())
        self.actor.refresh_from_db()
        self.assertFalse(self.actor.is_superuser)

    def test_command_defaults_to_preview(self):
        output = StringIO()
        call_command("install_beness_dominicana", site=self.site.pk, actor=self.actor.pk, stdout=output)
        self.assertIn("DRY RUN", output.getvalue())
        self.assertFalse(Company.objects.filter(name="Beness Dominicana").exists())
