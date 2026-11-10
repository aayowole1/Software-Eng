from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_attendanceauditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceauditlog",
            name="change_key",
            field=models.CharField(
                blank=True,
                help_text="Stable idempotency token: 'mark:<attendance_pk>' or 'unmark:<attendance_pk>'.",
                max_length=150,
                null=True,
                unique=True,
            ),
        ),
    ]
