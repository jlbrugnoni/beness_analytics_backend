from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membershipmonthstatus",
            name="studio_inference_method",
            field=models.CharField(
                choices=[
                    ("purchase", "Membership Purchase"),
                    ("attendance_month", "Attendance in Month"),
                    ("recent_attendance", "Recent Attendance"),
                    ("previous_month", "Previous Month"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
                max_length=30,
            ),
        ),
    ]
