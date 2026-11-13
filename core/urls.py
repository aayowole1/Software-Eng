from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("audit/", views.audit_history, name="audit_history"),
    path("help/", views.help_page, name="help"),
    path("about/", views.public_info_page, {"page": "about"}, name="about"),
    path("accessibility/", views.public_info_page, {"page": "accessibility"}, name="accessibility"),
    path("bylaws/", views.public_info_page, {"page": "bylaws"}, name="bylaws"),
    path("privacy/", views.public_info_page, {"page": "privacy"}, name="privacy"),
    path("health/", views.health, name="health"),
    path("health/ready/", views.readiness, name="readiness"),
]
