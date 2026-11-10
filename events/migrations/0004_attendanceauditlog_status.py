import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Separate pending removals from completed changes and keep the original time.

    Existing entries were written as completed changes, so they get the
    completed status.
    """

    dependencies = [
        ("events", "0003_attendanceauditlog_change_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceauditlog",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("completed", "Completed")],
                default="completed",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="attendanceauditlog",
            name="at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
