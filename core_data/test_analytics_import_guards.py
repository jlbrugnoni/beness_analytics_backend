from datetime import date, time
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_data.models import (
    AttendanceClassMatch,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    CustomUser,
    ExpectedClassSlot,
    PaymentMethod,
    PricingOption,
    ReportImport,
    Room,
    ScheduledClass,
    ServiceCategory,
    Site,
    StaffMember,
    Studio,
    StudioClosure,
    WeeklyRoomTemplate,
)
from core_data.importers import (
    attendance_natural_key,
    legacy_attendance_missing_occurrence_natural_key,
    legacy_attendance_occurrence_staff_natural_key,
    import_attendance_report,
    preview_attendance_report,
    preview_attendance_rows,
)
from core_data.views import automate_schedule_after_import


def excel_serial(value):
    return (value - date(1899, 12, 30)).days


def inline_cell(cell_ref, value):
    return (
        f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    )


def xlsx_upload(name, headers, rows):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    xml_rows = []
    for row_index, values in enumerate([headers, *rows], start=1):
        cells = [
            inline_cell(f"{letters[column_index]}{row_index}", value)
            for column_index, value in enumerate(values)
        ]
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    workbook = BytesIO()
    with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{''.join(xml_rows)}</sheetData>
</worksheet>""",
        )
    workbook.seek(0)
    return SimpleUploadedFile(
        name,
        workbook.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class AnalyticsImportGuardTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
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

    def attendance_upload(self, remaining_visits="4", revenue="25", staff="Entrenador Uno"):
        headers = [
            "Fecha",
            "Día de la semana",
            "Tiempo",
            "ID del cliente",
            "Cliente",
            "Visita por categoría de servicio",
            "Tipo de Visita",
            "Tipo",
            "Opción de precio",
            "Fecha de Exp.",
            "Visitas Rest.",
            "Personal",
            "Ubicación de visita",
            "Ubicación de venta",
            "Personal pagado",
            "Cancelación tardíá",
            "No presentado",
            "Metodo de programación",
            "Método de pago",
            "Ingresos por visita",
            "Pago de categoría de servicio",
        ]
        row = [
            excel_serial(date(2026, 4, 15)),
            "Miércoles",
            "10:00 AM",
            "100001",
            "Cliente Prueba",
            "Clases Grupales",
            "Clase",
            "Visita",
            "Bono 5 clases",
            excel_serial(date(2026, 4, 30)),
            remaining_visits,
            staff,
            "Pi Tao",
            "Pi Tao",
            "Sí",
            "No",
            "No",
            "Web",
            "Tarjeta",
            revenue,
            "Clases Grupales",
        ]
        return xlsx_upload("attendance.xlsx", headers, [row])

    def attendance_upload_for_clients(self, client_ids):
        headers = [
            "Fecha",
            "Día de la semana",
            "Tiempo",
            "ID del cliente",
            "Cliente",
            "Visita por categoría de servicio",
            "Tipo de Visita",
            "Tipo",
            "Opción de precio",
            "Fecha de Exp.",
            "Visitas Rest.",
            "Personal",
            "Ubicación de visita",
            "Ubicación de venta",
            "Personal pagado",
            "Cancelación tardíá",
            "No presentado",
            "Metodo de programación",
            "Método de pago",
            "Ingresos por visita",
            "Pago de categoría de servicio",
        ]
        rows = []
        for client_id in client_ids:
            rows.append([
                excel_serial(date(2026, 4, 15)),
                "Miércoles",
                "10:00 AM",
                client_id,
                f"Cliente {client_id}",
                "Clases Grupales",
                "Clase",
                "Visita",
                "Bono 5 clases",
                excel_serial(date(2026, 4, 30)),
                "4",
                "Entrenador Uno",
                "Pi Tao",
                "Pi Tao",
                "Sí",
                "No",
                "No",
                "Web",
                "Tarjeta",
                "25",
                "Clases Grupales",
            ])
        return xlsx_upload("attendance.xlsx", headers, rows)

    def test_repeated_attendance_file_is_identical_in_preview_and_import(self):
        first_result = import_attendance_report(self.attendance_upload(), self.site, self.user)
        self.assertEqual(first_result["import"]["attendance_created"], 1)

        preview = preview_attendance_report(
            self.attendance_upload(remaining_visits="2"),
            self.site,
        )
        impact = preview["data_quality"]["import_impact"]
        self.assertEqual(impact["current_records_to_create"], 0)
        self.assertEqual(impact["current_records_to_update"], 0)
        self.assertEqual(impact["current_records_unchanged"], 1)

        second_result = import_attendance_report(
            self.attendance_upload(remaining_visits="2"),
            self.site,
            self.user,
        )
        self.assertEqual(second_result["import"]["attendance_created"], 0)
        self.assertEqual(second_result["import"]["attendance_changed"], 0)
        self.assertEqual(second_result["import"]["attendance_identical"], 1)
        self.assertEqual(second_result["import"]["versions_created"], 0)

        corrected_result = import_attendance_report(
            self.attendance_upload(remaining_visits="1", revenue="30"),
            self.site,
            self.user,
        )
        self.assertEqual(corrected_result["import"]["attendance_created"], 0)
        self.assertEqual(corrected_result["import"]["attendance_changed"], 1)
        self.assertEqual(corrected_result["import"]["attendance_identical"], 0)
        self.assertEqual(corrected_result["import"]["versions_created"], 1)
        corrected_version = AttendanceVisitVersion.objects.get(
            report_import_id=corrected_result["import"]["report_import_id"],
        )
        self.assertEqual(corrected_version.changed_fields, ["revenue"])

    def test_exact_duplicate_attendance_file_is_skipped_before_raw_rows_are_created(self):
        first_result = import_attendance_report(self.attendance_upload(), self.site, self.user)
        self.assertFalse(first_result["import"]["duplicate_skipped"])
        self.assertEqual(first_result["import"]["raw_rows_created"], 1)
        self.assertEqual(AttendanceVisit.objects.count(), 1)

        second_result = import_attendance_report(self.attendance_upload(), self.site, self.user)

        self.assertTrue(second_result["import"]["duplicate_skipped"])
        self.assertEqual(
            second_result["import"]["duplicate_of_report_import_id"],
            first_result["import"]["report_import_id"],
        )
        self.assertEqual(second_result["import"]["raw_rows_created"], 0)
        self.assertEqual(ReportImport.objects.count(), 1)
        self.assertEqual(AttendanceVisit.objects.count(), 1)

    def test_later_attendance_import_removes_missing_visits_in_report_window(self):
        first_result = import_attendance_report(
            self.attendance_upload_for_clients(["100001", "100002"]),
            self.site,
            self.user,
        )
        self.assertEqual(first_result["import"]["attendance_created"], 2)
        self.assertEqual(first_result["import"]["attendance_removed"], 0)

        second_result = import_attendance_report(
            self.attendance_upload_for_clients(["100001"]),
            self.site,
            self.user,
        )

        self.assertEqual(second_result["import"]["attendance_created"], 0)
        self.assertEqual(second_result["import"]["attendance_identical"], 1)
        self.assertEqual(second_result["import"]["attendance_removed"], 1)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 1)
        removed_visit = AttendanceVisit.objects.get(client__mindbody_id="100002")
        self.assertFalse(removed_visit.is_active)
        self.assertEqual(removed_visit.removed_reason, "missing_from_latest_import")
        self.assertEqual(removed_visit.removed_seen_import_id, second_result["import"]["report_import_id"])

        report_import = ReportImport.objects.get(id=second_result["import"]["report_import_id"])
        self.assertEqual(report_import.period_start, date(2026, 4, 15))
        self.assertEqual(report_import.period_end, date(2026, 4, 15))

    def test_later_attendance_import_reactivates_previously_removed_visit(self):
        import_attendance_report(
            self.attendance_upload_for_clients(["100001", "100002"]),
            self.site,
            self.user,
        )
        import_attendance_report(
            self.attendance_upload_for_clients(["100001"]),
            self.site,
            self.user,
        )

        restored_result = import_attendance_report(
            self.attendance_upload_for_clients(["100001", "100002"]),
            self.site,
            self.user,
        )

        self.assertEqual(restored_result["import"]["attendance_reactivated"], 1)
        self.assertEqual(restored_result["import"]["attendance_removed"], 0)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 2)
        restored_visit = AttendanceVisit.objects.get(client__mindbody_id="100002")
        self.assertTrue(restored_visit.is_active)
        self.assertIsNone(restored_visit.removed_seen_import)
        self.assertIsNone(restored_visit.removed_at)
        self.assertIsNone(restored_visit.removed_reason)

    @override_settings(ENABLE_ATTENDANCE_RECONSTRUCTION=True)
    def test_attendance_reconstruction_preview_and_apply_endpoint(self):
        import_attendance_report(
            self.attendance_upload_for_clients(["100001", "100002"]),
            self.site,
            self.user,
        )
        import_attendance_report(
            self.attendance_upload_for_clients(["100001"]),
            self.site,
            self.user,
        )
        AttendanceVisit.objects.update(
            is_active=True,
            removed_seen_import=None,
            removed_at=None,
            removed_reason=None,
        )

        preview = self.client.post(
            "/api/data/report-imports/reconstruct-attendance-history/",
            {"site": self.site.id},
            format="json",
        )

        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertTrue(preview.data["dry_run"])
        self.assertEqual(preview.data["totals"]["visits_removed"], 1)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 2)

        apply_response = self.client.post(
            "/api/data/report-imports/reconstruct-attendance-history/",
            {
                "site": self.site.id,
                "apply": True,
                "confirmation": "RECONSTRUCT ATTENDANCE",
            },
            format="json",
        )

        self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
        self.assertFalse(apply_response.data["dry_run"])
        self.assertEqual(apply_response.data["totals"]["visits_removed"], 1)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 1)
        removed_visit = AttendanceVisit.objects.get(client__mindbody_id="100002")
        self.assertFalse(removed_visit.is_active)
        self.assertEqual(removed_visit.removed_reason, "missing_from_historical_reconstruction")
        self.assertTrue(apply_response.data["rebuilt"])

    @override_settings(ENABLE_ATTENDANCE_RECONSTRUCTION=True)
    def test_restore_reconstructed_attendance_preview_and_apply_endpoint(self):
        import_attendance_report(
            self.attendance_upload_for_clients(["100001", "100002"]),
            self.site,
            self.user,
        )
        import_attendance_report(
            self.attendance_upload_for_clients(["100001"]),
            self.site,
            self.user,
        )

        preview = self.client.post(
            "/api/data/report-imports/restore-reconstructed-attendance/",
            {"site": self.site.id, "date_to": "2026-04-15"},
            format="json",
        )

        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertTrue(preview.data["dry_run"])
        self.assertEqual(preview.data["visits_to_restore"], 1)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 1)

        apply_response = self.client.post(
            "/api/data/report-imports/restore-reconstructed-attendance/",
            {
                "site": self.site.id,
                "date_to": "2026-04-15",
                "apply": True,
                "confirmation": "RESTORE ATTENDANCE",
            },
            format="json",
        )

        self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
        self.assertFalse(apply_response.data["dry_run"])
        self.assertEqual(apply_response.data["visits_restored"], 1)
        self.assertEqual(AttendanceVisit.objects.filter(is_active=True).count(), 2)
        restored_visit = AttendanceVisit.objects.get(client__mindbody_id="100002")
        self.assertTrue(restored_visit.is_active)
        self.assertIsNone(restored_visit.removed_reason)
        self.assertTrue(apply_response.data["rebuilt"])

    @override_settings(ENABLE_ATTENDANCE_RECONSTRUCTION=True)
    def test_cleanup_auto_scheduled_classes_endpoint_removes_only_auto_import_classes(self):
        room = Room.objects.create(site=self.site, studio=self.studio, name="Sala 1", group_capacity=8)
        staff = StaffMember.objects.create(site=self.site, name="Entrenador Uno")
        auto_class = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            room=room,
            staff_member=staff,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
            capacity=8,
            status=ScheduledClass.STATUS_SCHEDULED,
            source=ScheduledClass.SOURCE_MANUAL,
            reason="Automatically created from expected schedule after report import.",
        )
        manual_class = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            room=room,
            staff_member=staff,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(12, 0),
            end_time=time(13, 0),
            capacity=8,
            status=ScheduledClass.STATUS_SCHEDULED,
            source=ScheduledClass.SOURCE_MANUAL,
            reason="Created by user",
        )
        expected_slot = ExpectedClassSlot.objects.create(
            site=self.site,
            studio=self.studio,
            room=room,
            staff_member=staff,
            scheduled_class=auto_class,
            slot_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
            capacity=8,
            status=ExpectedClassSlot.STATUS_MANUALLY_CREATED,
        )

        preview = self.client.post(
            "/api/data/report-imports/cleanup-auto-scheduled-classes/",
            {
                "site": self.site.id,
                "date_from": "2026-04-15",
                "date_to": "2026-04-15",
            },
            format="json",
        )

        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertTrue(preview.data["dry_run"])
        self.assertEqual(preview.data["auto_classes"], 1)
        self.assertEqual(preview.data["capacity_to_remove"], 8)
        self.assertTrue(ScheduledClass.objects.filter(id=auto_class.id).exists())

        apply_response = self.client.post(
            "/api/data/report-imports/cleanup-auto-scheduled-classes/",
            {
                "site": self.site.id,
                "date_from": "2026-04-15",
                "date_to": "2026-04-15",
                "apply": True,
                "confirmation": "CLEANUP AUTO CLASSES",
            },
            format="json",
        )

        self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
        self.assertFalse(ScheduledClass.objects.filter(id=auto_class.id).exists())
        self.assertTrue(ScheduledClass.objects.filter(id=manual_class.id).exists())
        expected_slot.refresh_from_db()
        self.assertIsNone(expected_slot.scheduled_class)
        self.assertEqual(expected_slot.status, ExpectedClassSlot.STATUS_MISSING)

    def test_attendance_schedule_automation_does_not_create_expected_classes(self):
        result = automate_schedule_after_import(
            self.site,
            {"preview": {"date_range": {"from": "2026-04-15", "to": "2026-04-15"}}},
            "attendance_with_revenue",
        )

        self.assertTrue(result["manual_classes"]["skipped"])
        self.assertEqual(ScheduledClass.objects.count(), 0)

    @override_settings(ENABLE_ATTENDANCE_RECONSTRUCTION=True)
    def test_attendance_reconstruction_apply_requires_confirmation(self):
        response = self.client.post(
            "/api/data/report-imports/reconstruct-attendance-history/",
            {"site": self.site.id, "apply": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attendance_staff_change_updates_existing_visit(self):
        first_result = import_attendance_report(
            self.attendance_upload(staff="Entrenador Uno"),
            self.site,
            self.user,
        )
        self.assertEqual(first_result["import"]["attendance_created"], 1)

        preview = preview_attendance_report(
            self.attendance_upload(staff="Entrenador Dos"),
            self.site,
        )
        impact = preview["data_quality"]["import_impact"]
        self.assertEqual(impact["current_records_to_create"], 0)
        self.assertEqual(impact["current_records_to_update"], 1)

        second_result = import_attendance_report(
            self.attendance_upload(staff="Entrenador Dos"),
            self.site,
            self.user,
        )

        self.assertEqual(second_result["import"]["attendance_created"], 0)
        self.assertEqual(second_result["import"]["attendance_changed"], 1)
        self.assertEqual(AttendanceVisitVersion.objects.count(), 2)
        visit = AttendanceVisitVersion.objects.latest("id").attendance_visit
        self.assertEqual(visit.staff_member.name, "Entrenador dos")
        self.assertEqual(visit.versions.count(), 2)

    def test_attendance_preview_matches_historical_occurrence_staff_key(self):
        rows = preview_attendance_rows(self.attendance_upload(staff="Entrenador Uno"))
        row = rows["valid_rows"][0]
        payload = row["payload"]
        client = Client.objects.create(
            site=self.site,
            name="Cliente Prueba",
            mindbody_id=payload["ID del cliente"],
        )
        visit = AttendanceVisit.objects.create(
            site=self.site,
            natural_key=legacy_attendance_occurrence_staff_natural_key(self.site, payload),
            current_row_hash=row["hash"],
            client=client,
            visit_studio=self.studio,
            visit_date=date.fromisoformat(payload["_visit_date"]),
            visit_time_raw=payload["Tiempo"],
        )

        preview = preview_attendance_report(
            self.attendance_upload(staff="Entrenador Uno"),
            self.site,
        )
        impact = preview["data_quality"]["import_impact"]
        self.assertEqual(impact["current_records_to_create"], 0)
        self.assertEqual(impact["current_records_unchanged"], 1)

        result = import_attendance_report(
            self.attendance_upload(staff="Entrenador Uno"),
            self.site,
            self.user,
        )
        self.assertEqual(result["import"]["attendance_created"], 0)
        self.assertEqual(result["import"]["attendance_identical"], 1)
        visit.refresh_from_db()
        self.assertEqual(visit.natural_key, attendance_natural_key(self.site, payload))

    def test_attendance_preview_matches_historical_missing_occurrence_key(self):
        rows = preview_attendance_rows(self.attendance_upload(staff="Entrenador Uno"))
        row = rows["valid_rows"][0]
        payload = row["payload"]
        client = Client.objects.create(
            site=self.site,
            name="Cliente Prueba",
            mindbody_id=payload["ID del cliente"],
        )
        visit = AttendanceVisit.objects.create(
            site=self.site,
            natural_key=legacy_attendance_missing_occurrence_natural_key(self.site, payload),
            current_row_hash=row["hash"],
            client=client,
            visit_studio=self.studio,
            visit_date=date.fromisoformat(payload["_visit_date"]),
            visit_time_raw=payload["Tiempo"],
        )

        preview = preview_attendance_report(
            self.attendance_upload(staff="Entrenador Uno"),
            self.site,
        )
        impact = preview["data_quality"]["import_impact"]
        self.assertEqual(impact["current_records_to_create"], 0)
        self.assertEqual(impact["current_records_unchanged"], 1)
        self.assertEqual(impact["legacy_records_matched"], 1)

        result = import_attendance_report(
            self.attendance_upload(staff="Entrenador Uno"),
            self.site,
            self.user,
        )
        self.assertEqual(result["import"]["attendance_created"], 0)
        self.assertEqual(result["import"]["attendance_identical"], 1)
        visit.refresh_from_db()
        self.assertEqual(visit.natural_key, attendance_natural_key(self.site, payload))

    def test_rebuild_matches_repairs_staff_change_duplicates(self):
        category = ServiceCategory.objects.create(site=self.site, name="Clases Grupales")
        pricing_option = PricingOption.objects.create(
            site=self.site,
            name="Bono 5 clases",
            service_category=category,
        )
        staff_one = StaffMember.objects.create(site=self.site, name="Entrenador Uno")
        staff_two = StaffMember.objects.create(site=self.site, name="Entrenador Dos")
        scheduled_class = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(10, 50),
            capacity=8,
            staff_member=staff_two,
        )
        client = Client.objects.create(
            site=self.site,
            name="Cliente Prueba",
            mindbody_id="100001",
        )
        old_visit = AttendanceVisit.objects.create(
            site=self.site,
            natural_key="old-staff-key",
            current_row_hash="old-staff-hash",
            client=client,
            staff_member=staff_one,
            visit_studio=self.studio,
            service_category=category,
            pricing_option=pricing_option,
            visit_date=date(2026, 4, 15),
            visit_time_raw="10:00 AM",
        )
        new_visit = AttendanceVisit.objects.create(
            site=self.site,
            natural_key="new-staff-key",
            current_row_hash="new-staff-hash",
            client=client,
            staff_member=staff_two,
            visit_studio=self.studio,
            service_category=category,
            pricing_option=pricing_option,
            visit_date=date(2026, 4, 15),
            visit_time_raw="10:00 AM",
        )
        AttendanceClassMatch.objects.create(
            attendance_visit=old_visit,
            scheduled_class=scheduled_class,
            match_method=AttendanceClassMatch.METHOD_SINGLE_CLASS_SAME_TIME,
        )
        AttendanceClassMatch.objects.create(
            attendance_visit=new_visit,
            scheduled_class=scheduled_class,
            match_method=AttendanceClassMatch.METHOD_EXACT_INSTRUCTOR_TIME,
        )

        response = self.client.post(
            "/api/data/analytics/class-matches/rebuild/",
            {
                "site": self.site.id,
                "date_from": "2026-04-15",
                "date_to": "2026-04-15",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["attendance_duplicate_repair"]["duplicate_visits_deleted"],
            1,
        )
        self.assertEqual(AttendanceVisit.objects.count(), 1)
        self.assertEqual(AttendanceClassMatch.objects.count(), 1)
        self.assertEqual(response.data["visits_processed"], 1)

    def test_cancel_scheduled_classes_for_day_uses_selected_scope(self):
        room_one = Room.objects.create(site=self.site, studio=self.studio, name="Sala 1", group_capacity=8)
        room_two = Room.objects.create(site=self.site, studio=self.studio, name="Sala 2", group_capacity=8)
        staff = StaffMember.objects.create(site=self.site, name="Entrenador Uno")
        category = ServiceCategory.objects.create(site=self.site, name="Clases Grupales")
        pricing_option = PricingOption.objects.create(
            site=self.site,
            name="Bono 5 clases",
            service_category=category,
        )
        client = Client.objects.create(
            site=self.site,
            name="Cliente Prueba",
            mindbody_id="100001",
        )
        class_one = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            room=room_one,
            staff_member=staff,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(10, 50),
            capacity=8,
        )
        class_two = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            room=room_one,
            staff_member=staff,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(11, 0),
            end_time=time(11, 50),
            capacity=8,
        )
        other_room_class = ScheduledClass.objects.create(
            site=self.site,
            studio=self.studio,
            room=room_two,
            staff_member=staff,
            name="Pilates",
            class_date=date(2026, 4, 15),
            start_time=time(12, 0),
            end_time=time(12, 50),
            capacity=8,
        )
        ExpectedClassSlot.objects.create(
            site=self.site,
            studio=self.studio,
            room=room_one,
            staff_member=staff,
            scheduled_class=class_one,
            slot_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(10, 50),
            status=ExpectedClassSlot.STATUS_MATCHED,
        )
        visit = AttendanceVisit.objects.create(
            site=self.site,
            natural_key="attendance-key",
            current_row_hash="attendance-hash",
            client=client,
            staff_member=staff,
            visit_studio=self.studio,
            service_category=category,
            pricing_option=pricing_option,
            visit_date=date(2026, 4, 15),
            visit_time_raw="10:00 AM",
        )
        AttendanceClassMatch.objects.create(
            attendance_visit=visit,
            scheduled_class=class_one,
            match_method=AttendanceClassMatch.METHOD_EXACT_INSTRUCTOR_TIME,
        )

        response = self.client.post(
            "/api/data/scheduled-classes/cancel-day/",
            {
                "site": self.site.id,
                "studio": self.studio.id,
                "room": room_one.id,
                "date": "2026-04-15",
                "reason": "Holiday",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["classes_found"], 2)
        self.assertEqual(response.data["classes_cancelled"], 2)
        self.assertEqual(response.data["attended_count"], 1)
        class_one.refresh_from_db()
        class_two.refresh_from_db()
        other_room_class.refresh_from_db()
        self.assertEqual(class_one.status, ScheduledClass.STATUS_CANCELLED)
        self.assertEqual(class_two.status, ScheduledClass.STATUS_CANCELLED)
        self.assertEqual(other_room_class.status, ScheduledClass.STATUS_SCHEDULED)
        self.assertEqual(ExpectedClassSlot.objects.get(scheduled_class=class_one).status, ExpectedClassSlot.STATUS_CANCELLED)

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
