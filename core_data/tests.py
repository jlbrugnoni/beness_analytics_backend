from datetime import datetime, time, timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_data.models import (
    Center,
    CustomUser,
    DailyRoutineAssignment,
    GeneralRoutineAssignment,
    Machine,
    Room,
    Routine,
    RoutineSession,
)


class DailyRoutineAssignmentAPITests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="planner@example.com",
            password="testpass123",
            first_name="Plan",
            last_name="Ner",
        )
        self.client.force_authenticate(self.user)

        self.center = Center.objects.create(name="Centro Principal")
        self.room = Room.objects.create(name="Sala 1", center=self.center)
        self.machine = Machine.objects.create(name="Reformer")

        self.routine_a = Routine.objects.create(
            name="Clase A",
            duration=50,
            on_edit=False,
        )
        self.routine_a.machines.add(self.machine)

        self.routine_b = Routine.objects.create(
            name="Clase B",
            duration=55,
            on_edit=False,
        )
        self.routine_b.machines.add(self.machine)

        self.bulk_assign_url = "/api/data/daily-routine-assignments/bulk-assign/"

    def _make_session(self, *, session_date, session_time=time(9, 0), routine=None, state=0, **extra_fields):
        scheduled_at = timezone.make_aware(datetime.combine(session_date, session_time))
        return RoutineSession.objects.create(
            room=self.room,
            routine=routine or self.routine_a,
            scheduled_at=scheduled_at,
            duration=60,
            state=state,
            created_by=self.user,
            **extra_fields,
        )

    def _bulk_assign(self, *, assignment_date, routine=None, overwrite_manual=False):
        return self.client.post(
            self.bulk_assign_url,
            {
                "date": assignment_date.isoformat(),
                "routine_id": (routine or self.routine_b).id,
                "center_id": self.center.id,
                "room_ids": [self.room.id],
                "overwrite_manual": overwrite_manual,
            },
            format="json",
        )

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_bulk_assign_updates_only_future_programmed_sessions(self):
        future_date = timezone.localdate() + timedelta(days=2)
        programmed_session = self._make_session(session_date=future_date, routine=self.routine_a, state=0)
        in_progress_session = self._make_session(
            session_date=future_date,
            session_time=time(10, 0),
            routine=self.routine_a,
            state=1,
        )

        response = self._bulk_assign(assignment_date=future_date)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        programmed_session.refresh_from_db()
        in_progress_session.refresh_from_db()

        self.assertEqual(programmed_session.routine_id, self.routine_b.id)
        self.assertIsNotNone(programmed_session.daily_routine_assignment)
        self.assertEqual(in_progress_session.routine_id, self.routine_a.id)
        self.assertEqual(response.data["updated_sessions"], 1)
        self.assertEqual(response.data["skipped_non_programmed_sessions"], 1)
        self.assertEqual(response.data["skipped_past_sessions"], 0)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_bulk_assign_rejects_past_dates_when_flag_is_disabled(self):
        past_date = timezone.localdate() - timedelta(days=3)

        response = self._bulk_assign(assignment_date=past_date)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date", response.data)
        self.assertEqual(DailyRoutineAssignment.objects.count(), 0)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=True)
    def test_bulk_assign_can_create_past_assignment_but_does_not_modify_past_sessions(self):
        past_date = timezone.localdate() - timedelta(days=4)
        past_session = self._make_session(session_date=past_date, routine=self.routine_a, state=0)

        response = self._bulk_assign(assignment_date=past_date)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        past_session.refresh_from_db()
        assignment = DailyRoutineAssignment.objects.get(date=past_date, room=self.room)

        self.assertEqual(past_session.routine_id, self.routine_a.id)
        self.assertIsNone(past_session.daily_routine_assignment)
        self.assertEqual(assignment.routine_id, self.routine_b.id)
        self.assertEqual(response.data["updated_sessions"], 0)
        self.assertEqual(response.data["skipped_past_sessions"], 1)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_bulk_assign_preserves_manual_overrides_by_default(self):
        future_date = timezone.localdate() + timedelta(days=1)
        previous_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=self.room,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        session = self._make_session(
            session_date=future_date,
            routine=self.routine_a,
            state=0,
            daily_routine_assignment=previous_assignment,
            routine_manually_overridden=True,
        )

        response = self._bulk_assign(assignment_date=future_date, overwrite_manual=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.routine_id, self.routine_a.id)
        self.assertTrue(session.routine_manually_overridden)
        self.assertEqual(response.data["updated_sessions"], 0)
        self.assertEqual(response.data["skipped_overridden_sessions"], 1)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_bulk_assign_overwrites_manual_overrides_when_requested(self):
        future_date = timezone.localdate() + timedelta(days=1)
        previous_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=self.room,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        session = self._make_session(
            session_date=future_date,
            routine=self.routine_a,
            state=0,
            daily_routine_assignment=previous_assignment,
            routine_manually_overridden=True,
        )

        response = self._bulk_assign(assignment_date=future_date, overwrite_manual=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.routine_id, self.routine_b.id)
        self.assertFalse(session.routine_manually_overridden)
        self.assertEqual(response.data["updated_sessions"], 1)
        self.assertEqual(response.data["skipped_overridden_sessions"], 0)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_delete_daily_assignment_without_general_deactivates_assignment_and_clears_non_manual_sessions(self):
        future_date = timezone.localdate() + timedelta(days=2)
        assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=self.room,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        scheduled_session = self._make_session(
            session_date=future_date,
            routine=self.routine_a,
            state=0,
            daily_routine_assignment=assignment,
            routine_manually_overridden=False,
        )
        manual_session = self._make_session(
            session_date=future_date,
            session_time=time(10, 0),
            routine=self.routine_b,
            state=0,
            daily_routine_assignment=assignment,
            routine_manually_overridden=True,
        )

        response = self.client.delete(f"/api/data/daily-routine-assignments/{assignment.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        scheduled_session.refresh_from_db()
        manual_session.refresh_from_db()
        self.assertFalse(assignment.active)
        self.assertIsNone(scheduled_session.routine)
        self.assertIsNone(scheduled_session.daily_routine_assignment)
        self.assertEqual(manual_session.routine_id, self.routine_b.id)
        self.assertTrue(manual_session.routine_manually_overridden)
        self.assertIsNone(manual_session.daily_routine_assignment)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_delete_daily_assignment_with_general_keeps_override_row_and_clears_non_manual_sessions(self):
        future_date = timezone.localdate() + timedelta(days=2)
        general_assignment = GeneralRoutineAssignment.objects.create(
            date=future_date,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=self.room,
            routine=self.routine_b,
            general_routine_assignment=general_assignment,
            overrides_general_assignment=True,
            created_by=self.user,
            updated_by=self.user,
        )
        scheduled_session = self._make_session(
            session_date=future_date,
            routine=self.routine_b,
            state=0,
            daily_routine_assignment=assignment,
            routine_manually_overridden=False,
        )

        response = self.client.delete(f"/api/data/daily-routine-assignments/{assignment.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        scheduled_session.refresh_from_db()
        self.assertTrue(assignment.active)
        self.assertIsNone(assignment.routine)
        self.assertTrue(assignment.overrides_general_assignment)
        self.assertEqual(assignment.general_routine_assignment_id, general_assignment.id)
        self.assertIsNone(scheduled_session.routine)
        self.assertEqual(scheduled_session.daily_routine_assignment_id, assignment.id)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_clear_day_clears_all_center_assignments_for_date(self):
        future_date = timezone.localdate() + timedelta(days=3)
        second_room = Room.objects.create(name="Sala 2", center=self.center)
        first_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=self.room,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        second_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center,
            room=second_room,
            routine=self.routine_b,
            created_by=self.user,
            updated_by=self.user,
        )
        first_session = self._make_session(
            session_date=future_date,
            routine=self.routine_a,
            daily_routine_assignment=first_assignment,
        )
        second_session = RoutineSession.objects.create(
            room=second_room,
            routine=self.routine_b,
            scheduled_at=timezone.make_aware(datetime.combine(future_date, time(10, 0))),
            duration=60,
            state=0,
            created_by=self.user,
            daily_routine_assignment=second_assignment,
        )

        response = self.client.post(
            "/api/data/daily-routine-assignments/clear-day/",
            {"center_id": self.center.id, "date": future_date.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_assignment.refresh_from_db()
        second_assignment.refresh_from_db()
        first_session.refresh_from_db()
        second_session.refresh_from_db()
        self.assertFalse(first_assignment.active)
        self.assertFalse(second_assignment.active)
        self.assertIsNone(first_session.routine)
        self.assertIsNone(second_session.routine)


class RoutineSessionUpdateRestrictionTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="coach@example.com",
            password="testpass123",
            first_name="Coach",
            last_name="User",
        )
        self.client.force_authenticate(self.user)

        self.center = Center.objects.create(name="Centro Test")
        self.room = Room.objects.create(name="Sala Test", center=self.center)
        self.machine = Machine.objects.create(name="Cadillac")

        self.routine_a = Routine.objects.create(name="Clase Base", duration=45, on_edit=False)
        self.routine_a.machines.add(self.machine)
        self.routine_b = Routine.objects.create(name="Clase Nueva", duration=60, on_edit=False)
        self.routine_b.machines.add(self.machine)

    def _make_session(self, *, session_date, session_time=time(8, 0), routine=None, state=0):
        scheduled_at = timezone.make_aware(datetime.combine(session_date, session_time))
        return RoutineSession.objects.create(
            room=self.room,
            routine=routine or self.routine_a,
            user=self.user,
            scheduled_at=scheduled_at,
            duration=60,
            state=state,
            created_by=self.user,
        )

    def test_patch_rejects_routine_change_for_non_programmed_session(self):
        future_date = timezone.localdate() + timedelta(days=1)
        session = self._make_session(session_date=future_date, state=1)

        response = self.client.patch(
            f"/api/data/routinesessions/{session.id}/",
            {"routine_id": self.routine_b.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        self.assertEqual(session.routine_id, self.routine_a.id)


class GeneralRoutineAssignmentAPITests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="globalplanner@example.com",
            password="testpass123",
            first_name="Global",
            last_name="Planner",
        )
        self.client.force_authenticate(self.user)

        self.center_a = Center.objects.create(name="Centro A")
        self.center_b = Center.objects.create(name="Centro B")
        self.center_c = Center.objects.create(name="Centro Sin Uso")
        self.room_a = Room.objects.create(name="Sala A", center=self.center_a)
        self.room_b = Room.objects.create(name="Sala B", center=self.center_b)
        self.room_c = Room.objects.create(name="Sala C", center=self.center_c)
        self.machine = Machine.objects.create(name="Chair")

        self.routine_a = Routine.objects.create(name="Clase General", duration=50, on_edit=False)
        self.routine_a.machines.add(self.machine)
        self.routine_b = Routine.objects.create(name="Clase Override", duration=55, on_edit=False)
        self.routine_b.machines.add(self.machine)
        self.routine_c = Routine.objects.create(name="Clase Nueva General", duration=60, on_edit=False)
        self.routine_c.machines.add(self.machine)

        self.bulk_assign_url = "/api/data/general-routine-assignments/bulk-assign/"

    def _make_session(self, *, room, session_date, session_time=time(9, 0), routine=None, state=0, **extra_fields):
        scheduled_at = timezone.make_aware(datetime.combine(session_date, session_time))
        return RoutineSession.objects.create(
            room=room,
            routine=routine or self.routine_a,
            scheduled_at=scheduled_at,
            duration=60,
            state=state,
            created_by=self.user,
            **extra_fields,
        )

    def _bulk_assign(self, *, assignment_date, routine, overwrite_room_overrides=False, overwrite_manual=False):
        return self.client.post(
            self.bulk_assign_url,
            {
                "date": assignment_date.isoformat(),
                "routine_id": routine.id,
                "overwrite_room_overrides": overwrite_room_overrides,
                "overwrite_manual": overwrite_manual,
            },
            format="json",
        )

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_general_bulk_assign_creates_daily_assignments_for_all_rooms(self):
        future_date = timezone.localdate() + timedelta(days=2)
        session_a = self._make_session(room=self.room_a, session_date=future_date, routine=self.routine_b, state=0)
        session_b = self._make_session(room=self.room_b, session_date=future_date, routine=self.routine_b, state=0)

        response = self._bulk_assign(assignment_date=future_date, routine=self.routine_a)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(GeneralRoutineAssignment.objects.count(), 1)
        self.assertEqual(DailyRoutineAssignment.objects.filter(date=future_date).count(), 2)

        assignment_a = DailyRoutineAssignment.objects.get(date=future_date, room=self.room_a)
        assignment_b = DailyRoutineAssignment.objects.get(date=future_date, room=self.room_b)
        self.assertEqual(assignment_a.routine_id, self.routine_a.id)
        self.assertEqual(assignment_b.routine_id, self.routine_a.id)
        self.assertFalse(assignment_a.overrides_general_assignment)
        self.assertFalse(assignment_b.overrides_general_assignment)
        self.assertEqual(assignment_a.general_routine_assignment_id, assignment_b.general_routine_assignment_id)

        session_a.refresh_from_db()
        session_b.refresh_from_db()
        self.assertEqual(session_a.routine_id, self.routine_a.id)
        self.assertEqual(session_b.routine_id, self.routine_a.id)
        self.assertEqual(response.data["created_room_assignments"], 2)
        self.assertEqual(response.data["targeted_centers_count"], 2)
        self.assertEqual(response.data["targeted_rooms_count"], 2)
        self.assertFalse(DailyRoutineAssignment.objects.filter(date=future_date, room=self.room_c).exists())

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_general_week_summary_counts_planned_assignments(self):
        future_date = timezone.localdate() + timedelta(days=2)
        start_of_week = future_date - timedelta(days=future_date.weekday())
        self._make_session(room=self.room_a, session_date=future_date, routine=self.routine_b, state=0)
        self._make_session(room=self.room_b, session_date=future_date, routine=self.routine_b, state=0)

        self._bulk_assign(assignment_date=future_date, routine=self.routine_a)

        response = self.client.get(
            "/api/data/general-routine-assignments/week-summary/",
            {"start_date": start_of_week.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target_day = next(day for day in response.data["days"] if day["date"] == future_date.isoformat())
        self.assertEqual(target_day["centers_count"], 2)
        self.assertEqual(target_day["rooms_count"], 2)
        self.assertEqual(target_day["assigned_centers_count"], 2)
        self.assertEqual(target_day["assigned_rooms_count"], 2)
        self.assertEqual(target_day["sessions_count"], 2)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_general_bulk_assign_preserves_existing_room_override_by_default(self):
        future_date = timezone.localdate() + timedelta(days=3)
        old_general = GeneralRoutineAssignment.objects.create(
            date=future_date,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        room_override = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center_a,
            room=self.room_a,
            routine=self.routine_b,
            general_routine_assignment=old_general,
            overrides_general_assignment=True,
            created_by=self.user,
            updated_by=self.user,
        )
        self._make_session(room=self.room_a, session_date=future_date, routine=self.routine_b, state=0)
        self._make_session(room=self.room_b, session_date=future_date, routine=self.routine_a, state=0)

        response = self._bulk_assign(assignment_date=future_date, routine=self.routine_c, overwrite_room_overrides=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room_override.refresh_from_db()
        center_b_assignment = DailyRoutineAssignment.objects.get(date=future_date, room=self.room_b)

        self.assertEqual(room_override.routine_id, self.routine_b.id)
        self.assertTrue(room_override.overrides_general_assignment)
        self.assertEqual(room_override.general_routine_assignment.routine_id, self.routine_c.id)
        self.assertEqual(center_b_assignment.routine_id, self.routine_c.id)
        self.assertFalse(center_b_assignment.overrides_general_assignment)
        self.assertEqual(response.data["preserved_room_overrides"], 1)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_general_bulk_assign_can_overwrite_existing_room_override(self):
        future_date = timezone.localdate() + timedelta(days=4)
        old_general = GeneralRoutineAssignment.objects.create(
            date=future_date,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        room_override = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center_a,
            room=self.room_a,
            routine=self.routine_b,
            general_routine_assignment=old_general,
            overrides_general_assignment=True,
            created_by=self.user,
            updated_by=self.user,
        )
        session = self._make_session(room=self.room_a, session_date=future_date, routine=self.routine_b, state=0)

        response = self._bulk_assign(assignment_date=future_date, routine=self.routine_c, overwrite_room_overrides=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room_override.refresh_from_db()
        session.refresh_from_db()

        self.assertEqual(room_override.routine_id, self.routine_c.id)
        self.assertFalse(room_override.overrides_general_assignment)
        self.assertEqual(session.routine_id, self.routine_c.id)
        self.assertEqual(response.data["preserved_room_overrides"], 0)

    @override_settings(ALLOW_PAST_DAILY_ASSIGNMENTS=False)
    def test_delete_general_assignment_deactivates_inherited_assignments_and_preserves_room_overrides(self):
        future_date = timezone.localdate() + timedelta(days=5)
        general_assignment = GeneralRoutineAssignment.objects.create(
            date=future_date,
            routine=self.routine_a,
            created_by=self.user,
            updated_by=self.user,
        )
        inherited_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center_a,
            room=self.room_a,
            routine=self.routine_a,
            general_routine_assignment=general_assignment,
            overrides_general_assignment=False,
            created_by=self.user,
            updated_by=self.user,
        )
        override_assignment = DailyRoutineAssignment.objects.create(
            date=future_date,
            center=self.center_b,
            room=self.room_b,
            routine=self.routine_b,
            general_routine_assignment=general_assignment,
            overrides_general_assignment=True,
            created_by=self.user,
            updated_by=self.user,
        )
        inherited_session = self._make_session(
            room=self.room_a,
            session_date=future_date,
            routine=self.routine_a,
            state=0,
            daily_routine_assignment=inherited_assignment,
            routine_manually_overridden=False,
        )
        manual_session = self._make_session(
            room=self.room_a,
            session_date=future_date,
            session_time=time(10, 0),
            routine=self.routine_c,
            state=0,
            daily_routine_assignment=inherited_assignment,
            routine_manually_overridden=True,
        )

        response = self.client.delete(f"/api/data/general-routine-assignments/{general_assignment.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        general_assignment.refresh_from_db()
        inherited_assignment.refresh_from_db()
        override_assignment.refresh_from_db()
        inherited_session.refresh_from_db()
        manual_session.refresh_from_db()

        self.assertFalse(general_assignment.active)
        self.assertFalse(inherited_assignment.active)
        self.assertEqual(override_assignment.routine_id, self.routine_b.id)
        self.assertIsNone(override_assignment.general_routine_assignment)
        self.assertFalse(override_assignment.overrides_general_assignment)
        self.assertIsNone(inherited_session.routine)
        self.assertIsNone(inherited_session.daily_routine_assignment)
        self.assertEqual(manual_session.routine_id, self.routine_c.id)
        self.assertIsNone(manual_session.daily_routine_assignment)

    def test_patch_rejects_routine_change_for_past_session(self):
        past_date = timezone.localdate() - timedelta(days=1)
        session = self._make_session(
            room=self.room_a,
            session_date=past_date,
            state=0,
            user=self.user,
        )

        response = self.client.patch(
            f"/api/data/routinesessions/{session.id}/",
            {"routine_id": self.routine_b.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        self.assertEqual(session.routine_id, self.routine_a.id)
