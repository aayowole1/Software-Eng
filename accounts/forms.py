from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import Role

User = get_user_model()


class RegisterForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and password != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        if password and cleaned.get("email"):
            try:
                # Django's validators enforce >= 8 characters, not too common,
                # not all numeric, and not too similar to the email.
                password_validation.validate_password(
                    password, User(username=cleaned["email"], email=cleaned["email"])
                )
            except forms.ValidationError as err:
                self.add_error("password", err)
        return cleaned

    def save(self):
        email = self.cleaned_data["email"]
        # The email doubles as the username so people sign in with their email.
        return User.objects.create_user(
            username=email, email=email, password=self.cleaned_data["password"]
        )


class EmailLoginForm(AuthenticationForm):
    # Matched against username or email by accounts.backends.EmailOrUsernameBackend.
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )


class RoleForm(forms.Form):
    role = forms.ChoiceField(label="Role", choices=Role.choices)
