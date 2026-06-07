from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from analytics.models import MembershipMonthStatus
from core_data.importers import service_purchase_natural_key
from core_data.models import (
    Client,
    CustomUser,
    PricingOption,
    ReportImport,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    ServicePurchaseVersion,
    Site,
    Studio,
)
from core_data.purchase_repair import apply_purchase_repairs, audit_purchase_repairs


class PurchaseRepairTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(
            name="Repair Site",
            country_code=Site.COUNTRY_DOMINICAN_REPUBLIC,
        )
        self.studio = Studio.objects.create(site=self.site, name="Piantini")
        self.client = Client.objects.create(
            site=self.site,
            name="Repair Client",
            mindbody_id="repair-client",
        )
        category = ServiceCategory.objects.create(site=self.site, name="Memberships")
        self.option = PricingOption.objects.create(
            site=self.site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )

    def create_imported_purchase(self, suffix, activation_date, expiration_date):
        report_import = ReportImport.objects.create(
            report_type="sales_by_service",
            file_name=f"{suffix}.xlsx",
            status=ReportImport.STATUS_COMPLETED,
            studio=self.studio,
        )
        raw_row = ServicePurchaseRawRow.objects.create(
            report_import=report_import,
            site=self.site,
            studio=self.studio,
            row_number=2,
            row_hash=f"{suffix}-row-hash",
            raw_payload={},
            normalized_payload={},
            is_valid=True,
            validation_errors=[],
        )
        purchase = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key=f"{suffix}-natural-key",
            current_row_hash=f"{suffix}-row-hash",
            client=self.client,
            pricing_option=self.option,
            sale_date=date(2026, 3, 1),
            activation_date=activation_date,
            expiration_date=expiration_date,
            total_amount=Decimal("100.00"),
            quantity=Decimal("1.00"),
            first_seen_import=report_import,
            last_seen_import=report_import,
            source_raw_row=raw_row,
        )
        ServicePurchaseVersion.objects.create(
            service_purchase=purchase,
            report_import=report_import,
            raw_row=raw_row,
            row_hash=f"{suffix}-row-hash",
            changed_fields=["activation_date", "expiration_date"],
            snapshot={
                "activation_date": activation_date.isoformat(),
                "expiration_date": expiration_date.isoformat(),
            },
        )
        return purchase

    def test_safe_cross_import_date_change_is_merged(self):
        original = self.create_imported_purchase(
            "original",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        corrected = self.create_imported_purchase(
            "corrected",
            date(2026, 3, 5),
            date(2026, 4, 4),
        )
        status = MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio,
            month=date(2026, 4, 1),
            client=self.client,
            status=MembershipMonthStatus.STATUS_NOT_RENEWED,
            source_purchase=corrected,
        )

        audit = audit_purchase_repairs(site_id=self.site.id)
        self.assertEqual(audit["safe_group_count"], 1)
        self.assertEqual(audit["ambiguous_group_count"], 0)

        result = apply_purchase_repairs(site_id=self.site.id)

        self.assertEqual(result["merged_purchase_records"], 1)
        self.assertEqual(ServicePurchase.objects.count(), 1)
        original.refresh_from_db()
        status.refresh_from_db()
        self.assertEqual(original.activation_date, date(2026, 3, 5))
        self.assertEqual(original.expiration_date, date(2026, 4, 4))
        self.assertEqual(original.versions.count(), 2)
        self.assertEqual(status.source_purchase, original)

    def test_multiple_indistinguishable_rows_in_one_import_are_ambiguous(self):
        first = self.create_imported_purchase(
            "first",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        second = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="second-natural-key",
            current_row_hash="second-row-hash",
            client=self.client,
            pricing_option=self.option,
            sale_date=first.sale_date,
            activation_date=date(2026, 3, 10),
            expiration_date=date(2026, 4, 9),
            total_amount=first.total_amount,
            quantity=first.quantity,
            first_seen_import=first.first_seen_import,
            last_seen_import=first.last_seen_import,
            source_raw_row=first.source_raw_row,
        )
        ServicePurchaseVersion.objects.create(
            service_purchase=second,
            report_import=first.first_seen_import,
            raw_row=first.source_raw_row,
            row_hash="second-row-hash",
            changed_fields=[],
            snapshot={},
        )

        audit = audit_purchase_repairs(site_id=self.site.id)

        self.assertEqual(audit["safe_group_count"], 0)
        self.assertEqual(audit["ambiguous_group_count"], 1)

    def test_purchase_identity_ignores_activation_and_expiration_dates(self):
        payload = {
            "_occurrence_index": 1,
            "ID del Cliente": self.client.mindbody_id,
            "Nombre": self.option.name,
            "_sale_date": "2026-03-01",
            "_activation_date": "2026-03-01",
            "_expiration_date": "2026-03-31",
            "_total_amount": 100,
            "_quantity": 1,
        }
        original_key = service_purchase_natural_key(self.site, payload, self.studio)
        payload["_activation_date"] = "2026-03-05"
        payload["_expiration_date"] = "2026-04-04"

        self.assertEqual(
            service_purchase_natural_key(self.site, payload, self.studio),
            original_key,
        )

    @override_settings(ENABLE_PURCHASE_REPAIR=True)
    def test_maintenance_endpoint_requires_confirmation_before_apply(self):
        self.create_imported_purchase(
            "endpoint-original",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        self.create_imported_purchase(
            "endpoint-corrected",
            date(2026, 3, 5),
            date(2026, 4, 4),
        )
        user = CustomUser.objects.create_superuser(
            email="repair-admin@example.com",
            password="testpass123",
        )
        api = APIClient()
        api.force_authenticate(user)
        endpoint = "/api/data/report-imports/repair-sales-by-service-purchases/"

        audit_response = api.post(endpoint, {"site": self.site.id}, format="json")
        invalid_response = api.post(
            endpoint,
            {"site": self.site.id, "apply": True, "confirmation": "WRONG"},
            format="json",
        )
        apply_response = api.post(
            endpoint,
            {
                "site": self.site.id,
                "apply": True,
                "confirmation": "REPAIR PURCHASES",
            },
            format="json",
        )

        self.assertEqual(audit_response.status_code, 200)
        self.assertTrue(audit_response.data["dry_run"])
        self.assertEqual(audit_response.data["safe_group_count"], 1)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(apply_response.status_code, 200)
        self.assertFalse(apply_response.data["dry_run"])
        self.assertEqual(apply_response.data["merged_purchase_records"], 1)
