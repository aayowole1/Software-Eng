from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("meetings", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="meetingdraft", name="review_update_pending",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="meetingdraft", name="review_item_intent",
            field=models.JSONField(blank=True, default=None, editable=False, null=True),
        ),
    ]
