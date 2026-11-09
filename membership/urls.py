from django.urls import path

from . import views

app_name = "membership"

urlpatterns = [
    path("apply/", views.apply, name="apply"),
    path("apply/officer/", views.apply_for_officer, name="apply_for_officer"),
    path("applications/", views.application_list, name="application_list"),
    path("applications/<oid:pk>/review/", views.review_application, name="review_application"),
    path("applications/officer/<oid:pk>/review/", views.review_officer_application, name="review_officer_application"),
    path("applications/<oid:pk>/finish-access/", views.finish_review_access, name="finish_review_access"),
    path("roster/", views.roster, name="roster"),
    path("roster/<oid:pk>/", views.member_detail, name="member_detail"),
]
