from datetime import date
from decimal import Decimal

from django.test import TestCase

from analytics.models import MembershipMonthStatus
from analytics.views import rebuild_membership_month, serialize_membership_status_rows
from core_data.models import Client, PricingOption, ServiceCategory, ServicePurchase, Site


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
