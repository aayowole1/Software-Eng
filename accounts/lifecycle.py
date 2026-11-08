"""Bounded suspension recovery across standalone MongoDB documents.

The view authorizes the acting Admin. Profile fields preserve the original
activation and unfinished intent; role changes use their independent CAS fields.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Profile


class SuspensionConflict(ValueError):
    """A newer lifecycle action owns the account's current suspension state."""


def _versioned(profile):
    rows = Profile.objects.filter(pk=profile.pk)
    version = profile.suspension_version or 0
    if version == 0:
        return rows.filter(Q(suspension_version=0) | Q(suspension_version__isnull=True))
    return rows.filter(suspension_version=version)


def _current_operation(profile):
    return _versioned(profile).filter(
        is_suspended=profile.is_suspended, suspension_update_pending=True,
    )


def _check_operation(profile):
    if not _current_operation(profile).exists():
        raise SuspensionConflict("This account's suspension changed. Reload before trying again.")


def _restore_membership_access(profile, user):
    from membership.models import ApplicationStatus, MembershipApplication

    unfinished = list(MembershipApplication.objects.filter(
        user_id=user.pk, access_update_pending=True,
    ).order_by("submitted_at"))
    if unfinished:
        # Persist the review's activation intent before it clears its own flag.
        # A later lifecycle retry must not mistake the pre-review inactive
        # snapshot for a reason to undo a successfully finalized review.
        if _current_operation(profile).update(suspension_restore_active=True) != 1:
            raise SuspensionConflict("This account's suspension changed. Reload before trying again.")
        profile.suspension_restore_active = True
    for application in unfinished:
        _check_operation(profile)
        # This re-reads the recorded decision and uses its original reviewer.
        # It never substitutes the Admin who removed the suspension.
        application.complete_access_update(suspension_version=profile.suspension_version)
    _check_operation(profile)
    user.refresh_from_db()
    if MembershipApplication.objects.filter(user_id=user.pk, status=ApplicationStatus.PENDING).exists():
        return False
    if profile.suspension_restore_active is not None:
        return profile.suspension_restore_active
    # Legacy unknown activation must not be guessed from an old review or the
    # absence of application records (which can be purged).
    return user.is_active


def apply_suspension(user, suspend, *, expected_version=None):
    """Apply or retry an authorized action, retaining first-suspension intent.

    Authentication denies suspension_update_pending until all effects finish.
    Repeating an already completed action does not overwrite activation chosen
    later by another authorized workflow.
    """
    if type(suspend) is not bool:
        raise ValueError("Invalid suspension action.")
    if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
        raise ValueError("Invalid suspension version.")
    current_user = get_user_model().objects.get(pk=user.pk)
    if current_user.is_superuser:
        raise ValueError("Superuser suspension cannot be changed here.")
    profile, _ = Profile.objects.get_or_create(user=current_user)
    pending = bool(profile.suspension_update_pending)
    version = profile.suspension_version or 0
    if profile.is_suspended == suspend and not pending:
        return profile
    if expected_version is not None and version != expected_version:
        raise SuspensionConflict("This account's suspension changed while you were editing. Reload before trying again.")

    was_active = profile.suspension_was_active
    restore_active = profile.suspension_restore_active
    capture_activation = suspend and (
        (not profile.is_suspended and not pending)
        or (profile.is_suspended and pending and was_active is None)
    )
    if capture_activation:
        # Reserve lifecycle intent before reading activation. A completed review
        # in between the earlier User read and this CAS must be captured; a
        # still-running review is prevented from clearing its access intent.
        was_active = restore_active = None
    changed = _versioned(profile).filter(is_suspended=profile.is_suspended).update(
        is_suspended=suspend, suspension_was_active=was_active,
        suspension_restore_active=restore_active,
        suspension_version=version + 1, suspension_update_pending=True,
    )
    if changed != 1:
        raise SuspensionConflict("This account changed while suspension was being updated. Reload before trying again.")
    # Keep this operation's token; refreshing here could adopt a competing
    # action's version and then accidentally act on its behalf.
    profile.is_suspended = suspend
    profile.suspension_was_active = was_active
    profile.suspension_restore_active = restore_active
    profile.suspension_version = version + 1
    profile.suspension_update_pending = True
    if capture_activation:
        _check_operation(profile)
        current_user.refresh_from_db()
        was_active = current_user.is_active
        if _current_operation(profile).update(
            suspension_was_active=was_active, suspension_restore_active=was_active,
        ) != 1:
            raise SuspensionConflict("This account's suspension changed before activation was saved. Reload before retrying.")
        profile.suspension_was_active = profile.suspension_restore_active = was_active
    active = False if suspend else _restore_membership_access(profile, current_user)
    _check_operation(profile)
    current_user.refresh_from_db()
    if current_user.is_active != active:
        current_user.is_active = active
        current_user.save(update_fields=["is_active"])

    if _current_operation(profile).update(suspension_update_pending=False) != 1:
        # A late User write cannot atomically test another document's version.
        # Keep the winner's state/snapshot, but require a fresh completion before
        # account access resumes after an interleaved lifecycle write.
        latest = Profile.objects.get(pk=profile.pk)
        _versioned(latest).update(suspension_update_pending=True)
        raise SuspensionConflict("Another suspension action intervened. Reload and finish the current account access update.")
    profile.refresh_from_db()
    return profile
