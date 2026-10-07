from django.apps import AppConfig


class CommitteesConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "committees"
