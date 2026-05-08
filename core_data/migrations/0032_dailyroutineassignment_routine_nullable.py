from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core_data", "0031_generalroutineassignment_dailyassignment_general_link"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailyroutineassignment",
            name="routine",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="daily_assignments",
                to="core_data.routine",
            ),
        ),
    ]
