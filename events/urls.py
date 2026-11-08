from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("new/", views.event_create, name="create"),
    path("<oid:pk>/", views.event_detail, name="detail"),
    path("<oid:pk>/edit/", views.event_edit, name="edit"),
    path("<oid:pk>/cancel/", views.event_cancel, name="cancel"),
    path("<oid:pk>/rsvp/", views.event_rsvp, name="rsvp"),
    path("<oid:pk>/attendance/", views.event_attendance, name="attendance"),
]
