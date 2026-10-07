from django.urls import path

from . import views

app_name = "membership"

urlpatterns = [
    path("apply/", views.apply, name="apply"),
    path("applications/", views.application_list, name="application_list"),
    path("applications/<oid:pk>/review/", views.review_application, name="review_application"),
    path("roster/", views.roster, name="roster"),
]
