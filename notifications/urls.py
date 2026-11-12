from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<oid:pk>/read/", views.notification_read, name="read"),
    path("mark-all-read/", views.mark_all_read, name="mark_all_read"),
]
