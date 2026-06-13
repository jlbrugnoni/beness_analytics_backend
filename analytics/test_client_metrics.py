from datetime import date
from decimal import Decimal

from django.test import TestCase

from analytics.client_metrics import (
    aggregate_client_monthly_metrics,
    rebuild_client_studio_monthly_metrics,
)
from analytics.models import ClientStudioMonthlyMetric, MembershipMonthStatus
from core_data.models import (
    AttendanceVisit,
    Client,
    PricingOption,
    SaleLine,
    ServiceCategory,
    ServicePurchase,
    Site,
    Studio,
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
