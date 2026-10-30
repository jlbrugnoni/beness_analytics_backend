from datetime import date, time

from django.test import TestCase
from rest_framework.test import APIClient
from core_data.models import (
    Site, Studio, CustomUser, ScheduledClass, StudioClosure,
    Client, AttendanceVisit, AttendanceClassMatch,
)


class CrossPeriodOccupancyTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="Occupancy test", country_code="DO")
        self.studio = Studio.objects.create(site=self.site, name="Studio")
        self.user = CustomUser.objects.create_superuser(email="occupancy@test.com", password="test")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.params = {"mode": "monthly", "date_from": "2026-02-01", "date_to": "2026-02-28", "site": self.site.pk}

    def create_class(self, day, hour=8, capacity=10, studio=None):
        return ScheduledClass.objects.create(site=self.site, studio=studio or self.studio, name="Class",
            class_date=day, start_time=time(hour), end_time=time(hour+1), capacity=capacity, status="scheduled")

    def get_data(self, **params):
        response = self.api.get("/api/data/analytics/dashboard/occupancy/", {**self.params, **params})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_full_month_slots_and_closure_consistency(self):
        for day in range(1, 29):
            for hour in range(8, 13):
                self.create_class(date(2026, 2, day), hour)
        StudioClosure.objects.create(site=self.site, studio=self.studio, closure_date=date(2026, 2, 2), all_day=True)
        data = self.get_data()["current"]["occupation"]
        self.assertEqual(len(data["by_slot"]), 135)
        self.assertEqual(data["scheduled_capacity"], 1350)
        matrix = self.get_data(detail="matrix")["current_week"]
        self.assertEqual(len(matrix["days"]), 27)
        self.assertEqual(sum(cell["scheduled_capacity"] for cell in matrix["cells"]), 1350)
        self.assertNotIn("2026-02-02", [day["date"] for day in matrix["days"]])

    def test_month_boundaries_trends_comparison_and_scoping(self):
        self.create_class(date(2026, 1, 31), capacity=7)
        self.create_class(date(2026, 2, 28), capacity=12)
        self.create_class(date(2026, 3, 1), capacity=20)
        other = Studio.objects.create(site=self.site, name="Other")
        self.create_class(date(2026, 2, 28), capacity=100, studio=other)
        data = self.get_data(studio=self.studio.pk)
        self.assertEqual(data["current"]["occupation"]["scheduled_capacity"], 12)
        self.assertEqual(data["comparison"]["occupation"]["scheduled_capacity"], 7)
        trends = self.get_data(detail="trends", studio=self.studio.pk)["weeks"]
        self.assertEqual(len(trends), 6)
        self.assertEqual(trends[0]["week_start"], "2025-09-01")
        self.assertEqual(trends[-1]["scheduled_capacity"], 12)
        self.assertEqual(trends[-2]["scheduled_capacity"], 7)

    def test_matrix_uses_matched_attendance_and_aggregate_capacity(self):
        scheduled = self.create_class(date(2026, 2, 3), capacity=4)
        other = Studio.objects.create(site=self.site, name="Second room studio")
        self.create_class(date(2026, 2, 3), capacity=6, studio=other)
        client = Client.objects.create(site=self.site, name="Client")
        visit = AttendanceVisit.objects.create(site=self.site, client=client, visit_studio=self.studio,
            natural_key="visit", current_row_hash="hash", visit_date=date(2026, 2, 3), visit_time_raw="8:00 AM")
        AttendanceClassMatch.objects.create(attendance_visit=visit, scheduled_class=scheduled,
            match_method=AttendanceClassMatch.METHOD_MANUAL, confidence=100)
        cell = self.get_data(detail="matrix")["current_week"]["cells"][0]
        self.assertEqual(cell["scheduled_capacity"], 10)
        self.assertEqual(cell["attended"], 1)
        self.assertEqual(cell["occupation_rate"], 10)

    def test_weekly_range_and_invalid_range(self):
        self.create_class(date(2026, 2, 3))
        self.create_class(date(2026, 2, 10), capacity=20)
        data = self.get_data(mode="weekly", date_from="2026-02-09", date_to="2026-02-15")
        self.assertEqual(data["current"]["occupation"]["scheduled_capacity"], 20)
        self.assertEqual(data["comparison"]["occupation"]["scheduled_capacity"], 10)
        response = self.api.get("/api/data/analytics/dashboard/occupancy/", {**self.params, "date_to": "2025-01-01"})
        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        self.api.force_authenticate(user=None)
        self.assertIn(self.api.get("/api/data/analytics/dashboard/occupancy/", self.params).status_code, (401, 403))
