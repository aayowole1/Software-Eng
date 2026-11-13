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
    path(
        "attachments/<str:pk>/download/",
        views.announcement_attachment_download,
        name="attachment_download",
    ),
    path("<str:pk>/edit/", views.announcement_edit, name="edit"),
    path("<str:pk>/delete/", views.announcement_delete, name="delete"),
    path("<str:pk>/read/", views.announcement_mark_read, name="mark_read"),
    path("<str:pk>/comments/", views.announcement_comment_create, name="comment_create"),
    path(
        "<str:pk>/comments/<str:comment_pk>/delete/",
        views.announcement_comment_delete,
        name="comment_delete",
    ),
    path(
        "<str:pk>/comments/<str:comment_pk>/moderate/",
        views.announcement_comment_moderate,
        name="comment_moderate",
    ),
    path("<str:pk>/", views.announcement_detail, name="detail"),
]
