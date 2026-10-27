"""
@brief      Define the URL paths for the announcements module.

@citation   Code written with aid of Google Stitch.
"""

# === IMPORTS
from django.urls import path

from . import views


app_name = "announcements"

# === URL PATTERNS
urlpatterns = [
    path("", views.announcements_list, name="list"),
    # Management routes:
    path("create/", views.announcement_create, name="create"),
    path("<oid:pk>/edit/", views.announcement_edit, name="edit"),
    path("<oid:pk>/", views.announcement_detail, name="detail"),
    path("<oid:pk>/read/", views.announcement_mark_read, name="mark_read"),
]
