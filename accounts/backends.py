from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import Profile


def find_user(identifier):
    """Return the account matching a username or email, or None.

    The username is tried first (exact match). Otherwise the value is treated
    as an email (case-insensitive); it only matches when exactly one account
    has that email, since Django doesn't force emails to be unique.
    """
    if not identifier:
        return None
    User = get_user_model()
    identifier = identifier.strip()
    user = User.objects.filter(username=identifier).first()
    if user is None:
        matches = list(User.objects.filter(email__iexact=identifier)[:2])
        user = matches[0] if len(matches) == 1 else None
    return user


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with either a username or an email address (see `find_user`)."""

    def user_can_authenticate(self, user):
        from membership.models import MembershipApplication

        # Suspension and activation are separate documents on MongoDB. Check
        # both so a partial suspension write also invalidates existing sessions.
        return (
            super().user_can_authenticate(user)
            and not Profile.objects.filter(user_id=user.pk, is_suspended=True).exists()
            and not MembershipApplication.objects.filter(
                user_id=user.pk, access_update_pending=True
            ).exists()
        )

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user = find_user(username)
        if user is None:
            # Run the password hasher anyway so a missing account takes about
            # as long as a wrong password (same as Django's ModelBackend).
            get_user_model()().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
