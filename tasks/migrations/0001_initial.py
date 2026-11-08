import django.db.models.deletion
import django_mongodb_backend.fields
import tasks.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0004_profile_is_suspended"),
        ("committees", "0001_initial"),
        ("meetings", "0001_initial"),
        ("membership", "0002_review_access_pending"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", django_mongodb_backend.fields.ObjectIdAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("status", models.CharField(choices=[("todo", "To do"), ("in_progress", "In progress"), ("done", "Done")], default="todo", max_length=20)),
                ("version", models.PositiveIntegerField(default=0)),
                ("history", models.JSONField(blank=True, default=list)),
                ("origin_key", models.CharField(default=tasks.models.manual_origin_key, editable=False, max_length=100, unique=True)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tasks", to=settings.AUTH_USER_MODEL)),
                ("committee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="committees.committee")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_tasks", to=settings.AUTH_USER_MODEL)),
                ("source_action_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imported_tasks", to="meetings.actionitem")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
