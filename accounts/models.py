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
from django.core.exceptions import ValidationError
from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)

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


def set_role(user, role):
    """Change a role without contradicting Django's superuser authority."""
    if role not in Role.values:
        raise ValueError(f"Invalid role: {role}")
    if user.is_superuser and role != Role.ADMIN:
        raise ValueError("Superusers must remain admins.")
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.role = role
    profile.save(update_fields=["role"])
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
