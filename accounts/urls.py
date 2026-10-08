from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views
from .google_auth import google_signin

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("google/", google_signin, name="google_signin"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", views.profile, name="profile"),
    path("users/", views.user_list, name="user_list"),
    path("users/<oid:pk>/role/", views.change_role, name="change_role"),
]
