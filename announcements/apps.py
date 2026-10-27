from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "announcements"
