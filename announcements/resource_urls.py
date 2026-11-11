from django.urls import path
from . import resource_views as views

app_name = "resources"
urlpatterns = [
    path("", views.resource_list, name="list"),
    path("create/", views.resource_edit, name="create"),
    path("<oid:pk>/edit/", views.resource_edit, name="edit"),
    path("<oid:pk>/delete/", views.resource_delete, name="delete"),
    path("<oid:pk>/open/", views.resource_open, name="open"),
]
