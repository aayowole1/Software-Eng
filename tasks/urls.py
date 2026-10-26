from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.task_list, name="list"),
    path("new/", views.task_create, name="create"),
    path("assignees/", views.assignees, name="assignees"),
    path("from-meeting/<oid:pk>/", views.import_draft, name="import_draft"),
    path("<oid:pk>/", views.task_detail, name="detail"),
    path("<oid:pk>/edit/", views.task_edit, name="edit"),
    path("<oid:pk>/status/", views.task_update_status, name="update_status"),
    path("<oid:pk>/claim/", views.task_claim, name="claim"),
]
