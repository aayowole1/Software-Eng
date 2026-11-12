"""Use the shared current-account rules for announcement access."""

from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from accounts.backends import EmailOrUsernameBackend
from accounts.models import Profile, Role, has_minimum_role
from membership.models import MembershipApplication
from committees.models import CommitteeMember
from .models import Announcement


def effective_role(user):
    if not user.is_authenticated:
        return None
    current = get_user_model().objects.filter(pk=user.pk).first()
    if current is None:
        return None
    if current.is_superuser:
        return Role.ADMIN
    if not EmailOrUsernameBackend().user_can_authenticate(current):
        return None
    if current.is_staff or current.groups.filter(name="Officer").exists():
        return None
    profile = Profile.objects.filter(user_id=current.pk).first()
    if (
        profile is None
        or profile.is_suspended
        or profile.suspension_update_pending
        or MembershipApplication.objects.filter(
            user_id=current.pk,
            access_update_pending=True,
        ).exists()
    ):
        return None
    return profile.role


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


def visible_announcements(user, role):
    """Return announcements visible to the current account."""
    if has_minimum_role(role, Role.OFFICER):
        return Announcement.objects.all()
    if not has_minimum_role(role, Role.MEMBER):
        return Announcement.objects.none()
    committee_ids = list(
        CommitteeMember.objects.filter(user_id=user.pk).values_list("committee_id", flat=True)
    )
    return Announcement.objects.filter(
        status="published",
    ).filter(
        Q(committee_id__isnull=True) | Q(committee_id__in=committee_ids),
    )
