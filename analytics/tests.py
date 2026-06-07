from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from analytics.models import MembershipMonthStatus
from analytics.views import (
    rebuild_membership_month,
    rebuild_membership_months_after_import,
    serialize_membership_status_rows,
)
from core_data.models import (
    Client,
    CustomUser,
    AttendanceVisit,
    PricingOption,
    ReportImport,
    ServiceCategory,
    ServicePurchase,
    Site,
    Studio,
)


class ReactivatedMembershipHistoryTests(TestCase):
    def test_previous_purchase_excludes_reactivation_purchase(self):
        site = Site.objects.create(name="Santo Domingo", country_code=Site.COUNTRY_DOMINICAN_REPUBLIC)
        client = Client.objects.create(site=site, name="Test Client", mindbody_id="client-1")
        category = ServiceCategory.objects.create(site=site, name="Memberships")
        option = PricingOption.objects.create(
            site=site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )
        previous_purchase = ServicePurchase.objects.create(
            site=site,
            natural_key="previous-purchase",
            current_row_hash="previous-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 1, 5),
            activation_date=date(2026, 1, 5),
            expiration_date=date(2026, 2, 4),
            total_amount=Decimal("100.00"),
        )
        reactivation_purchase = ServicePurchase.objects.create(
            site=site,
            natural_key="reactivation-purchase",
            current_row_hash="reactivation-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 5, 10),
            activation_date=date(2026, 5, 10),
            expiration_date=date(2026, 6, 9),
            total_amount=Decimal("120.00"),
        )
        status = MembershipMonthStatus.objects.create(
            site=site,
            month=date(2026, 5, 1),
            client=client,
            status=MembershipMonthStatus.STATUS_REACTIVATED,
            current_month_member=True,
            membership_days=22,
            membership_value=reactivation_purchase.total_amount,
            source_purchase=reactivation_purchase,
        )

        row = serialize_membership_status_rows(
            MembershipMonthStatus.objects.filter(id=status.id)
        )[0]

        self.assertEqual(row["sale_date"], reactivation_purchase.sale_date.isoformat())
        self.assertEqual(
            row["previous_membership_purchase_date"],
            previous_purchase.sale_date.isoformat(),
        )
        self.assertEqual(
            row["last_membership_purchase_date"],
            reactivation_purchase.sale_date.isoformat(),
        )

    def test_advance_sale_without_prior_coverage_is_new_not_reactivated(self):
        site = Site.objects.create(name="Santo Domingo", country_code=Site.COUNTRY_DOMINICAN_REPUBLIC)
        client = Client.objects.create(site=site, name="Fenix Vidal", mindbody_id="100003793")
        category = ServiceCategory.objects.create(site=site, name="Memberships")
        option = PricingOption.objects.create(
            site=site,
            name="1 vez por semana",
            service_category=category,
            track_retention=True,
        )
        ServicePurchase.objects.create(
            site=site,
            natural_key="advance-sale",
            current_row_hash="advance-sale-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 2, 12),
            activation_date=date(2026, 5, 1),
            expiration_date=date(2026, 5, 30),
            total_amount=Decimal("3600.00"),
        )

        rebuild_membership_month(site.id, date(2026, 5, 1))

        status = MembershipMonthStatus.objects.get(
            site=site,
            client=client,
            month=date(2026, 5, 1),
        )
        self.assertEqual(status.status, MembershipMonthStatus.STATUS_NEW)

    def test_prior_covered_membership_is_reactivated(self):
        site = Site.objects.create(name="Madrid", country_code=Site.COUNTRY_SPAIN)
        client = Client.objects.create(site=site, name="Returning Client", mindbody_id="returning-1")
        category = ServiceCategory.objects.create(site=site, name="Memberships")
        option = PricingOption.objects.create(
            site=site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )
        ServicePurchase.objects.create(
            site=site,
            natural_key="march-membership",
            current_row_hash="march-membership-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 3, 1),
            activation_date=date(2026, 3, 1),
            expiration_date=date(2026, 3, 31),
            total_amount=Decimal("100.00"),
        )
        ServicePurchase.objects.create(
            site=site,
            natural_key="may-membership",
            current_row_hash="may-membership-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 5, 1),
            activation_date=date(2026, 5, 1),
            expiration_date=date(2026, 5, 31),
            total_amount=Decimal("120.00"),
        )

        rebuild_membership_month(site.id, date(2026, 5, 1))

        status = MembershipMonthStatus.objects.get(
            site=site,
            client=client,
            month=date(2026, 5, 1),
        )
        self.assertEqual(status.status, MembershipMonthStatus.STATUS_REACTIVATED)

    def test_membership_snapshot_uses_purchase_studio_not_attendance(self):
        site = Site.objects.create(name="Studio Site", country_code=Site.COUNTRY_SPAIN)
        purchase_studio = Studio.objects.create(site=site, name="Purchase Studio")
        client = Client.objects.create(site=site, name="Studio Client", mindbody_id="studio-client")
        category = ServiceCategory.objects.create(site=site, name="Memberships")
        option = PricingOption.objects.create(
            site=site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )
        purchase = ServicePurchase.objects.create(
            site=site,
            studio=purchase_studio,
            natural_key="studio-membership",
            current_row_hash="studio-membership-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 5, 1),
            activation_date=date(2026, 5, 1),
            expiration_date=date(2026, 5, 31),
            total_amount=Decimal("100.00"),
        )

        rebuild_membership_month(site.id, date(2026, 5, 1))

        status = MembershipMonthStatus.objects.get(
            site=site,
            client=client,
            month=date(2026, 5, 1),
        )
        self.assertEqual(status.source_purchase, purchase)
        self.assertEqual(status.studio, purchase_studio)
        self.assertEqual(
            status.studio_inference_method,
            MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )

    def test_sales_by_service_import_rebuilds_coverage_and_following_month(self):
        site = Site.objects.create(name="Barcelona", country_code=Site.COUNTRY_SPAIN)
        client = Client.objects.create(site=site, name="Imported Client", mindbody_id="imported-1")
        category = ServiceCategory.objects.create(site=site, name="Memberships")
        option = PricingOption.objects.create(
            site=site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )
        report_import = ReportImport.objects.create(
            report_type="sales_by_service",
            file_name="memberships.xlsx",
            status=ReportImport.STATUS_COMPLETED,
        )
        purchase = ServicePurchase.objects.create(
            site=site,
            natural_key="imported-membership",
            current_row_hash="imported-membership-hash",
            client=client,
            pricing_option=option,
            sale_date=date(2026, 4, 20),
            activation_date=date(2026, 5, 1),
            expiration_date=date(2026, 5, 31),
            total_amount=Decimal("100.00"),
            first_seen_import=report_import,
            last_seen_import=report_import,
        )

        result = rebuild_membership_months_after_import(site.id, report_import.id)

        self.assertFalse(result["skipped"])
        self.assertEqual(
            [row["month"] for row in result["rebuilt"]],
            ["2026-05-01", "2026-06-01"],
        )
        may_status = MembershipMonthStatus.objects.get(
            site=site,
            client=client,
            month=date(2026, 5, 1),
        )
        june_status = MembershipMonthStatus.objects.get(
            site=site,
            client=client,
            month=date(2026, 6, 1),
        )
        self.assertEqual(may_status.status, MembershipMonthStatus.STATUS_NEW)
        self.assertEqual(june_status.status, MembershipMonthStatus.STATUS_NOT_RENEWED)
        self.assertEqual(may_status.source_purchase, purchase)


class RetentionFollowupActivityTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = CustomUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
        )
        self.api.force_authenticate(self.user)
        self.site = Site.objects.create(
            name="Activity Site",
            country_code=Site.COUNTRY_DOMINICAN_REPUBLIC,
        )
        self.studio = Studio.objects.create(site=self.site, name="Piantini")
        self.client = Client.objects.create(
            site=self.site,
            name="Follow-up Client",
            mindbody_id="followup-1",
        )
        category = ServiceCategory.objects.create(site=self.site, name="Memberships")
        self.membership = PricingOption.objects.create(
            site=self.site,
            name="Monthly",
            service_category=category,
            track_retention=True,
        )
        self.drop_in = PricingOption.objects.create(
            site=self.site,
            name="Drop In",
            service_category=category,
        )
        purchase = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="expired-membership",
            current_row_hash="expired-membership-hash",
            client=self.client,
            pricing_option=self.membership,
            sale_date=date(2026, 3, 1),
            activation_date=date(2026, 3, 1),
            expiration_date=date(2026, 3, 31),
            total_amount=Decimal("100.00"),
        )
        self.snapshot = MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio,
            month=date(2026, 4, 1),
            client=self.client,
            status=MembershipMonthStatus.STATUS_NOT_RENEWED,
            previous_month_member=True,
            previous_membership_days=31,
            membership_value=purchase.total_amount,
            source_purchase=purchase,
            studio_inference_method=MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )

    def create_visit(self, natural_key, visit_date, revenue):
        return AttendanceVisit.objects.create(
            site=self.site,
            natural_key=natural_key,
            current_row_hash=f"{natural_key}-hash",
            client=self.client,
            visit_studio=self.studio,
            pricing_option=self.drop_in,
            visit_date=visit_date,
            visit_time_raw="10:00 AM",
            revenue=Decimal(revenue),
        )

    def test_activity_endpoint_separates_followup_and_later_visits(self):
        self.create_visit("followup-unpaid", date(2026, 4, 10), "0.00")
        self.create_visit("followup-paid", date(2026, 4, 20), "25.00")
        self.create_visit("later-paid", date(2026, 5, 5), "30.00")

        response = self.api.get(
            reverse(
                "analytics-retention-followup-activity",
                kwargs={"snapshot_id": self.snapshot.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["activity_status"], "attending_paid")
        self.assertEqual(
            response.data["last_tracked_purchase"],
            {
                "service": "Monthly",
                "studio": "Piantini",
                "sale_date": "2026-03-01",
                "activation_date": "2026-03-01",
                "expiration_date": "2026-03-31",
            },
        )
        self.assertEqual(
            [visit["date"] for visit in response.data["followup_period"]["visits"]],
            ["2026-04-10", "2026-04-20"],
        )
        self.assertEqual(
            [visit["date"] for visit in response.data["later_period"]["visits"]],
            ["2026-05-05"],
        )
        self.assertEqual(
            response.data["followup_period"]["visits"][0]["payment_status"],
            "unpaid",
        )

    def test_activity_endpoint_returns_empty_periods_for_inactive_client(self):
        response = self.api.get(
            reverse(
                "analytics-retention-followup-activity",
                kwargs={"snapshot_id": self.snapshot.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["activity_status"], "inactive")
        self.assertEqual(response.data["followup_period"]["visits"], [])
        self.assertEqual(response.data["later_period"]["visits"], [])

    def test_purchase_history_returns_all_purchases_newest_first(self):
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="newer-membership",
            current_row_hash="newer-membership-hash",
            client=self.client,
            pricing_option=self.membership,
            sale_date=date(2026, 5, 1),
            activation_date=date(2026, 5, 1),
            expiration_date=date(2026, 5, 31),
            total_amount=Decimal("120.00"),
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="non-tracked-purchase",
            current_row_hash="non-tracked-purchase-hash",
            client=self.client,
            pricing_option=self.drop_in,
            sale_date=date(2026, 6, 1),
            activation_date=date(2026, 6, 1),
            expiration_date=date(2026, 6, 1),
            total_amount=Decimal("25.00"),
        )

        response = self.api.get(
            reverse(
                "analytics-retention-purchase-history",
                kwargs={"snapshot_id": self.snapshot.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(
            [purchase["sale_date"] for purchase in response.data["purchases"]],
            ["2026-06-01", "2026-05-01", "2026-03-01"],
        )
        self.assertEqual(response.data["purchases"][0]["service"], "Drop In")
        self.assertEqual(response.data["purchases"][1]["studio"], "Piantini")
        self.assertEqual(response.data["purchases"][1]["activation_date"], "2026-05-01")
        self.assertEqual(response.data["purchases"][1]["expiration_date"], "2026-05-31")

    def test_followup_list_filters_and_orders_not_renewed_activity(self):
        paid_client = Client.objects.create(
            site=self.site,
            name="Paid Client",
            mindbody_id="paid-1",
        )
        unpaid_client = Client.objects.create(
            site=self.site,
            name="Unpaid Client",
            mindbody_id="unpaid-1",
        )
        paid_purchase = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="paid-expired-membership",
            current_row_hash="paid-expired-membership-hash",
            client=paid_client,
            pricing_option=self.membership,
            sale_date=date(2026, 3, 2),
            activation_date=date(2026, 3, 1),
            expiration_date=date(2026, 3, 31),
            total_amount=Decimal("100.00"),
        )
        unpaid_purchase = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="unpaid-expired-membership",
            current_row_hash="unpaid-expired-membership-hash",
            client=unpaid_client,
            pricing_option=self.membership,
            sale_date=date(2026, 3, 3),
            activation_date=date(2026, 3, 1),
            expiration_date=date(2026, 3, 31),
            total_amount=Decimal("100.00"),
        )
        MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio,
            month=date(2026, 4, 1),
            client=paid_client,
            status=MembershipMonthStatus.STATUS_NOT_RENEWED,
            previous_month_member=True,
            previous_membership_days=31,
            membership_value=paid_purchase.total_amount,
            source_purchase=paid_purchase,
            studio_inference_method=MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )
        MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio,
            month=date(2026, 4, 1),
            client=unpaid_client,
            status=MembershipMonthStatus.STATUS_NOT_RENEWED,
            previous_month_member=True,
            previous_membership_days=31,
            membership_value=unpaid_purchase.total_amount,
            source_purchase=unpaid_purchase,
            studio_inference_method=MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )
        AttendanceVisit.objects.create(
            site=self.site,
            natural_key="paid-followup-visit",
            current_row_hash="paid-followup-visit-hash",
            client=paid_client,
            visit_studio=self.studio,
            pricing_option=self.drop_in,
            visit_date=date(2026, 4, 8),
            visit_time_raw="10:00 AM",
            revenue=Decimal("25.00"),
        )
        AttendanceVisit.objects.create(
            site=self.site,
            natural_key="unpaid-followup-visit",
            current_row_hash="unpaid-followup-visit-hash",
            client=unpaid_client,
            visit_studio=self.studio,
            pricing_option=self.drop_in,
            visit_date=date(2026, 4, 9),
            visit_time_raw="10:00 AM",
            revenue=Decimal("0.00"),
        )

        response = self.api.get(
            reverse("analytics-retention-followup"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "status": "not_renewed",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["activity_counts"],
            {
                "all": 3,
                "attending_unpaid": 1,
                "attending_paid": 1,
                "inactive": 1,
            },
        )
        self.assertEqual(
            [row["not_renewed_activity_status"] for row in response.data["rows"]],
            ["attending_unpaid", "attending_paid", "inactive"],
        )

        filtered_response = self.api.get(
            reverse("analytics-retention-followup"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "status": "not_renewed",
                "activity": "attending_paid",
            },
        )

        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(filtered_response.data["count"], 1)
        self.assertEqual(filtered_response.data["rows"][0]["client"], "Paid Client")

        retention_response = self.api.get(
            reverse("analytics-retention"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
            },
        )
        self.assertEqual(
            [row["client"] for row in retention_response.data["not_renewed_clients"]],
            ["Unpaid Client", "Paid Client", "Follow-up Client"],
        )

        tables_response = self.api.get(
            reverse("analytics-dashboard-monthly-retention-tables"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
            },
        )
        self.assertEqual(
            [
                row["client"]
                for row in tables_response.data["tables"]["not_renewed"]["rows"]
            ],
            ["Unpaid Client", "Paid Client", "Follow-up Client"],
        )

    def test_new_non_members_use_first_non_trial_purchase(self):
        trial_option = PricingOption.objects.create(
            site=self.site,
            name="Trial",
            service_category=self.drop_in.service_category,
            is_trial_class=True,
        )
        non_member = Client.objects.create(
            site=self.site,
            name="New Non-member",
            mindbody_id="new-non-member",
        )
        trial_then_non_member = Client.objects.create(
            site=self.site,
            name="Trial Then Non-member",
            mindbody_id="trial-then-non-member",
        )
        new_member = Client.objects.create(
            site=self.site,
            name="New Member",
            mindbody_id="new-member",
        )
        existing_client = Client.objects.create(
            site=self.site,
            name="Existing Client",
            mindbody_id="existing-client",
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="new-non-member-first",
            current_row_hash="new-non-member-first-hash",
            client=non_member,
            pricing_option=self.drop_in,
            sale_date=date(2026, 4, 5),
            total_amount=Decimal("25.00"),
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="trial-first",
            current_row_hash="trial-first-hash",
            client=trial_then_non_member,
            pricing_option=trial_option,
            sale_date=date(2026, 4, 2),
            total_amount=Decimal("0.00"),
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="trial-then-drop-in",
            current_row_hash="trial-then-drop-in-hash",
            client=trial_then_non_member,
            pricing_option=self.drop_in,
            sale_date=date(2026, 4, 8),
            total_amount=Decimal("25.00"),
        )
        member_purchase = ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="new-member-first",
            current_row_hash="new-member-first-hash",
            client=new_member,
            pricing_option=self.membership,
            sale_date=date(2026, 4, 6),
            activation_date=date(2026, 4, 1),
            expiration_date=date(2026, 4, 30),
            total_amount=Decimal("100.00"),
        )
        MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio,
            month=date(2026, 4, 1),
            client=new_member,
            status=MembershipMonthStatus.STATUS_NEW,
            current_month_member=True,
            membership_days=30,
            membership_value=member_purchase.total_amount,
            source_purchase=member_purchase,
            studio_inference_method=MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="existing-client-march",
            current_row_hash="existing-client-march-hash",
            client=existing_client,
            pricing_option=self.drop_in,
            sale_date=date(2026, 3, 15),
            total_amount=Decimal("25.00"),
        )
        ServicePurchase.objects.create(
            site=self.site,
            studio=self.studio,
            natural_key="existing-client-april",
            current_row_hash="existing-client-april-hash",
            client=existing_client,
            pricing_option=self.drop_in,
            sale_date=date(2026, 4, 15),
            total_amount=Decimal("25.00"),
        )

        response = self.api.get(
            reverse("analytics-retention-followup"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "status": "new_non_members",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            [row["client"] for row in response.data["rows"]],
            ["New Non-member", "Trial Then Non-member"],
        )
        self.assertEqual(response.data["rows"][1]["sale_date"], "2026-04-08")

        retention_response = self.api.get(
            reverse("analytics-retention"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
            },
        )
        self.assertEqual(retention_response.status_code, 200)
        self.assertEqual(retention_response.data["new_non_members"], 2)
        self.assertEqual(len(retention_response.data["new_non_member_samples"]), 2)

        tables_response = self.api.get(
            reverse("analytics-dashboard-monthly-retention-tables"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
            },
        )
        self.assertEqual(tables_response.status_code, 200)
        self.assertEqual(tables_response.data["tables"]["new_non_members"]["count"], 2)

        history_response = self.api.get(
            reverse(
                "analytics-retention-client-purchase-history",
                kwargs={"client_id": trial_then_non_member.id},
            )
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.data["count"], 2)
