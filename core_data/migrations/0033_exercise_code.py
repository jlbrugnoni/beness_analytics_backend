# Generated manually because the local environment is missing cloudinary.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_data", "0032_dailyroutineassignment_routine_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="exercise",
            name="code",
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
    ]
