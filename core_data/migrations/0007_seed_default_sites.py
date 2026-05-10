from django.db import migrations


def seed_default_sites(apps, schema_editor):
    Site = apps.get_model("core_data", "Site")
    defaults = [
        {"name": "Dominican Republic", "country_code": "DO"},
        {"name": "Spain", "country_code": "ES"},
    ]

    for site in defaults:
        Site.objects.get_or_create(
            country_code=site["country_code"],
            name=site["name"],
            defaults={"active": True},
        )


def unseed_default_sites(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core_data", "0006_client_first_name_client_last_name_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_default_sites, unseed_default_sites),
    ]
