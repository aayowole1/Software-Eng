from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with either a username or an email address.

    The username is tried first (exact match). Otherwise the value is treated
    as an email (case-insensitive); it only matches when exactly one account
    has that email, since Django doesn't force emails to be unique.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        identifier = username.strip()

        user = User.objects.filter(username=identifier).first()
        if user is None:
            matches = list(User.objects.filter(email__iexact=identifier)[:2])
            user = matches[0] if len(matches) == 1 else None

        if user is None:
            # Run the password hasher anyway so a missing account takes about
            # as long as a wrong password (same as Django's ModelBackend).
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
