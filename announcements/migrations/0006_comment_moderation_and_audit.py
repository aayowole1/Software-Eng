import django.db.models.deletion
import django_mongodb_backend.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("announcements", "0005_category_committee_and_comments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="announcementcomment",
            name="moderation_provider",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="announcementcomment",
            name="moderation_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="announcementcomment",
            name="moderation_status",
            field=models.CharField(
                choices=[("visible", "Visible"), ("flagged", "Flagged")],
                default="visible",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="AnnouncementCommentAudit",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("comment_id", models.CharField(max_length=32)),
                ("action", models.CharField(max_length=16)),
                ("content", models.TextField(max_length=2000)),
                ("detail", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "announcement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comment_audits", to="announcements.announcement",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
