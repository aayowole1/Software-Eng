"""
Organization roles (FR-01, NFR-02).

Each user has exactly one organization role, stored on a Profile linked to
Django's built-in User. Roles are ordered by privilege; a higher role has
every permission of the roles below it:

    applicant (1) < member (2) < officer (3) < admin (4)

New accounts start as applicants. An officer approves a membership
application to make someone a member; an admin can set any role.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Role(models.TextChoices):
    APPLICANT = "applicant", "Applicant"
    MEMBER = "member", "Member"
    OFFICER = "officer", "Officer"
    ADMIN = "admin", "Admin"


ROLE_LEVELS = {
    Role.APPLICANT: 1,
    Role.MEMBER: 2,
    Role.OFFICER: 3,
    Role.ADMIN: 4,
}

# Roles that count as part of the organization's roster.
ROSTER_ROLES = [Role.MEMBER, Role.OFFICER, Role.ADMIN]


def has_minimum_role(user_role, required_role):
    """Return True when `user_role` is at least as privileged as `required_role`."""
    user_level = ROLE_LEVELS.get(user_role, 0)
    required_level = ROLE_LEVELS.get(required_role, float("inf"))
    return user_level >= required_level


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.APPLICANT,
    )

    is_suspended = models.BooleanField(
        default=False,
        help_text="Administrative suspension independent of membership approval.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    role_version = models.PositiveIntegerField(default=0)
    role_history = models.JSONField(default=list, blank=True)
    suspension_was_active = models.BooleanField(default=None, null=True, blank=True)
    suspension_restore_active = models.BooleanField(default=None, null=True, blank=True)
    suspension_version = models.PositiveIntegerField(default=0)
    suspension_update_pending = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email or self.user.username} ({self.role})"

    def clean(self):
        super().clean()
        if self.user_id and self.user.is_superuser and self.role != Role.ADMIN:
            raise ValidationError({"role": "Superusers must remain admins."})


def get_role(user):
    """Return the organization role for `user`, or None when signed out.

    Django superusers are always treated as admins so the account created
    with `createsuperuser` can manage everything from the start.
    """
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.role


class RoleChangeConflict(ValueError):
    """A newer role or suspension update prevented this role change."""


class RoleChangeBlocked(ValueError):
    """Membership review must finish before an ordinary role change."""


def _membership_role_source(
    user, role, actor, source, membership_review, reconcile_rejected,
    expected_role, require_unsuspended,
):
    # Import at call time: membership uses the role writer for its promotion.
    from membership.models import ApplicationStatus, MembershipApplication

    unfinished = MembershipApplication.objects.filter(user_id=user.pk).filter(
        Q(status=ApplicationStatus.PENDING) | Q(access_update_pending=True)
    )
    if membership_review is not None:
        # A source string cannot authorize a bypass. Only the recorded approved
        # decision may perform its own conditional Applicant -> Member step.
        current = None
        if isinstance(membership_review, MembershipApplication):
            current = MembershipApplication.objects.filter(
                pk=membership_review.pk, user_id=user.pk,
                status=ApplicationStatus.APPROVED, access_update_pending=True,
            ).first()
        if (
            current is None or role != Role.MEMBER
            or expected_role != Role.APPLICANT or not require_unsuspended
            or current.reviewed_by_id != (actor.pk if actor is not None else None)
            or unfinished.exclude(pk=current.pk).exists()
        ):
            raise RoleChangeBlocked("This role update does not match an unfinished approved membership review.")
        return f"membership_review:{current.pk}"
    if not unfinished.exists():
        return source

    # Repair a legacy elevated rejected applicant without giving an officer
    # authority to demote an Officer/Admin or changing the recorded decision.
    actor_user = get_user_model().objects.filter(pk=actor.pk).first() if actor is not None else None
    actor_profile = Profile.objects.filter(user_id=actor_user.pk).first() if actor_user else None
    actor_is_admin = bool(
        actor_user and actor_user.is_active and actor_profile and not actor_profile.is_suspended
        and not actor_profile.suspension_update_pending
        and (actor_user.is_superuser or actor_profile.role == Role.ADMIN)
    )
    if (
        reconcile_rejected and role == Role.APPLICANT and actor_is_admin
        and actor_user.pk != user.pk and not user.is_superuser
        and not unfinished.exclude(status=ApplicationStatus.REJECTED, access_update_pending=True).exists()
    ):
        return "rejected_membership_reconciliation"
    raise RoleChangeBlocked(
        "Finish this account's membership review before changing its role. "
        "An administrator may restore Applicant only for a rejected review with unfinished account access."
    )


def set_role(
    user, role, actor=None, *, source="system", expected_version=None,
    expected_role=None, require_unsuspended=False, membership_review=None,
    reconcile_rejected=False,
):
    """Write a role and its history together in one conditional Profile update.

    This is an internal mutation API; callers authorize their workflow first.
    Legacy callers without an actor are recorded as System. Membership recovery
    can condition an Applicant promotion without demoting a newer Officer/Admin.
    """
    if role not in Role.values:
        raise ValueError(f"Invalid role: {role}")
    current_user = get_user_model().objects.get(pk=user.pk)
    if current_user.is_superuser and role != Role.ADMIN:
        raise ValueError("Superusers must remain admins.")
    if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
        raise ValueError("Invalid role version.")
    if expected_role is not None and expected_role not in Role.values:
        raise ValueError("Invalid expected role.")
    source = str(source or "system").strip()
    if not source or len(source) > 100:
        raise ValueError("Invalid role change source.")
    if actor is not None and (not getattr(actor, "is_authenticated", False) or actor.pk is None):
        raise ValueError("A role change actor must be a saved user or System.")
    source = _membership_role_source(
        current_user, role, actor, source, membership_review, reconcile_rejected,
        expected_role, require_unsuspended,
    )
    profile, _ = Profile.objects.get_or_create(user=user)
    if require_unsuspended and profile.is_suspended:
        raise ValueError("This account is administratively suspended and its role cannot be updated here.")
    if expected_role is not None and profile.role != expected_role:
        return profile
    # Retrying an acknowledged or unacknowledged successful write is a no-op.
    if profile.role == role:
        return profile
    version = profile.role_version or 0
    if expected_version is not None and version != expected_version:
        raise RoleChangeConflict("This account's role changed while you were editing. Reload before trying again.")
    entry = {
        "at": timezone.now().isoformat(),
        "actor_id": str(actor.pk) if actor is not None else None,
        "actor": actor.get_username() if actor is not None else "System",
        "old_role": str(profile.role),
        "new_role": str(role),
        "source": source,
    }
    eligible = Profile.objects.filter(pk=profile.pk, role=profile.role)
    if version == 0:
        # Also tolerate historical-model inserts that predate the migration.
        eligible = eligible.filter(Q(role_version=0) | Q(role_version__isnull=True))
    else:
        eligible = eligible.filter(role_version=version)
    if require_unsuspended:
        eligible = eligible.filter(is_suspended=False)
    changed = eligible.update(
        role=role, role_version=version + 1,
        role_history=[*(profile.role_history or []), entry],
    )
    if changed != 1:
        raise RoleChangeConflict("This account changed while its role was being updated. Reload before trying again.")
    profile.refresh_from_db()
    return profile


class GoogleIdentity(models.Model):
    """A verified Google subject linked to one local account, independent of email."""

    subject = models.CharField(max_length=255, unique=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_identity",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Google identity for {self.user}"
