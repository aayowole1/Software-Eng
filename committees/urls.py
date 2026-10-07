from django.urls import path

from . import views

app_name = "committees"

urlpatterns = [
    path("", views.committee_list, name="list"),
    path("new/", views.committee_create, name="create"),
    path("<oid:pk>/", views.committee_detail, name="detail"),
    path("<oid:pk>/delete/", views.committee_delete, name="delete"),
    path("<oid:pk>/members/", views.add_member, name="add_member"),
    path("<oid:pk>/members/<oid:user_pk>/remove/", views.remove_member, name="remove_member"),
]
