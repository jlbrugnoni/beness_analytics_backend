from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core_data.attendance_repair import repair_attendance_staff_duplicates


def parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class Command(BaseCommand):
    help = (
        "Merges duplicate attendance visits caused by instructor/staff changes "
        "between repeated attendance imports."
    )

    def add_arguments(self, parser):
        parser.add_argument("--site", type=int, help="Limit repair to one site id.")
        parser.add_argument("--studio", type=int, help="Limit repair to one visit studio id.")
        parser.add_argument("--date-from", help="Limit repair to visits on or after this date.")
        parser.add_argument("--date-to", help="Limit repair to visits on or before this date.")
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument(
            "--skip-metrics",
            action="store_true",
            help="Do not rebuild client monthly/weekly metrics for affected periods.",
        )

    def handle(self, *args, **options):
        date_from = parse_iso_date(options.get("date_from"))
        date_to = parse_iso_date(options.get("date_to"))
        if options.get("date_from") and not date_from:
            raise CommandError("--date-from must be YYYY-MM-DD.")
        if options.get("date_to") and not date_to:
            raise CommandError("--date-to must be YYYY-MM-DD.")
        if date_from and date_to and date_to < date_from:
            raise CommandError("--date-to must be after --date-from.")

        stats = repair_attendance_staff_duplicates(
            site_id=options.get("site"),
            studio_id=options.get("studio"),
            date_from=date_from,
            date_to=date_to,
            dry_run=options["dry_run"],
            rebuild_metrics=not options["skip_metrics"],
        )
        self.stdout.write(self.style.SUCCESS(str(stats)))
