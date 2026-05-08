import re
from urllib.parse import urlparse

from django.core.management.base import BaseCommand

from core_data.models import Exercise


CODE_PATTERN = re.compile(r"^va[_\s.-]*(\d+)[_\s.-]+(\d+)", re.IGNORECASE)


def extract_code_from_video_url(video_url):
    if not video_url:
        return None

    filename = urlparse(video_url).path.rsplit("/", 1)[-1]
    filename_without_extension = filename.rsplit(".", 1)[0]
    match = CODE_PATTERN.match(filename_without_extension)

    if not match:
        return None

    return f"{match.group(1)}.{match.group(2)}"


class Command(BaseCommand):
    help = "Backfill Exercise.code from Cloudinary video URLs. Intended as a one-time manual command."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without saving changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        exercises = Exercise.objects.filter(code__isnull=True).exclude(video__isnull=True).exclude(video="")

        updated_count = 0
        skipped_count = 0

        for exercise in exercises.iterator():
            code = extract_code_from_video_url(exercise.video)

            if not code:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped exercise {exercise.id}: could not parse code from video URL"
                    )
                )
                continue

            updated_count += 1
            self.stdout.write(f"Exercise {exercise.id}: code={code}")

            if not dry_run:
                exercise.code = code
                exercise.save(update_fields=["code"])

        action = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {updated_count} exercises. Skipped {skipped_count} exercises."
            )
        )
