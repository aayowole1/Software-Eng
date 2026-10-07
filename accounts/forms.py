from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import Role

User = get_user_model()


class RegisterForm(forms.Form):
    # No "@" allowed, so a username can never look like someone else's email
    # (sign-in accepts either; see accounts.backends).
    username = forms.RegexField(
        label="Username",
        max_length=150,
        regex=r"^[A-Za-z0-9._-]+$",
        error_messages={"invalid": "Use only letters, numbers, and . _ -"},
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        # Case-insensitive so "Ada" and "ada" can't both exist.
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # Older accounts used their email as the username, so check both fields.
        if (
            User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and password != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        if password and cleaned.get("email") and cleaned.get("username"):
            try:
                # Django's validators enforce >= 8 characters, not too common,
                # not all numeric, and not too similar to the username or email.
                password_validation.validate_password(
                    password, User(username=cleaned["username"], email=cleaned["email"])
                )
            except forms.ValidationError as err:
                self.add_error("password", err)
        return cleaned

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
        )


class EmailLoginForm(AuthenticationForm):
    # Matched against username or email by accounts.backends.EmailOrUsernameBackend.
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )


class RoleForm(forms.Form):
    role = forms.ChoiceField(label="Role", choices=Role.choices)
