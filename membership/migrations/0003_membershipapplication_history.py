from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("membership", "0002_review_access_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipapplication",
            name="history",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Audit log of membership application events (submission and review).",
            ),
        ),
    ]
