from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ScheduledClass, WeeklyRoomTemplate


def minutes_since_midnight(value):
    return value.hour * 60 + value.minute


def duration_difference_minutes(start_a, end_a, start_b, end_b):
    duration_a = minutes_since_midnight(end_a) - minutes_since_midnight(start_a)
    duration_b = minutes_since_midnight(end_b) - minutes_since_midnight(start_b)
    return abs(duration_a - duration_b)


def find_detected_class_for_template(template, slot_date):
    candidates = ScheduledClass.objects.filter(
        site=template.site,
        studio=template.studio,
        room=template.room,
        class_date=slot_date,
        start_time=template.start_time,
        source=ScheduledClass.SOURCE_TRAINER_AVAILABILITY,
    ).exclude(status=ScheduledClass.STATUS_CANCELLED)
    candidates = [
        candidate for candidate in candidates
        if duration_difference_minutes(
            template.start_time,
            template.end_time,
            candidate.start_time,
            candidate.end_time,
        ) <= 15
    ]
    if template.staff_member_id:
        exact = next((candidate for candidate in candidates if candidate.staff_member_id == template.staff_member_id), None)
        if exact:
            return exact
    if len(candidates) == 1:
        return candidates[0]
    return None


def find_existing_expected_class_for_template(template, slot_date):
    return (
        ScheduledClass.objects.filter(
            site=template.site,
            studio=template.studio,
            room=template.room,
            class_date=slot_date,
            start_time=template.start_time,
            end_time=template.end_time,
            source__in=[
                ScheduledClass.SOURCE_EXPECTED_TEMPLATE,
                ScheduledClass.SOURCE_MANUAL,
            ],
        )
        .exclude(status=ScheduledClass.STATUS_CANCELLED)
        .order_by("-template_id", "id")
        .first()
    )


def update_class_reconciliation(scheduled_class, *, template, schedule_status, notes):
    scheduled_class.template = template
    scheduled_class.expected_from_template = template is not None
    scheduled_class.schedule_status = schedule_status
    scheduled_class.reconciled_at = timezone.now()
    scheduled_class.reconciliation_notes = notes
    scheduled_class.save(update_fields=[
        "template",
        "expected_from_template",
        "schedule_status",
        "reconciled_at",
        "reconciliation_notes",
        "updated_at",
    ])


def create_expected_scheduled_class(template, slot_date):
    scheduled_class = ScheduledClass.objects.create(
        site=template.site,
        studio=template.studio,
        room=template.room,
        staff_member=template.staff_member,
        template=template,
        name=template.name,
        class_date=slot_date,
        start_time=template.start_time,
        end_time=template.end_time,
        session_type=ScheduledClass.SESSION_TYPE_GROUP,
        capacity=template.capacity,
        status=ScheduledClass.STATUS_SCHEDULED,
        reason="Created from expected weekly schedule.",
        source=ScheduledClass.SOURCE_EXPECTED_TEMPLATE,
        manually_modified=False,
        expected_from_template=True,
        schedule_status=ScheduledClass.SCHEDULE_STATUS_MISSING_FROM_REPORT,
        reconciled_at=timezone.now(),
        reconciliation_notes="Expected class was not found in Trainer Availability report.",
    )
    return scheduled_class


@transaction.atomic
def reconcile_scheduled_classes_from_templates(site_id=None, studio_id=None, room_id=None, date_from=None, date_to=None):
    templates = WeeklyRoomTemplate.objects.select_related("site", "studio", "room", "staff_member").filter(active=True)
    if site_id:
        templates = templates.filter(site_id=site_id)
    if studio_id:
        templates = templates.filter(studio_id=studio_id)
    if room_id:
        templates = templates.filter(room_id=room_id)

    detected_classes = ScheduledClass.objects.filter(
        class_date__range=(date_from, date_to),
        source=ScheduledClass.SOURCE_TRAINER_AVAILABILITY,
    ).exclude(status=ScheduledClass.STATUS_CANCELLED)
    if site_id:
        detected_classes = detected_classes.filter(site_id=site_id)
    if studio_id:
        detected_classes = detected_classes.filter(studio_id=studio_id)
    if room_id:
        detected_classes = detected_classes.filter(room_id=room_id)

    detected_ids = set(detected_classes.values_list("id", flat=True))
    matched_detected_ids = set()
    stats = {
        "templates_checked": 0,
        "classes_matched": 0,
        "missing_classes_created": 0,
        "missing_classes_existing": 0,
        "unexpected_classes": 0,
    }

    current_date = date_from
    while current_date <= date_to:
        for template in templates:
            if template.weekday != current_date.weekday():
                continue
            if template.active_from > current_date:
                continue
            if template.active_until and template.active_until < current_date:
                continue

            stats["templates_checked"] += 1
            detected_class = find_detected_class_for_template(template, current_date)
            if detected_class:
                update_class_reconciliation(
                    detected_class,
                    template=template,
                    schedule_status=ScheduledClass.SCHEDULE_STATUS_MATCHED,
                    notes="Matched to weekly room template during schedule reconciliation.",
                )
                matched_detected_ids.add(detected_class.id)
                stats["classes_matched"] += 1
                continue

            expected_class = find_existing_expected_class_for_template(template, current_date)
            if expected_class:
                update_class_reconciliation(
                    expected_class,
                    template=template,
                    schedule_status=ScheduledClass.SCHEDULE_STATUS_MISSING_FROM_REPORT,
                    notes="Expected class still missing from Trainer Availability report.",
                )
                stats["missing_classes_existing"] += 1
            else:
                create_expected_scheduled_class(template, current_date)
                stats["missing_classes_created"] += 1
        current_date += timedelta(days=1)

    unexpected_ids = detected_ids - matched_detected_ids
    if unexpected_ids:
        stats["unexpected_classes"] = ScheduledClass.objects.filter(id__in=unexpected_ids).update(
            template=None,
            expected_from_template=False,
            schedule_status=ScheduledClass.SCHEDULE_STATUS_UNEXPECTED_FROM_REPORT,
            reconciled_at=timezone.now(),
            reconciliation_notes="Trainer Availability class did not match the weekly room template.",
            updated_at=timezone.now(),
        )

    return stats
