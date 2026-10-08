"""Make accounts that predate the accounts app visible in role management."""

from django.conf import settings
from django.db import migrations


def backfill_profiles(apps, schema_editor):
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)
    Profile = apps.get_model("accounts", "Profile")
    alias = schema_editor.connection.alias
    for user in User.objects.using(alias).all().iterator():
        Profile.objects.using(alias).get_or_create(
            user_id=user.pk,
            defaults={"role": "admin" if user.is_superuser else "applicant"},
        )


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunPython(backfill_profiles, migrations.RunPython.noop)]
