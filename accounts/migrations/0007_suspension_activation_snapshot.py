from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_canonical_account_identifiers")]

    operations = [
        migrations.AddField(
            model_name="profile", name="suspension_was_active",
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="profile", name="suspension_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile", name="suspension_restore_active",
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="profile", name="suspension_update_pending",
            field=models.BooleanField(default=False),
        ),
    ]
