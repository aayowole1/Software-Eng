from django.urls import path

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.draft_list, name="list"),
    path("new/", views.draft_create, name="create"),
    path("transcribe/", views.transcribe_chunk, name="transcribe"),
    path("<oid:pk>/", views.draft_detail, name="detail"),
    path("<oid:pk>/review/", views.draft_review, name="review"),
    path("<oid:pk>/revise/", views.draft_revise, name="revise"),
    path("<oid:pk>/delete/", views.draft_delete, name="delete"),
]
