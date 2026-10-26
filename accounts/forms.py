import logging

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db import DatabaseError

from membership.models import MembershipApplication, inactive_account_message

from .backends import find_user
from .models import Role
from .provisioning import complete_signup, is_identifier_conflict, record_signup_compensation, reserve_signup

User = get_user_model()
logger = logging.getLogger(__name__)


class PasswordSignupRetryError(Exception):
    """A safe, retryable failure while saving a password membership signup."""


class PasswordSignupConflictError(PasswordSignupRetryError):
    """The database identity constraint rejected a concurrent signup."""


def _cleanup_password_signup(user_id, username):
    """Compensate only this reserved attempt, including its related records."""
    try:
        User.objects.filter(pk=user_id, username=username).delete()
    except Exception:
        logger.error("An incomplete password signup could not be cleaned up; operator recovery is required.")


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
        username = self.cleaned_data["username"]
        attempt = None
        stage = "journal"
        try:
            # Persist ownership before create_user, including profile signals.
            # A process exit bypasses compensation but leaves this repair record.
            attempt = reserve_signup(
                "password", username, self.cleaned_data["email"], self.cleaned_data["statement"],
            )
            stage = "user"
            user = User.objects.create_user(
                pk=attempt.reserved_user_id,
                username=username,
                email=self.cleaned_data["email"],
                password=self.cleaned_data["password"],
                is_active=False,
            )
            stage = "application"
            MembershipApplication.objects.create(
                pk=attempt.application_id, user=user, statement=attempt.statement,
            )
            complete_signup(attempt)
        except DatabaseError as error:
            conflict = stage == "user" and is_identifier_conflict(error)
            if attempt is not None:
                _cleanup_password_signup(attempt.reserved_user_id, username)
                record_signup_compensation(attempt)
            if conflict:
                raise PasswordSignupConflictError("The username or email was claimed by another signup.") from error
            raise PasswordSignupRetryError(
                "Your application could not be saved right now. Please try submitting it again. "
                "Contact an officer if the problem continues."
            ) from error
        except Exception:
            if attempt is not None:
                _cleanup_password_signup(attempt.reserved_user_id, username)
                record_signup_compensation(attempt)
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
    version = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)


class SuspensionForm(forms.Form):
    version = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)
    action = forms.ChoiceField(
        choices=[
            ("suspend", "Suspend"),
            ("reinstate", "Reinstate"),
        ]
    )
