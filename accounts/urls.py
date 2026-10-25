from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy

from . import views
from .google_auth import google_apply, google_signin

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("google/", google_signin, name="google_signin"),
    path("google/apply/", google_apply, name="google_apply"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", views.profile, name="profile"),
    path("users/", views.user_list, name="user_list"),
    path("users/<oid:pk>/role/", views.change_role, name="change_role"),
    # Forgot password (Django's built-in reset flow). Accounts without a
    # usable password (Google sign-in) or not yet approved never get an email.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("users/<oid:pk>/suspension/", views.change_suspension, name="change_suspension"),
]
