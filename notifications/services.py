"""Helpers that create Notification records; callers never raise on failure."""

import logging

from django.contrib.auth import get_user_model
from django.db import DatabaseError

from accounts.models import ROSTER_ROLES, Role
from .models import Notification, NotificationKind

logger = logging.getLogger(__name__)


def _bulk_create(notifications):
    """Insert all notification records; log and swallow any storage error."""
    if not notifications:
        return
    try:
        Notification.objects.bulk_create(notifications)
    except DatabaseError:
        logger.exception("Failed to create %d notification(s)", len(notifications))


def notify_announcement_published(announcement):
    """Create one notification per eligible member for a newly published announcement.

    Members, Officers, and Admins are notified. Applicants are excluded.
    Committee-targeted filtering (US-18) is out of scope for this story.
    """
    User = get_user_model()
    recipients = User.objects.filter(
        is_active=True,
        profile__role__in=ROSTER_ROLES,
        profile__is_suspended=False,
    ).exclude(profile__suspension_update_pending=True)

    headline = f"New announcement: {announcement.title}"
    object_id = str(announcement.pk)
    notifications = [
        Notification(
            user=user,
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=object_id,
            headline=headline,
        )
        for user in recipients
    ]
    _bulk_create(notifications)


def notify_task_assigned(task, assignee):
    """Create a notification for a user who has been assigned (or reassigned) a task."""
    headline = f"You have been assigned a task: {task.title}"
    _bulk_create([
        Notification(
            user=assignee,
            kind=NotificationKind.TASK,
            object_id=str(task.pk),
            headline=headline,
        )
    ])
