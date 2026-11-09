from datetime import date, time
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from .models import (Site, Studio, Room, RoomAlias, RoomIdentityEvent, ScheduledClass,
                     WeeklyRoomTemplate, StudioClosure, AttendanceClassMatch, AttendanceVisit,
                     Client, CustomUser, UserAccessProfile, StaffMember, TrainerAvailabilityRawRow)
from .room_identity import add_alias, resolve_room, repair_plan, consolidate_rooms
from .importers import (import_trainer_availability_report, preview_trainer_availability_report,
                        trainer_legacy_class_natural_key)


class RoomIdentityTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="Room alias test Spain", country_code="ES")
        self.studio = Studio.objects.create(site=self.site, name="Estepona")
        self.room = Room.objects.create(site=self.site, studio=self.studio, name="Sala 1", group_capacity=10)
        self.staff = StaffMember.objects.create(site=self.site, name="Ana")
        self.user = CustomUser.objects.create_superuser(email="room-test@example.test", password="test")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def report(self, room="Sala 1"):
        html = f'''<table><tr><td>SCHEDULE FOR Ana</td></tr><tr><td>9 de noviembre de 2026</td></tr>
        <tr><td>8:00 AM - 9:00 AM</td><td>Pilates</td><td>Estepona</td><td>Group</td><td>{room}</td><td></td></tr></table>'''
        return SimpleUploadedFile("trainer.xls", html.encode(), content_type="application/vnd.ms-excel")

    def scheduled(self, room=None, **extra):
        values = dict(site=self.site, studio=self.studio, room=room or self.room, name="Pilates", class_date=date(2026,11,9),
            start_time=time(8), end_time=time(9), staff_member=self.staff, capacity=10, status="scheduled", source="trainer_availability")
        values.update(extra)
        return ScheduledClass.objects.create(**values)

    def test_alias_is_scoped_and_preserves_names_after_rename(self):
        add_alias(self.room, "Sala Grupal", self.user, display_name="Sala Grupal")
        self.assertEqual(resolve_room(self.site, self.studio, " SALA 1 ").pk, self.room.pk)
        self.assertEqual(resolve_room(self.site, self.studio, "Sala Grupal").pk, self.room.pk)
        other = Studio.objects.create(site=self.site, name="Other")
        self.assertIsNone(resolve_room(self.site, other, "Sala Grupal"))
        self.assertEqual(RoomIdentityEvent.objects.count(), 1)

    def test_old_and_new_reports_reuse_class_and_capacity(self):
        first = import_trainer_availability_report(self.report(), self.site, uploaded_by=self.user)
        pk = ScheduledClass.objects.get().pk
        add_alias(self.room, "Sala Grupal", self.user, display_name="Sala Grupal")
        preview = preview_trainer_availability_report(self.report("Sala Grupal"), self.site)
        self.assertEqual(preview["lookup_preview"]["rooms"]["new"], 0)
        self.assertEqual(preview["capacity_requirements"], [])
        self.assertEqual(preview["data_quality"]["import_impact"]["current_records_to_create"], 0)
        import_trainer_availability_report(self.report("Sala Grupal"), self.site, uploaded_by=self.user)
        import_trainer_availability_report(self.report(), self.site, uploaded_by=self.user)
        item = ScheduledClass.objects.get()
        self.assertEqual(item.pk, pk)
        self.assertEqual(item.capacity, 10)
        self.assertEqual(Room.objects.count(), 1)
        self.assertEqual(set(TrainerAvailabilityRawRow.objects.values_list("raw_payload__room", flat=True)), {"Sala 1", "Sala Grupal"})

    def test_legacy_class_key_is_reused(self):
        payload = {"_class_date":"2026-11-09", "_start_time":"08:00", "_end_time":"09:00", "studio":"Estepona", "room":"Sala 1", "staff":"Ana", "event":"Pilates"}
        original = self.scheduled(natural_key=trainer_legacy_class_natural_key(self.site, payload))
        add_alias(self.room, "Sala Grupal", self.user)
        import_trainer_availability_report(self.report("Sala Grupal"), self.site)
        self.assertEqual(ScheduledClass.objects.count(), 1)
        self.assertEqual(ScheduledClass.objects.get().pk, original.pk)

    def test_unrecognized_preview_offers_only_same_studio_rooms(self):
        other = Studio.objects.create(site=self.site, name="Other")
        Room.objects.create(site=self.site, studio=other, name="Sala Grupal")
        preview = preview_trainer_availability_report(self.report("Sala Grupal"), self.site)
        row = preview["lookup_preview"]["rooms"]["unrecognized"][0]
        self.assertEqual([r["id"] for r in row["existing_room_options"]], [self.room.pk])

    def test_alias_does_not_override_an_existing_room(self):
        Room.objects.create(site=self.site, studio=self.studio, name="Sala Grupal")
        with self.assertRaises(ValidationError):
            add_alias(self.room, "Sala Grupal", self.user)
        self.assertFalse(RoomAlias.objects.exists())

    def test_repair_preview_then_apply_preserves_manual_links_and_source_classes(self):
        duplicate = Room.objects.create(site=self.site, studio=self.studio, name="Sala Grupal", group_capacity=10)
        keep = self.scheduled()
        retire = self.scheduled(room=duplicate)
        client = Client.objects.create(site=self.site, name="Client")
        visit = AttendanceVisit.objects.create(site=self.site, client=client, visit_studio=self.studio,
            visit_date=date(2026,11,9), visit_time_raw="8:00 AM", natural_key="v1", current_row_hash="h")
        match = AttendanceClassMatch.objects.create(attendance_visit=visit, scheduled_class=retire,
            candidate_class_ids=[keep.pk,retire.pk], match_method=AttendanceClassMatch.METHOD_MANUAL, confidence=1)
        unresolved_visit = AttendanceVisit.objects.create(site=self.site, client=client, visit_studio=self.studio,
            staff_member=self.staff, visit_date=date(2026,11,9), visit_time_raw="8:00 AM", natural_key="v2", current_row_hash="h2")
        unresolved = AttendanceClassMatch.objects.create(attendance_visit=unresolved_visit,
            candidate_class_ids=[keep.pk,retire.pk], match_method=AttendanceClassMatch.METHOD_AMBIGUOUS, confidence=0.4)
        plan, token, _ = repair_plan(duplicate, self.room, "Sala Grupal")
        self.assertFalse(plan["blockers"])
        self.assertTrue(duplicate.active)
        self.assertEqual(len(plan["duplicate_classes"]), 1)
        consolidate_rooms(duplicate, self.room, self.user, token, "Sala Grupal")
        duplicate.refresh_from_db(); match.refresh_from_db(); retire.refresh_from_db()
        self.assertFalse(duplicate.active)
        self.assertEqual(retire.status, "cancelled")
        self.assertEqual(match.scheduled_class_id, keep.pk)
        self.assertEqual(match.match_method, AttendanceClassMatch.METHOD_MANUAL)
        self.assertEqual(match.candidate_class_ids, [keep.pk])
        unresolved.refresh_from_db()
        self.assertEqual(unresolved.scheduled_class_id, keep.pk)
        self.assertEqual(unresolved.match_method, AttendanceClassMatch.METHOD_EXACT_INSTRUCTOR_TIME)
        self.assertEqual(resolve_room(self.site,self.studio,"Sala Grupal").pk,self.room.pk)
        self.assertEqual(ScheduledClass.objects.count(), 2)
        import_trainer_availability_report(self.report("Sala Grupal"), self.site)
        self.assertEqual(ScheduledClass.objects.count(), 2)
        self.assertEqual(ScheduledClass.objects.filter(status="scheduled").count(), 1)
        self.assertTrue(RoomIdentityEvent.objects.filter(action="consolidate").exists())

    def test_conflicting_capacity_and_manual_class_block_repair(self):
        duplicate = Room.objects.create(site=self.site, studio=self.studio, name="Sala Grupal", group_capacity=12)
        self.scheduled()
        self.scheduled(room=duplicate, manually_modified=True)
        plan, token, _ = repair_plan(duplicate,self.room)
        self.assertTrue(plan["blockers"])
        with self.assertRaises(ValidationError):
            consolidate_rooms(duplicate,self.room,self.user,token)
        duplicate.refresh_from_db()
        self.assertTrue(duplicate.active)

    def test_stale_preview_cannot_apply(self):
        duplicate = Room.objects.create(site=self.site, studio=self.studio, name="Sala Grupal",group_capacity=10)
        _,token,_ = repair_plan(duplicate,self.room)
        self.scheduled(room=duplicate)
        with self.assertRaises(ValidationError):
            consolidate_rooms(duplicate,self.room,self.user,token)

    def test_moves_templates_closures_and_classes_without_deleting(self):
        duplicate = Room.objects.create(site=self.site, studio=self.studio,name="Sala Grupal",group_capacity=10)
        item = self.scheduled(room=duplicate)
        template = WeeklyRoomTemplate.objects.create(site=self.site,studio=self.studio,room=duplicate,
            name="Pilates",weekday=0,start_time=time(8),end_time=time(9),capacity=10,active_from=date(2026,11,1))
        closure = StudioClosure.objects.create(site=self.site,studio=self.studio,room=duplicate,closure_date=date(2026,11,10),all_day=True)
        _,token,_ = repair_plan(duplicate,self.room)
        consolidate_rooms(duplicate,self.room,self.user,token)
        for obj in [item,template,closure]:
            obj.refresh_from_db();self.assertEqual(obj.room_id,self.room.pk)

    def test_permission_and_cross_studio_guards(self):
        other = Studio.objects.create(site=self.site,name="Other")
        foreign = Room.objects.create(site=self.site,studio=other,name="Room")
        response=self.api.post(f"/api/data/rooms/{self.room.pk}/consolidate/",{"source_room":foreign.pk},format="json")
        self.assertEqual(response.status_code,400)
        user=CustomUser.objects.create_user(email="viewer@example.test",password="test")
        profile,_=UserAccessProfile.objects.get_or_create(user=user)
        profile.allowed_studios.add(self.studio)
        self.api.force_authenticate(user)
        self.assertEqual(self.api.post(f"/api/data/rooms/{self.room.pk}/aliases/",{"name":"Alias"},format="json").status_code,403)
        profile.can_edit_data=True;profile.save()
        self.assertEqual(self.api.post(f"/api/data/rooms/{foreign.pk}/aliases/",{"name":"Alias"},format="json").status_code,404)

    def test_rename_via_room_editor_retains_import_identity(self):
        response=self.api.patch(f"/api/data/rooms/{self.room.pk}/",{"name":"Sala Grupal"},format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(resolve_room(self.site,self.studio,"Sala 1").pk,self.room.pk)
        self.assertEqual(resolve_room(self.site,self.studio,"Sala Grupal").pk,self.room.pk)

    def test_expected_template_duplicate_keeps_imported_class_and_template(self):
        duplicate = Room.objects.create(site=self.site,studio=self.studio,name="Sala Grupal",group_capacity=10)
        template = WeeklyRoomTemplate.objects.create(site=self.site,studio=self.studio,room=self.room,
            name="Pilates",weekday=0,start_time=time(8),end_time=time(9),capacity=10,active_from=date(2026,11,1))
        expected = self.scheduled(source=ScheduledClass.SOURCE_EXPECTED_TEMPLATE,template=template,expected_from_template=True)
        actual = self.scheduled(room=duplicate)
        plan,token,_=repair_plan(duplicate,self.room)
        self.assertEqual(plan["blockers"],[])
        consolidate_rooms(duplicate,self.room,self.user,token)
        actual.refresh_from_db();expected.refresh_from_db()
        self.assertEqual(expected.status,"cancelled")
        self.assertEqual(actual.template_id,template.pk)
        self.assertEqual(actual.room_id,self.room.pk)
        self.assertEqual(ScheduledClass.objects.filter(status="scheduled").count(),1)

    def test_overlapping_templates_block_instead_of_doubling_schedule(self):
        duplicate = Room.objects.create(site=self.site,studio=self.studio,name="Sala Grupal",group_capacity=10)
        for room in [duplicate,self.room]:
            WeeklyRoomTemplate.objects.create(site=self.site,studio=self.studio,room=room,
                name="Pilates",weekday=0,start_time=time(8),end_time=time(9),capacity=10,active_from=date(2026,11,1))
        plan,_,_=repair_plan(duplicate,self.room)
        self.assertTrue(any("template" in reason.lower() for reason in plan["blockers"]))

    def test_api_preview_and_apply_and_source_history(self):
        duplicate = Room.objects.create(site=self.site,studio=self.studio,name="Sala Grupal",group_capacity=10)
        self.scheduled(room=duplicate)
        url=f"/api/data/rooms/{self.room.pk}/consolidate/"
        body={"source_room":duplicate.pk,"display_name":"Sala Grupal"}
        preview=self.api.post(url,body,format="json")
        self.assertEqual(preview.status_code,200,preview.data)
        duplicate.refresh_from_db();self.assertTrue(duplicate.active)
        response=self.api.post(url,{**body,"token":preview.data["token"],"apply":True},format="json")
        self.assertEqual(response.status_code,200,response.data)
        duplicate.refresh_from_db();self.assertFalse(duplicate.active)
        event=RoomIdentityEvent.objects.get(action="consolidate")
        self.assertEqual(len(event.evidence["before"]["classes"]),1)

    def test_room_editor_cannot_create_a_room_that_shadows_an_alias(self):
        add_alias(self.room,"Sala Grupal",self.user)
        response=self.api.post("/api/data/rooms/",{"name":"Sala Grupal","site":self.site.pk,"studio":self.studio.pk},format="json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(Room.objects.count(),1)
