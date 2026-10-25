from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm

from membership.models import MembershipApplication, inactive_account_message

from .backends import find_user
from .models import Role

User = get_user_model()


def application_statement_field():
    """The membership application question asked at sign-up."""
    return forms.CharField(
        label="Why do you want to join?",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="This is your membership application. An officer reviews it before you can sign in.",
    )


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
    statement = application_statement_field()

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
        """Create a switched-off account plus its membership application."""
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            is_active=False,
        )
        try:
            MembershipApplication.objects.create(user=user, statement=self.cleaned_data["statement"])
        except Exception:
            # Don't leave an account behind that has no application to approve.
            user.delete()
            raise
        return user


class EmailLoginForm(AuthenticationForm):
    # Matched against username or email by accounts.backends.EmailOrUsernameBackend.
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            # Accounts waiting on (or refused) membership can't sign in. Say why,
            # but only to someone who knows the password, so the message can't
            # be used to find out who has applied.
            user = find_user(self.cleaned_data.get("username"))
            password = self.cleaned_data.get("password")
            if user is not None and not user.is_active and password and user.check_password(password):
                raise forms.ValidationError(inactive_account_message(user), code="inactive")
            raise


class GoogleApplicationForm(forms.Form):
    statement = application_statement_field()


class RoleForm(forms.Form):
    role = forms.ChoiceField(label="Role", choices=Role.choices)


class SuspensionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ("suspend", "Suspend"),
            ("reinstate", "Reinstate"),
        ]
    )
