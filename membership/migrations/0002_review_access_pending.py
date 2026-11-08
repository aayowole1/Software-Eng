from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("membership", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="membershipapplication",
            name="access_update_pending",
            field=models.BooleanField(
                default=False,
                help_text="A recorded review still needs its account access update completed.",
            ),
        ),
    ]
