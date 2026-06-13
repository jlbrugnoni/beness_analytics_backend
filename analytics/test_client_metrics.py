from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from analytics.client_metrics import (
    aggregate_client_monthly_metrics,
    aggregate_client_weekly_metrics,
    rebuild_client_metrics_after_import,
    rebuild_client_studio_monthly_metrics,
    rebuild_client_studio_weekly_metrics,
)
from analytics.models import (
    ClientStudioMonthlyMetric,
    ClientStudioWeeklyMetric,
    MembershipMonthStatus,
)
from analytics.views import rebuild_membership_month
from core_data.models import (
    AttendanceVisit,
    AttendanceRawRow,
    Client,
    CustomUser,
    PricingOption,
    ReportImport,
    SaleLine,
    ServiceCategory,
    ServicePurchase,
    Site,
    Studio,
    UserAccessProfile,
)


class ClientStudioMonthlyMetricTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(
            name="Santo Domingo",
            country_code=Site.COUNTRY_DOMINICAN_REPUBLIC,
        )
        self.studio_a = Studio.objects.create(site=self.site, name="Piantini")
        self.studio_b = Studio.objects.create(site=self.site, name="Naco")
        self.client = Client.objects.create(
            site=self.site,
            name="Monthly Metric Client",
            mindbody_id="metric-client",
        )
        category = ServiceCategory.objects.create(site=self.site, name="Services")
        self.membership = PricingOption.objects.create(
            site=self.site,
            name="Membership",
            service_category=category,
            track_retention=True,
        )
        self.drop_in = PricingOption.objects.create(
            site=self.site,
            name="Drop In",
            service_category=category,
        )
        self.trial = PricingOption.objects.create(
            site=self.site,
            name="Trial",
            service_category=category,
            is_trial_class=True,
        )

    def create_visit(
        self,
        key,
        studio,
        visit_date,
        *,
        revenue="0.00",
        no_show=False,
        late_cancel=False,
    ):
        return AttendanceVisit.objects.create(
            site=self.site,
            natural_key=key,
            current_row_hash=f"{key}-hash",
            client=self.client,
            visit_studio=studio,
            visit_date=visit_date,
            visit_time_raw="10:00 AM",
            revenue=Decimal(revenue),
            no_show=no_show,
            late_cancel=late_cancel,
        )

    def create_purchase(
        self,
        key,
        studio,
        option,
        sale_date,
        amount,
        *,
        activation_date=None,
        expiration_date=None,
    ):
        return ServicePurchase.objects.create(
            site=self.site,
            studio=studio,
            natural_key=key,
            current_row_hash=f"{key}-hash",
            client=self.client,
            pricing_option=option,
            sale_date=sale_date,
            activation_date=activation_date,
            expiration_date=expiration_date,
            total_amount=Decimal(amount),
        )

    def create_sale(self, key, studio, sale_date, amount):
        return SaleLine.objects.create(
            site=self.site,
            studio=studio,
            natural_key=key,
            current_row_hash=f"{key}-hash",
            client=self.client,
            sale_date=sale_date,
            sale_number=f"sale-{key}",
            item_name=f"Item {key}",
            paid_total=Decimal(amount),
        )

    def test_rebuild_separates_studios_and_financial_sources(self):
        self.create_visit("a-attended", self.studio_a, date(2026, 4, 1), revenue="10.00")
        self.create_visit(
            "a-no-show",
            self.studio_a,
            date(2026, 4, 8),
            no_show=True,
        )
        self.create_visit(
            "a-late-cancel",
            self.studio_a,
            date(2026, 4, 9),
            late_cancel=True,
        )
        self.create_visit("b-attended", self.studio_b, date(2026, 4, 2), revenue="15.00")

        first_membership = self.create_purchase(
            "membership-one",
            self.studio_a,
            self.membership,
            date(2026, 3, 25),
            "100.00",
            activation_date=date(2026, 3, 25),
            expiration_date=date(2026, 4, 20),
        )
        self.create_purchase(
            "membership-two",
            self.studio_a,
            self.membership,
            date(2026, 4, 15),
            "120.00",
            activation_date=date(2026, 4, 15),
            expiration_date=date(2026, 5, 15),
        )
        self.create_purchase(
            "drop-in",
            self.studio_a,
            self.drop_in,
            date(2026, 4, 3),
            "30.00",
        )
        self.create_purchase(
            "trial",
            self.studio_a,
            self.trial,
            date(2026, 4, 4),
            "5.00",
        )
        self.create_sale("general-a", self.studio_a, date(2026, 4, 5), "300.00")
        self.create_sale("general-b", self.studio_b, date(2026, 4, 6), "200.00")

        MembershipMonthStatus.objects.create(
            site=self.site,
            studio=self.studio_a,
            month=date(2026, 4, 1),
            client=self.client,
            status=MembershipMonthStatus.STATUS_NEW,
            current_month_member=True,
            membership_days=30,
            membership_value=Decimal("220.00"),
            source_purchase=first_membership,
            studio_inference_method=MembershipMonthStatus.STUDIO_METHOD_PURCHASE,
        )

        rebuilt = rebuild_client_studio_monthly_metrics(
            self.site.id,
            date(2026, 4, 18),
        )

        self.assertEqual(rebuilt, 2)
        studio_a = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
            month=date(2026, 4, 1),
        )
        studio_b = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio=self.studio_b,
            month=date(2026, 4, 1),
        )

        self.assertEqual(studio_a.total_bookings, 3)
        self.assertEqual(studio_a.attended_visits, 1)
        self.assertEqual(studio_a.no_shows, 1)
        self.assertEqual(studio_a.late_cancels, 1)
        self.assertEqual(studio_a.active_weeks, 1)
        self.assertEqual(studio_a.active_week_starts, ["2026-03-30"])
        self.assertEqual(studio_a.attendance_revenue, Decimal("10.00"))
        self.assertEqual(studio_a.service_purchase_count, 3)
        self.assertEqual(studio_a.service_spending, Decimal("155.00"))
        self.assertEqual(studio_a.membership_spending, Decimal("120.00"))
        self.assertEqual(studio_a.non_membership_spending, Decimal("30.00"))
        self.assertEqual(studio_a.general_sales_spending, Decimal("300.00"))
        self.assertEqual(studio_a.first_visit_date, date(2026, 4, 1))
        self.assertEqual(studio_a.last_visit_date, date(2026, 4, 9))
        self.assertEqual(studio_a.first_purchase_date, date(2026, 4, 3))
        self.assertEqual(studio_a.last_purchase_date, date(2026, 4, 15))
        self.assertEqual(studio_a.active_membership_days, 30)
        self.assertEqual(studio_a.membership_status, MembershipMonthStatus.STATUS_NEW)

        self.assertEqual(studio_b.total_bookings, 1)
        self.assertEqual(studio_b.attended_visits, 1)
        self.assertEqual(studio_b.active_week_starts, ["2026-03-30"])
        self.assertEqual(studio_b.general_sales_spending, Decimal("200.00"))

        site_totals = aggregate_client_monthly_metrics([studio_a, studio_b])
        self.assertEqual(site_totals["attended_visits"], 2)
        self.assertEqual(site_totals["active_weeks"], 1)
        self.assertEqual(site_totals["active_membership_days"], 30)
        self.assertEqual(site_totals["service_spending"], Decimal("155.00"))
        self.assertEqual(site_totals["general_sales_spending"], Decimal("500.00"))

    def test_rebuild_is_idempotent_and_replaces_corrected_values(self):
        visit = self.create_visit(
            "corrected-visit",
            self.studio_a,
            date(2026, 4, 10),
            revenue="20.00",
            no_show=True,
        )

        rebuild_client_studio_monthly_metrics(self.site.id, date(2026, 4, 1))
        first = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
        )
        self.assertEqual(first.attended_visits, 0)
        self.assertEqual(first.no_shows, 1)

        visit.no_show = False
        visit.revenue = Decimal("25.00")
        visit.save(update_fields=["no_show", "revenue", "updated_at"])
        rebuild_client_studio_monthly_metrics(self.site.id, date(2026, 4, 30))

        self.assertEqual(ClientStudioMonthlyMetric.objects.count(), 1)
        corrected = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
        )
        self.assertEqual(corrected.attended_visits, 1)
        self.assertEqual(corrected.no_shows, 0)
        self.assertEqual(corrected.attendance_revenue, Decimal("25.00"))

    def test_unassigned_purchases_share_one_monthly_row(self):
        self.create_purchase(
            "unassigned-service",
            None,
            self.drop_in,
            date(2026, 4, 7),
            "40.00",
        )
        self.create_sale("unassigned-sale", None, date(2026, 4, 8), "50.00")

        rebuild_client_studio_monthly_metrics(self.site.id, date(2026, 4, 1))

        row = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio__isnull=True,
        )
        self.assertEqual(row.service_spending, Decimal("40.00"))
        self.assertEqual(row.general_sales_spending, Decimal("50.00"))
        self.assertEqual(row.first_purchase_date, date(2026, 4, 7))
        self.assertEqual(row.last_purchase_date, date(2026, 4, 8))

    def test_weekly_rebuild_uses_monday_boundary_and_unions_studios(self):
        self.create_visit(
            "weekly-a-attended",
            self.studio_a,
            date(2025, 12, 30),
            revenue="10.00",
        )
        self.create_visit(
            "weekly-a-no-show",
            self.studio_a,
            date(2026, 1, 3),
            no_show=True,
        )
        self.create_visit(
            "weekly-b-attended",
            self.studio_b,
            date(2026, 1, 2),
            revenue="15.00",
        )
        self.create_visit(
            "weekly-b-late-cancel",
            self.studio_b,
            date(2026, 1, 4),
            late_cancel=True,
        )
        self.create_purchase(
            "weekly-membership-a",
            self.studio_a,
            self.membership,
            date(2025, 12, 28),
            "100.00",
            activation_date=date(2025, 12, 28),
            expiration_date=date(2026, 1, 2),
        )
        self.create_purchase(
            "weekly-membership-b",
            self.studio_b,
            self.membership,
            date(2026, 1, 1),
            "120.00",
            activation_date=date(2026, 1, 1),
            expiration_date=date(2026, 1, 5),
        )

        rebuilt = rebuild_client_studio_weekly_metrics(
            self.site.id,
            date(2026, 1, 1),
        )

        self.assertEqual(rebuilt, 2)
        studio_a = ClientStudioWeeklyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
            week_start=date(2025, 12, 29),
        )
        studio_b = ClientStudioWeeklyMetric.objects.get(
            client=self.client,
            studio=self.studio_b,
            week_start=date(2025, 12, 29),
        )

        self.assertEqual(studio_a.total_bookings, 2)
        self.assertEqual(studio_a.attended_visits, 1)
        self.assertEqual(studio_a.no_shows, 1)
        self.assertEqual(studio_a.late_cancels, 0)
        self.assertEqual(studio_a.attendance_revenue, Decimal("10.00"))
        self.assertEqual(studio_a.active_membership_days, 5)
        self.assertTrue(studio_a.had_active_membership)

        self.assertEqual(studio_b.total_bookings, 2)
        self.assertEqual(studio_b.attended_visits, 1)
        self.assertEqual(studio_b.no_shows, 0)
        self.assertEqual(studio_b.late_cancels, 1)
        self.assertEqual(studio_b.attendance_revenue, Decimal("15.00"))
        self.assertEqual(studio_b.active_membership_days, 4)

        site_totals = aggregate_client_weekly_metrics([studio_a, studio_b])
        self.assertEqual(site_totals["attended_visits"], 2)
        self.assertEqual(site_totals["active_weeks"], 1)
        self.assertEqual(site_totals["active_membership_days"], 7)
        self.assertTrue(site_totals["had_active_membership"])

        self.create_visit(
            "next-week-attended",
            self.studio_a,
            date(2026, 1, 6),
        )
        rebuild_client_studio_weekly_metrics(self.site.id, date(2026, 1, 6))
        range_totals = aggregate_client_weekly_metrics(
            ClientStudioWeeklyMetric.objects.filter(client=self.client)
        )
        self.assertEqual(range_totals["active_weeks"], 2)
        self.assertEqual(
            range_totals["active_week_starts"],
            ["2025-12-29", "2026-01-05"],
        )

    def test_weekly_rebuild_skips_empty_and_purchase_only_weeks(self):
        self.create_purchase(
            "weekly-drop-in-only",
            self.studio_a,
            self.drop_in,
            date(2026, 2, 3),
            "30.00",
        )

        rebuilt = rebuild_client_studio_weekly_metrics(
            self.site.id,
            date(2026, 2, 3),
        )

        self.assertEqual(rebuilt, 0)
        self.assertFalse(ClientStudioWeeklyMetric.objects.exists())

        empty_rebuild = rebuild_client_studio_weekly_metrics(
            self.site.id,
            date(2026, 2, 10),
        )
        self.assertEqual(empty_rebuild, 0)
        self.assertFalse(ClientStudioWeeklyMetric.objects.exists())

    def test_weekly_rebuild_keeps_membership_only_weeks(self):
        self.create_purchase(
            "weekly-membership-only",
            self.studio_a,
            self.membership,
            date(2026, 2, 1),
            "100.00",
            activation_date=date(2026, 2, 9),
            expiration_date=date(2026, 2, 12),
        )

        rebuilt = rebuild_client_studio_weekly_metrics(
            self.site.id,
            date(2026, 2, 10),
        )

        self.assertEqual(rebuilt, 1)
        row = ClientStudioWeeklyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
            week_start=date(2026, 2, 9),
        )
        self.assertEqual(row.total_bookings, 0)
        self.assertEqual(row.attended_visits, 0)
        self.assertEqual(row.active_membership_days, 4)
        self.assertEqual(
            row.active_membership_dates,
            ["2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12"],
        )
        self.assertTrue(row.had_active_membership)

    def test_weekly_rebuild_replaces_corrected_attendance(self):
        visit = self.create_visit(
            "weekly-corrected",
            self.studio_a,
            date(2026, 3, 4),
            revenue="0.00",
            no_show=True,
        )
        rebuild_client_studio_weekly_metrics(self.site.id, date(2026, 3, 4))

        first = ClientStudioWeeklyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
        )
        self.assertEqual(first.attended_visits, 0)
        self.assertEqual(first.no_shows, 1)

        visit.no_show = False
        visit.revenue = Decimal("35.00")
        visit.save(update_fields=["no_show", "revenue", "updated_at"])
        rebuild_client_studio_weekly_metrics(self.site.id, date(2026, 3, 8))

        self.assertEqual(ClientStudioWeeklyMetric.objects.count(), 1)
        corrected = ClientStudioWeeklyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
        )
        self.assertEqual(corrected.week_start, date(2026, 3, 2))
        self.assertEqual(corrected.attended_visits, 1)
        self.assertEqual(corrected.no_shows, 0)
        self.assertEqual(corrected.attendance_revenue, Decimal("35.00"))

    def test_import_periods_rebuild_only_relevant_metrics(self):
        attendance_import = ReportImport.objects.create(
            report_type="attendance_with_revenue",
            file_name="attendance.xlsx",
        )
        self.create_visit(
            "automated-attendance",
            self.studio_a,
            date(2026, 4, 14),
            revenue="20.00",
        )
        AttendanceVisit.objects.filter(natural_key="automated-attendance").update(
            last_seen_import=attendance_import,
        )

        attendance_result = rebuild_client_metrics_after_import(
            self.site.id,
            attendance_import.id,
        )

        self.assertEqual(
            [row["month"] for row in attendance_result["monthly"]],
            ["2026-04-01"],
        )
        self.assertEqual(
            [row["week_start"] for row in attendance_result["weekly"]],
            ["2026-04-13"],
        )

        sales_import = ReportImport.objects.create(
            report_type="sales",
            file_name="sales.xlsx",
        )
        sale = self.create_sale(
            "automated-sale",
            self.studio_a,
            date(2026, 5, 8),
            "75.00",
        )
        sale.last_seen_import = sales_import
        sale.save(update_fields=["last_seen_import", "updated_at"])

        sales_result = rebuild_client_metrics_after_import(
            self.site.id,
            sales_import.id,
        )

        self.assertEqual(
            [row["month"] for row in sales_result["monthly"]],
            ["2026-05-01"],
        )
        self.assertEqual(sales_result["weekly"], [])

    def test_service_import_rebuilds_old_and_new_membership_coverage(self):
        initial_import = ReportImport.objects.create(
            report_type="sales_by_service",
            file_name="initial.xlsx",
            studio=self.studio_a,
        )
        purchase = self.create_purchase(
            "coverage-change",
            self.studio_a,
            self.membership,
            date(2026, 4, 1),
            "100.00",
            activation_date=date(2026, 4, 1),
            expiration_date=date(2026, 5, 31),
        )
        purchase.first_seen_import = initial_import
        purchase.last_seen_import = initial_import
        purchase.save(
            update_fields=["first_seen_import", "last_seen_import", "updated_at"]
        )
        first_version = purchase.versions.create(
            report_import=initial_import,
            raw_row=self._service_raw_row(
                initial_import,
                1,
                "initial-row",
            ),
            row_hash="initial-version",
            snapshot={
                "pricing_option_id": self.membership.id,
                "sale_date": "2026-04-01",
                "activation_date": "2026-04-01",
                "expiration_date": "2026-05-31",
            },
        )
        self.assertIsNotNone(first_version.id)

        correction_import = ReportImport.objects.create(
            report_type="sales_by_service",
            file_name="correction.xlsx",
            studio=self.studio_a,
        )
        purchase.activation_date = date(2026, 5, 1)
        purchase.expiration_date = date(2026, 6, 30)
        purchase.last_seen_import = correction_import
        purchase.save(
            update_fields=[
                "activation_date",
                "expiration_date",
                "last_seen_import",
                "updated_at",
            ]
        )
        purchase.versions.create(
            report_import=correction_import,
            raw_row=self._service_raw_row(
                correction_import,
                1,
                "correction-row",
            ),
            row_hash="correction-version",
            snapshot={
                "pricing_option_id": self.membership.id,
                "sale_date": "2026-04-01",
                "activation_date": "2026-05-01",
                "expiration_date": "2026-06-30",
            },
        )

        result = rebuild_client_metrics_after_import(
            self.site.id,
            correction_import.id,
        )

        self.assertEqual(
            [row["month"] for row in result["monthly"]],
            ["2026-04-01", "2026-05-01", "2026-06-01"],
        )
        self.assertEqual(result["weekly"][0]["week_start"], "2026-03-30")
        self.assertEqual(result["weekly"][-1]["week_start"], "2026-06-29")

    def test_retention_rebuild_updates_monthly_metric_status(self):
        self.create_purchase(
            "retention-sync",
            self.studio_a,
            self.membership,
            date(2026, 4, 1),
            "100.00",
            activation_date=date(2026, 4, 1),
            expiration_date=date(2026, 4, 30),
        )

        rebuild_membership_month(self.site.id, date(2026, 4, 1))

        metric = ClientStudioMonthlyMetric.objects.get(
            client=self.client,
            studio=self.studio_a,
            month=date(2026, 4, 1),
        )
        self.assertEqual(metric.membership_status, MembershipMonthStatus.STATUS_NEW)
        self.assertEqual(metric.active_membership_days, 30)

    def _service_raw_row(self, report_import, row_number, row_hash):
        from core_data.models import ServicePurchaseRawRow

        return ServicePurchaseRawRow.objects.create(
            report_import=report_import,
            site=self.site,
            studio=self.studio_a,
            row_number=row_number,
            row_hash=row_hash,
            raw_payload={},
            normalized_payload={},
        )


class ClientMetricRebuildEndpointTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(
            name="Madrid",
            country_code=Site.COUNTRY_SPAIN,
        )
        self.studio = Studio.objects.create(site=self.site, name="Centro")
        self.client_record = Client.objects.create(
            site=self.site,
            name="Historical Client",
            mindbody_id="historical-client",
        )
        AttendanceVisit.objects.create(
            site=self.site,
            natural_key="historical-visit",
            current_row_hash="historical-visit-hash",
            client=self.client_record,
            visit_studio=self.studio,
            visit_date=date(2026, 1, 15),
            visit_time_raw="9:00 AM",
        )
        self.user = CustomUser.objects.create_user(
            email="metrics@example.com",
            password="testpass123",
        )
        self.profile, _ = UserAccessProfile.objects.get_or_create(user=self.user)
        self.profile.can_reset_data = True
        self.profile.save(update_fields=["can_reset_data"])
        self.profile.allowed_sites.add(self.site)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_manual_rebuild_is_permission_protected(self):
        self.profile.can_reset_data = False
        self.profile.save(update_fields=["can_reset_data"])

        response = self.api.post(
            reverse("analytics-client-metrics-rebuild"),
            {
                "site": self.site.id,
                "month": "2026-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ClientStudioMonthlyMetric.objects.exists())

    def test_manual_historical_rebuild_is_idempotent(self):
        payload = {
            "site": self.site.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        }
        first = self.api.post(
            reverse("analytics-client-metrics-rebuild"),
            payload,
            format="json",
        )
        second = self.api.post(
            reverse("analytics-client-metrics-rebuild"),
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(ClientStudioMonthlyMetric.objects.count(), 1)
        self.assertEqual(ClientStudioWeeklyMetric.objects.count(), 1)
        active_week = ClientStudioWeeklyMetric.objects.get(total_bookings=1)
        self.assertEqual(active_week.week_start, date(2026, 1, 12))

    @override_settings(ENABLE_ANALYTICS_RESET=True)
    def test_report_rollback_removes_derived_client_metrics(self):
        report_import = ReportImport.objects.create(
            report_type="attendance_with_revenue",
            file_name="rollback-attendance.xlsx",
            uploaded_by=self.user,
        )
        raw_row = AttendanceRawRow.objects.create(
            report_import=report_import,
            site=self.site,
            row_number=1,
            row_hash="rollback-row",
            raw_payload={},
            normalized_payload={},
        )
        visit = AttendanceVisit.objects.get(natural_key="historical-visit")
        visit.first_seen_import = report_import
        visit.last_seen_import = report_import
        visit.source_raw_row = raw_row
        visit.save(
            update_fields=[
                "first_seen_import",
                "last_seen_import",
                "source_raw_row",
                "updated_at",
            ]
        )
        rebuild_client_metrics_after_import(self.site.id, report_import.id)
        self.assertTrue(ClientStudioMonthlyMetric.objects.exists())
        self.assertTrue(ClientStudioWeeklyMetric.objects.exists())
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])

        response = self.api.post(
            f"/api/data/report-imports/{report_import.id}/rollback/",
            {"confirmation": "DELETE REPORT DATA"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceVisit.objects.exists())
        self.assertFalse(ClientStudioMonthlyMetric.objects.exists())
        self.assertFalse(ClientStudioWeeklyMetric.objects.exists())
        self.assertEqual(
            response.data["client_metrics_automation"]["total_monthly_rows"],
            0,
        )
