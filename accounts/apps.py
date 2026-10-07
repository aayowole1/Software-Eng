from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "accounts"

    def ready(self):
        from . import signals  # noqa: F401
