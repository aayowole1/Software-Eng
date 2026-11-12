from django.apps import AppConfig


class OfficerApplicationsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "officer_applications"
