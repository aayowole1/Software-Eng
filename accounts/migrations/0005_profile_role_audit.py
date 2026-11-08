from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_profile_is_suspended")]

    operations = [
        migrations.AddField(
            model_name="profile", name="role_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile", name="role_history",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
