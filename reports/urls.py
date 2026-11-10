from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report, name="report"),
    path("download/events/", views.report_csv_events, name="csv_events"),
    path("download/members/", views.report_csv_members, name="csv_members"),
    path("download/committees/", views.report_csv_committees, name="csv_committees"),
]
