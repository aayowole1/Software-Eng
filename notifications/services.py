"""Helpers that create and list Notification records; creation never raises."""

import logging

from django.db import DatabaseError

from accounts.models import Role, has_minimum_role
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
    """Create one notification per current member for a newly published announcement.

    Recipients follow the app's shared account rule (``eligible_assignees``):
    active Members, Officers and Admins who are not suspended and have no
    pending access change. Applicants are excluded. Committee-targeted
    filtering (US-18) is out of scope for this story.

    The announcement is already saved, so a failed recipient lookup is logged
    instead of turning the publish into an error page.
    """
    from tasks.models import eligible_assignees

    try:
        recipient_ids = list(eligible_assignees().values_list("pk", flat=True))
    except DatabaseError:
        logger.exception("Failed to look up recipients for announcement %s", announcement.pk)
        return

    headline = f"New announcement: {announcement.title}"
    object_id = str(announcement.pk)
    _bulk_create([
        Notification(
            user_id=user_id,
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=object_id,
            headline=headline,
        )
        for user_id in recipient_ids
    ])


def notify_task_assigned(task_id, title, assignee_id):
    """Create a notification for a user who has been assigned (or reassigned) a task.

    Callers pass the values their own write stored, not a re-read of the task,
    so a concurrent edit cannot redirect or duplicate the alert.
    """
    _bulk_create([
        Notification(
            user_id=assignee_id,
            kind=NotificationKind.TASK,
            object_id=str(task_id),
            headline=f"You have been assigned a task: {title}",
        )
    ])


def visible_notifications(user):
    """The user's notifications whose target they can still open.

    Announcement notifications need current Member access to announcements.
    Task notifications need the task to still be visible to the user, so a
    member demoted to applicant (or moved off the committee) no longer sees
    old task headlines. Hidden notifications are kept, so they reappear if
    access is restored.
    """
    from announcements.permissions import effective_role
    from tasks.models import Task

    mine = Notification.objects.filter(user=user)
    allowed = []
    if has_minimum_role(effective_role(user), Role.MEMBER):
        allowed.extend(mine.filter(kind=NotificationKind.ANNOUNCEMENT).values_list("pk", flat=True))
    task_ids = set(mine.filter(kind=NotificationKind.TASK).values_list("object_id", flat=True))
    if task_ids:
        open_ids = {
            str(pk) for pk in Task.objects.visible_to(user).filter(
                pk__in=[pk for pk in task_ids if _is_object_id(pk)]
            ).values_list("pk", flat=True)
        }
        allowed.extend(mine.filter(kind=NotificationKind.TASK, object_id__in=open_ids).values_list("pk", flat=True))
    return mine.filter(pk__in=allowed)


def _is_object_id(value):
    from bson import ObjectId

    return ObjectId.is_valid(value)
