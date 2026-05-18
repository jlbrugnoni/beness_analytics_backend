from datetime import time

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_data.models import (
    Client,
    CustomUser,
    PaymentMethod,
    PricingOption,
    ReportImport,
    Room,
    ServiceCategory,
    Site,
    StaffMember,
    Studio,
    StudioClosure,
    WeeklyRoomTemplate,
)


class AnalyticsImportGuardTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.site = Site.objects.create(name="Santo Domingo", country_code=Site.COUNTRY_DOMINICAN_REPUBLIC)
        self.other_site = Site.objects.create(name="Madrid", country_code=Site.COUNTRY_SPAIN)
        self.studio = Studio.objects.create(site=self.site, name="Pi Tao")
        self.other_studio = Studio.objects.create(site=self.other_site, name="Other Studio")

    def upload(self):
        return SimpleUploadedFile(
            "sales-by-service.xlsx",
            b"not a real workbook",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_sales_by_service_preview_requires_studio_before_parsing(self):
        response = self.client.post(
            "/api/data/report-imports/preview/",
            {"site": self.site.id, "report_type": "sales_by_service", "file": self.upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Studio is required for Sales by Service reports.")

    def test_sales_by_service_import_requires_studio_before_parsing(self):
        response = self.client.post(
            "/api/data/report-imports/import-file/",
            {"site": self.site.id, "report_type": "sales_by_service", "file": self.upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Studio is required for Sales by Service reports.")

    def test_sales_by_service_rejects_studio_from_another_site(self):
        response = self.client.post(
            "/api/data/report-imports/preview/",
            {
                "site": self.site.id,
                "studio": self.other_studio.id,
                "report_type": "sales_by_service",
                "file": self.upload(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Studio not found for selected site.")

    @override_settings(ENABLE_ANALYTICS_RESET=True)
    def test_reset_preserves_schedule_setup(self):
        room = Room.objects.create(site=self.site, studio=self.studio, name="Room 1", group_capacity=12)
        staff = StaffMember.objects.create(site=self.site, name="Coach One")
        WeeklyRoomTemplate.objects.create(
            site=self.site,
            studio=self.studio,
            room=room,
            staff_member=staff,
            name="Pilates",
            weekday=0,
            start_time=time(8, 0),
            end_time=time(8, 50),
            capacity=12,
            active_from=timezone.localdate(),
        )
        StudioClosure.objects.create(
            site=self.site,
            studio=self.studio,
            room=room,
            closure_date=timezone.localdate(),
            reason="Holiday",
        )
        Client.objects.create(site=self.site, name="Client One")
        category = ServiceCategory.objects.create(site=self.site, name="Memberships")
        PricingOption.objects.create(site=self.site, name="Monthly", service_category=category, track_retention=True)
        PaymentMethod.objects.create(site=self.site, name="Card")
        ReportImport.objects.create(report_type="sales_by_service", source_system="mindbody", file_name="old.xlsx")

        response = self.client.post(
            "/api/data/report-imports/reset-analytics-data/",
            {"confirmation": "RESET ANALYTICS DATA"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Studio.objects.count(), 2)
        self.assertEqual(Room.objects.count(), 1)
        self.assertEqual(StaffMember.objects.count(), 1)
        self.assertEqual(WeeklyRoomTemplate.objects.count(), 1)
        self.assertEqual(StudioClosure.objects.count(), 1)
        self.assertEqual(Client.objects.count(), 0)
        self.assertEqual(PricingOption.objects.count(), 0)
        self.assertEqual(PaymentMethod.objects.count(), 0)
        self.assertEqual(ReportImport.objects.count(), 0)
        self.assertIn("weekly_room_templates", response.data["preserved"])
