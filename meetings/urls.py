from django.urls import path

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.draft_list, name="list"),
    path("new/", views.draft_create, name="create"),
    path("new/processing/start/", views.meeting_processing, name="processing_start"),
    path("new/processing/", views.meeting_processing_page, name="processing"),
    path("new/process/", views.meeting_process, name="process"),
    path("transcribe/", views.transcribe_chunk, name="transcribe"),
    path("<oid:pk>/", views.draft_detail, name="detail"),
    path("<oid:pk>/review/", views.draft_review, name="review"),
    path("<oid:pk>/finish-review/", views.draft_finish_review, name="finish_review"),
    path("<oid:pk>/revise/", views.draft_revise, name="revise"),
    path("<oid:pk>/delete/", views.draft_delete, name="delete"),
]
