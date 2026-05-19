from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core_data.models import ExpectedClassSlot, ScheduledClass


def parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def schedule_status_for_expected_slot(expected_slot):
    if expected_slot.status == ExpectedClassSlot.STATUS_MATCHED:
        return ScheduledClass.SCHEDULE_STATUS_MATCHED
    if expected_slot.status in [
        ExpectedClassSlot.STATUS_MISSING,
        ExpectedClassSlot.STATUS_MANUALLY_CREATED,
        ExpectedClassSlot.STATUS_PENDING,
    ]:
        return ScheduledClass.SCHEDULE_STATUS_MISSING_FROM_REPORT
    return ScheduledClass.SCHEDULE_STATUS_MANUAL


def notes_for_expected_slot(expected_slot):
    if expected_slot.status == ExpectedClassSlot.STATUS_MATCHED:
        return "Migrated from matched expected schedule slot."
    if expected_slot.status == ExpectedClassSlot.STATUS_MANUALLY_CREATED:
        return "Migrated from manually-created expected schedule slot."
    if expected_slot.status == ExpectedClassSlot.STATUS_MISSING:
        return "Migrated from missing expected schedule slot."
    return "Migrated from expected schedule slot."


class Command(BaseCommand):
    help = "Backfills ScheduledClass reconciliation fields from ExpectedClassSlot rows."

    def add_arguments(self, parser):
        parser.add_argument("--site", type=int, help="Limit migration to one site id.")
        parser.add_argument("--studio", type=int, help="Limit migration to one studio id.")
        parser.add_argument("--date-from", help="Limit migration to expected slots on or after this date.")
        parser.add_argument("--date-to", help="Limit migration to expected slots on or before this date.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")

    def handle(self, *args, **options):
        date_from = parse_iso_date(options.get("date_from"))
        date_to = parse_iso_date(options.get("date_to"))
        if options.get("date_from") and not date_from:
            raise CommandError("--date-from must be YYYY-MM-DD.")
        if options.get("date_to") and not date_to:
            raise CommandError("--date-to must be YYYY-MM-DD.")
        if date_from and date_to and date_to < date_from:
            raise CommandError("--date-to must be after --date-from.")

        queryset = ExpectedClassSlot.objects.select_related(
            "site",
            "studio",
            "room",
            "template",
            "scheduled_class",
            "staff_member",
        ).all()
        if options.get("site"):
            queryset = queryset.filter(site_id=options["site"])
        if options.get("studio"):
            queryset = queryset.filter(studio_id=options["studio"])
        if date_from:
            queryset = queryset.filter(slot_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(slot_date__lte=date_to)

        dry_run = options["dry_run"]
        stats = {
            "expected_slots_checked": 0,
            "scheduled_classes_updated": 0,
            "scheduled_classes_created": 0,
            "existing_expected_classes_reused": 0,
            "skipped_without_template": 0,
        }

        with transaction.atomic():
            for expected_slot in queryset.iterator():
                stats["expected_slots_checked"] += 1
                if not expected_slot.template_id:
                    stats["skipped_without_template"] += 1
                    continue

                scheduled_class = expected_slot.scheduled_class
                if not scheduled_class:
                    scheduled_class = (
                        ScheduledClass.objects.filter(
                            site=expected_slot.site,
                            studio=expected_slot.studio,
                            room=expected_slot.room,
                            template=expected_slot.template,
                            class_date=expected_slot.slot_date,
                            start_time=expected_slot.start_time,
                            source=ScheduledClass.SOURCE_EXPECTED_TEMPLATE,
                        )
                        .exclude(status=ScheduledClass.STATUS_CANCELLED)
                        .first()
                    )
                    if scheduled_class:
                        stats["existing_expected_classes_reused"] += 1

                if scheduled_class:
                    stats["scheduled_classes_updated"] += 1
                    if dry_run:
                        continue
                    scheduled_class.template = expected_slot.template
                    scheduled_class.expected_from_template = True
                    scheduled_class.schedule_status = schedule_status_for_expected_slot(expected_slot)
                    scheduled_class.reconciled_at = timezone.now()
                    scheduled_class.reconciliation_notes = notes_for_expected_slot(expected_slot)
                    scheduled_class.save(update_fields=[
                        "template",
                        "expected_from_template",
                        "schedule_status",
                        "reconciled_at",
                        "reconciliation_notes",
                        "updated_at",
                    ])
                    if not expected_slot.scheduled_class_id:
                        expected_slot.scheduled_class = scheduled_class
                        expected_slot.save(update_fields=["scheduled_class", "updated_at"])
                    continue

                stats["scheduled_classes_created"] += 1
                if dry_run:
                    continue
                scheduled_class = ScheduledClass.objects.create(
                    site=expected_slot.site,
                    studio=expected_slot.studio,
                    room=expected_slot.room,
                    staff_member=expected_slot.staff_member,
                    template=expected_slot.template,
                    name=expected_slot.name,
                    class_date=expected_slot.slot_date,
                    start_time=expected_slot.start_time,
                    end_time=expected_slot.end_time,
                    session_type=ScheduledClass.SESSION_TYPE_GROUP,
                    capacity=expected_slot.capacity,
                    status=ScheduledClass.STATUS_SCHEDULED,
                    reason="Created while migrating expected schedule slots.",
                    source=ScheduledClass.SOURCE_EXPECTED_TEMPLATE,
                    expected_from_template=True,
                    schedule_status=schedule_status_for_expected_slot(expected_slot),
                    reconciled_at=timezone.now(),
                    reconciliation_notes=notes_for_expected_slot(expected_slot),
                )
                expected_slot.scheduled_class = scheduled_class
                expected_slot.save(update_fields=["scheduled_class", "updated_at"])

            if dry_run:
                transaction.set_rollback(True)

        mode = "DRY RUN" if dry_run else "MIGRATED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: {stats}"))
