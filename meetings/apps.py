from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "meetings"
