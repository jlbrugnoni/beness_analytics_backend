import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core_data.models import Site
from finance.configuration_presets.loader import install_preset


class Command(BaseCommand):
    help = "Install the configuration-only Beness Dominicana preset. Dry-run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--site", type=int, required=True, help="Existing Dominican Republic Site ID.")
        parser.add_argument("--actor", type=int, required=True, help="Active superuser ID for configuration audit.")
        parser.add_argument("--apply", action="store_true", help="Commit after all configuration checks succeed.")

    def handle(self, *args, **options):
        try:
            site = Site.objects.get(pk=options["site"])
            actor = get_user_model().objects.get(pk=options["actor"])
            counts = install_preset(site=site, actor=actor, apply=options["apply"])
        except (Site.DoesNotExist, get_user_model().DoesNotExist) as exc:
            raise CommandError("Select an existing site and active superuser.") from exc
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(("APPLIED" if options["apply"] else "DRY RUN — no settings saved") + "\n" +
                          json.dumps(counts, indent=2))
