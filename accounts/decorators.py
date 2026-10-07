from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import get_role, has_minimum_role


def role_required(min_role):
    """Allow a view only for signed-in users whose role is at least `min_role`.

    Signed-out users are redirected to the login page; signed-in users without
    the required role get HTTP 403 (NFR-02).

    Usage:
        @role_required(Role.OFFICER)
        def approve_application(request, pk): ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_minimum_role(get_role(request.user), min_role):
                raise PermissionDenied(f"Requires role: {min_role}")
            return view_func(request, *args, **kwargs)

        return login_required(wrapped)

    return decorator
