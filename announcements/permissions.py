"""Use the shared current-account rules for announcement access."""

from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.backends import EmailOrUsernameBackend
from accounts.models import Profile, Role, has_minimum_role


def effective_role(user):
    if not user.is_authenticated:
        return None
    current = get_user_model().objects.filter(pk=user.pk).first()
    if current is None or not EmailOrUsernameBackend().user_can_authenticate(current):
        return None
    if current.is_superuser:
        return Role.ADMIN
    profile = Profile.objects.filter(user_id=current.pk).first()
    return profile.role if profile else None


def announcement_access(minimum):
    def decorator(view):
        @wraps(view)
        def checked(request, *args, **kwargs):
            request.announcement_role = effective_role(request.user)
            if not has_minimum_role(request.announcement_role, minimum):
                raise PermissionDenied("You do not have access to announcements.")
            return view(request, *args, **kwargs)
        return login_required(checked)
    return decorator
