from django.apps import AppConfig


class MembershipConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "membership"
