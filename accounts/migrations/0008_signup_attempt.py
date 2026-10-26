import django_mongodb_backend.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_suspension_activation_snapshot")]

    operations = [
        migrations.CreateModel(
            name="SignupAttempt",
            fields=[
                ("id", django_mongodb_backend.fields.ObjectIdAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reserved_user_id", django_mongodb_backend.fields.ObjectIdField(unique=True)),
                ("application_id", django_mongodb_backend.fields.ObjectIdField(unique=True)),
                ("channel", models.CharField(choices=[("password", "Password"), ("google", "Google")], max_length=20)),
                ("username", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254)),
                ("statement", models.TextField()),
                ("google_subject", models.CharField(blank=True, default="", max_length=255)),
                ("state", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("compensated", "Compensated")], default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
