from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report, name="report"),
    path("download/", views.report_csv, name="csv"),
]
