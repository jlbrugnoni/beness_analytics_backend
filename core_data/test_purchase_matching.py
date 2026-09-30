from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .importers import SALES_BY_SERVICE_REQUIRED_HEADERS, import_sales_by_service_report
from .models import (
    CustomUser, ReportImport, ServicePurchase, ServicePurchaseMatchReview,
    Site, Studio, UserAccessProfile,
)
from .test_analytics_import_guards import excel_serial, xlsx_upload


class PurchaseMatchingTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="Purchase Review Test Site", country_code="DO")
        self.studio = Studio.objects.create(site=self.site, name="Piantini")
        self.user = CustomUser.objects.create_superuser(email="review@example.com", password="test")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.url = "/api/data/purchase-match-reviews/"

    def row(self, activation="2026-06-01", expiration="2026-06-30", client="123", amount="100"):
        return ["Monthly", client, "Test Client", "Membership", "", excel_serial(date(2026, 6, 1)), excel_serial(date.fromisoformat(activation)),
                "0", excel_serial(date.fromisoformat(expiration)), amount, amount, "0", "1"]

    def upload(self, rows):
        return import_sales_by_service_report(
            xlsx_upload("purchases.xlsx", SALES_BY_SERVICE_REQUIRED_HEADERS, rows),
            self.site, self.user, studio=self.studio,
        )["import"]

    def ambiguous(self):
        self.upload([self.row(), self.row("2026-07-01", "2026-07-31")])
        return self.upload([self.row("2026-06-02", "2026-07-01"), self.row("2026-07-02", "2026-08-01")])

    def resolve(self, review, decision, purchase=None, **extra):
        data = {"decision": decision, "raw_row_id": review.latest_raw_row_id, "note": "Checked report"}
        if purchase:
            data.update(purchase_id=purchase.id, purchase_updated_at=purchase.updated_at.isoformat())
        data.update(extra)
        return self.api.post(f"{self.url}{review.pk}/resolve/", data, format="json")

    def test_unchanged_overlapping_upload_is_idempotent(self):
        self.upload([self.row()])
        result = self.upload([self.row()])
        self.assertEqual(result["service_purchases_identical"], 1)
        self.assertEqual(ServicePurchase.objects.count(), 1)
        self.assertFalse(ServicePurchaseMatchReview.objects.exists())

    def test_reordered_repeated_purchases_keep_their_identifiers(self):
        a, b = self.row(), self.row("2026-07-01", "2026-07-31")
        self.upload([a, b])
        before = dict(ServicePurchase.objects.values_list("activation_date", "natural_key"))
        result = self.upload([b, a])
        self.assertEqual(result["service_purchase_pending_rows"], 0)
        self.assertEqual(dict(ServicePurchase.objects.values_list("activation_date", "natural_key")), before)
        self.assertEqual(ServicePurchase.objects.count(), 2)

    def test_clear_correction_keeps_identifier_and_version(self):
        self.upload([self.row()])
        purchase = ServicePurchase.objects.get()
        key = purchase.natural_key
        self.upload([self.row(expiration="2026-07-05")])
        purchase.refresh_from_db()
        self.assertEqual(purchase.expiration_date, date(2026, 7, 5))
        self.assertEqual(purchase.natural_key, key)
        self.assertEqual(purchase.versions.count(), 2)

    def test_conflict_does_not_abort_clear_rows(self):
        self.upload([self.row()])
        # Represents a historical record whose stored identity no longer matches its fields.
        ServicePurchase.objects.update(total_amount=90)
        result = self.upload([self.row(), self.row(client="456")])
        self.assertEqual(result["service_purchase_pending_rows"], 1)
        self.assertEqual(result["service_purchases_created"], 1)
        self.assertEqual(ServicePurchase.objects.count(), 2)
        review = ServicePurchaseMatchReview.objects.get()
        self.assertEqual(review.reason, "identifier_conflict")
        self.assertEqual(review.latest_raw_row.raw_payload["ID del Cliente"], "123")
        self.assertEqual(ReportImport.objects.get(pk=result["report_import_id"]).status, "needs_review")

    def test_ambiguous_rows_persist_once_across_reordered_uploads(self):
        result = self.ambiguous()
        self.assertEqual(result["service_purchase_pending_rows"], 2)
        result = self.upload([self.row("2026-07-02", "2026-08-01"), self.row("2026-06-02", "2026-07-01")])
        self.assertEqual(result["service_purchase_pending_rows"], 2)
        self.assertEqual(ServicePurchase.objects.count(), 2)
        self.assertEqual(ServicePurchaseMatchReview.objects.count(), 2)
        self.assertTrue(all(review.source_rows.count() == 2 for review in ServicePurchaseMatchReview.objects.all()))

    def test_manual_update_audited_and_remembered(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.order_by("id").first()
        purchase = ServicePurchase.objects.order_by("id").first()
        key = purchase.natural_key
        response = self.resolve(review, "update", purchase)
        self.assertEqual(response.status_code, 200, response.data)
        purchase.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(purchase.natural_key, key)
        self.assertEqual(purchase.activation_date, date(2026, 6, 2))
        self.assertEqual(review.resolved_by, self.user)
        self.assertEqual(review.status, "update")
        self.assertEqual(review.note, "Checked report")
        result = self.upload([self.row("2026-06-02", "2026-07-01"), self.row("2026-07-02", "2026-08-01")])
        self.assertEqual(result["service_purchase_pending_rows"], 1)
        self.assertEqual(ServicePurchase.objects.count(), 2)

    def test_manual_create_uses_separate_identity_and_reimport_reuses_it(self):
        self.upload([self.row()])
        ServicePurchase.objects.update(total_amount=90)
        self.upload([self.row()])
        review = ServicePurchaseMatchReview.objects.get()
        response = self.resolve(review, "create")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ServicePurchase.objects.count(), 2)
        self.assertEqual(len(set(ServicePurchase.objects.values_list("natural_key", flat=True))), 2)
        self.assertEqual(self.upload([self.row()])["service_purchase_pending_rows"], 0)
        self.assertEqual(ServicePurchase.objects.count(), 2)

    def test_ignore_remembered_and_all_report_statuses_completed(self):
        self.upload([self.row()])
        ServicePurchase.objects.update(total_amount=90)
        self.upload([self.row()])
        self.upload([self.row()])
        review = ServicePurchaseMatchReview.objects.get()
        response = self.resolve(review, "ignore")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReportImport.objects.filter(status="needs_review").exists())
        result = self.upload([self.row()])
        self.assertEqual(result["service_purchase_ignored_rows"], 1)
        self.assertEqual(result["service_purchase_pending_rows"], 0)
        self.assertEqual(ServicePurchase.objects.count(), 1)

    def test_stale_review_and_double_resolution_rejected(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.first()
        self.assertEqual(self.resolve(review, "ignore", raw_row_id=0).status_code, 400)
        self.assertEqual(self.resolve(review, "ignore").status_code, 200)
        self.assertEqual(self.resolve(review, "ignore").status_code, 400)

    def test_wrong_client_or_changed_purchase_cannot_be_selected(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.first()
        self.upload([self.row(client="456")])
        other = ServicePurchase.objects.get(client__mindbody_id="456")
        self.assertEqual(self.resolve(review, "update", other).status_code, 400)
        purchase = ServicePurchase.objects.filter(client__mindbody_id="123").first()
        self.assertEqual(self.resolve(review, "update", purchase, purchase_updated_at="2000-01-01T00:00:00Z").status_code, 400)

    def test_newer_purchase_cannot_be_overwritten(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.order_by("id").first()
        self.upload([self.row()])
        purchase = ServicePurchase.objects.get(activation_date=date(2026, 6, 1))
        response = self.resolve(review, "update", purchase)
        self.assertEqual(response.status_code, 400)
        self.assertIn("newer", str(response.data))

    def test_same_purchase_cannot_receive_two_rows_from_one_report(self):
        self.ambiguous()
        a, b = list(ServicePurchaseMatchReview.objects.order_by("id"))
        purchase = ServicePurchase.objects.order_by("id").first()
        self.assertEqual(self.resolve(a, "update", purchase).status_code, 200)
        purchase.refresh_from_db()
        response = self.resolve(b, "update", purchase)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already represents", str(response.data))

    def test_metric_failure_rolls_back_decision_and_purchase(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.first()
        count = ServicePurchase.objects.count()
        with patch("core_data.purchase_matching.rebuild_resolved_purchase_metrics", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.resolve(review, "create")
        review.refresh_from_db()
        self.assertEqual(review.status, "pending")
        self.assertEqual(ServicePurchase.objects.count(), count)

    def test_access_scope_capability_and_money_masking(self):
        self.ambiguous()
        review = ServicePurchaseMatchReview.objects.first()
        user = CustomUser.objects.create_user(email="operator@example.com", password="test")
        profile = UserAccessProfile.objects.create(user=user, can_upload_data=True)
        self.api.force_authenticate(user)
        self.assertEqual(self.api.get(self.url).data["count"], 0)
        self.assertEqual(self.resolve(review, "ignore").status_code, 404)
        profile.allowed_studios.add(self.studio)
        response = self.api.get(self.url)
        self.assertEqual(response.data["count"], 2)
        self.assertIsNone(response.data["results"][0]["incoming"]["total_amount"])
        response = self.api.get(f"{self.url}{review.pk}/candidates/")
        self.assertEqual(response.data["count"], 2)
        self.assertIsNone(response.data["results"][0]["total_amount"])
        profile.can_upload_data = False
        profile.save()
        self.assertEqual(self.api.get(self.url).status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)

    def test_reopened_review_keeps_prior_decision_audit(self):
        self.upload([self.row()])
        ServicePurchase.objects.update(total_amount=90)
        self.upload([self.row()])
        review = ServicePurchaseMatchReview.objects.get()
        self.assertEqual(self.resolve(review, "create").status_code, 200)
        review.refresh_from_db()
        review.purchase.delete()
        self.assertEqual(self.upload([self.row()])["service_purchase_pending_rows"], 1)
        review.refresh_from_db()
        self.assertEqual(self.resolve(review, "ignore").status_code, 200)
        review.refresh_from_db()
        self.assertEqual([entry["decision"] for entry in review.decision_history], ["create", "ignore"])

    def test_update_rebuilds_old_and_new_membership_coverage(self):
        from analytics.models import ClientStudioMonthlyMetric, MembershipMonthStatus
        from analytics.views import rebuild_membership_month
        self.upload([self.row(expiration="2026-08-31")])
        purchase = ServicePurchase.objects.get()
        purchase.pricing_option.track_retention = True
        purchase.pricing_option.save()
        rebuild_membership_month(self.site.pk, date(2026, 8, 1))
        self.assertTrue(MembershipMonthStatus.objects.get(site=self.site, month=date(2026, 8, 1)).current_month_member)
        # A historical identity conflict queues a shortened membership for review.
        ServicePurchase.objects.filter(pk=purchase.pk).update(total_amount=90)
        self.upload([self.row(expiration="2026-06-30")])
        review = ServicePurchaseMatchReview.objects.get()
        purchase.refresh_from_db()
        response = self.resolve(review, "update", purchase)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(MembershipMonthStatus.objects.filter(site=self.site, month=date(2026, 8, 1), current_month_member=True).exists())
        self.assertFalse(ClientStudioMonthlyMetric.objects.filter(site=self.site, month=date(2026, 8, 1), active_membership_days__gt=0).exists())
        self.assertTrue(MembershipMonthStatus.objects.get(site=self.site, month=date(2026, 6, 1)).current_month_member)

    def test_http_import_returns_partial_success(self):
        self.upload([self.row()])
        ServicePurchase.objects.update(total_amount=90)
        response = self.api.post("/api/data/report-imports/import-file/", {
            "site": self.site.pk, "studio": self.studio.pk, "report_type": "sales_by_service",
            "file": xlsx_upload("sunday.xlsx", SALES_BY_SERVICE_REQUIRED_HEADERS, [self.row(), self.row(client="456")]),
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["import"]["status"], "needs_review")
        self.assertEqual(response.data["import"]["service_purchase_pending_rows"], 1)
        self.assertEqual(response.data["import"]["service_purchases_created"], 1)
        self.assertFalse(response.data["client_metrics_automation"].get("error"))
