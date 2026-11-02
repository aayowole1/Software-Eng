from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("audit/", views.audit_history, name="audit_history"),
    path("health/", views.health, name="health"),
    path("health/ready/", views.readiness, name="readiness"),
]
