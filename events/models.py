"""
Events, RSVPs and attendance (FR-03; WBS 1.5).

Officers create and manage events. Members RSVP to upcoming events, and
officers record who actually attended. Attendance is recorded separately
from RSVPs because people who didn't RSVP can still show up (and the other
way round); reports (WBS 1.8) will read both.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


def member_since_by_user(users):
    """When each user's current membership started, as {user_pk: datetime} (US-13).

    This is the most recent approval of their membership application, so
    events held while the account was still pending, or before a later
    re-approval, don't count. Accounts never approved through an application
    (for example the createsuperuser admin, or members whose role was set
    directly) fall back to the account's creation date. Uses one query for
    all users.
    """
    # Imported here because membership imports account models at load time.
    from membership.models import ApplicationStatus, MembershipApplication

    users = list(users)
    latest_approval = {}
    approvals = MembershipApplication.objects.filter(
        user_id__in=[u.pk for u in users],
        status=ApplicationStatus.APPROVED,
        reviewed_at__isnull=False,
    ).values_list("user_id", "reviewed_at")
    for user_id, reviewed_at in approvals:
        if user_id not in latest_approval or reviewed_at > latest_approval[user_id]:
            latest_approval[user_id] = reviewed_at
    return {u.pk: latest_approval.get(u.pk) or u.date_joined for u in users}


def member_since(user):
    """When one user's current membership started; see member_since_by_user."""
    return member_since_by_user([user])[user.pk]


class EventQuerySet(models.QuerySet):
    def attendance_summary_for(self, user):
        """US-13: a member's own attendance since their membership was approved.

        Counts past, non-cancelled events that started on or after
        member_since(user). Returns the events newest first, each marked
        attended or not, plus the attended count, total, rounded rate
        (None when there are no past events yet) and the start date used.
        """
        since = member_since(user)
        events = list(
            self.filter(
                starts_at__lt=timezone.now(),
                cancelled=False,
                starts_at__gte=since,
            ).order_by("-starts_at")
        )
        attended_ids = set(
            Attendance.objects.filter(user=user, event__in=[e.pk for e in events]).values_list(
                "event_id", flat=True
            )
        )
        total = len(events)
        attended = sum(1 for e in events if e.pk in attended_ids)
        return {
            "history": [{"event": e, "attended": e.pk in attended_ids} for e in events],
            "attended": attended,
            "total": total,
            "rate": round(attended / total * 100) if total else None,
            "since": since,
        }


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    @property
    def is_upcoming(self):
        return self.starts_at >= timezone.now()

    @property
    def accepts_rsvps(self):
        return self.is_upcoming and not self.cancelled


class RSVPResponse(models.TextChoices):
    GOING = "going", "Going"
    NOT_GOING = "not_going", "Not going"


class RSVP(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="rsvps")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_rsvps")
    response = models.CharField(max_length=20, choices=RSVPResponse.choices)
    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="unique_event_rsvp"),
        ]

    def __str__(self):
        return f"{self.user} - {self.event} ({self.response})"


class Attendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendance")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_attendance")
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="unique_event_attendance"),
        ]

    def __str__(self):
        return f"{self.user} attended {self.event}"


class AttendanceAction(models.TextChoices):
    MARKED = "marked", "Marked present"
    UNMARKED = "unmarked", "Marked absent"


class AttendanceAuditStatus(models.TextChoices):
    # A removal is logged as pending before the Attendance record is deleted
    # and only becomes completed once the delete is confirmed. Marks are
    # written after their Attendance record exists, so they are always completed.
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"


class AttendanceAuditLog(models.Model):
    """Immutable record of attendance mark/unmark actions for FR-09 audit history.

    change_key is a stable idempotency token set by the caller:
      - mark events:   "mark:<attendance_pk>"
      - unmark events: "unmark:<attendance_pk>"
    Using the Attendance PK as the anchor ensures that retrying a partial write
    after a database failure produces exactly one audit entry per attendance change,
    even when one of the two writes (attendance and audit log) succeeded while the
    other did not.

    status separates a removal that has been requested (pending) from one that
    has happened (completed). The audit history shows only completed entries.
    actor and at describe the original change: a mark entry repaired on a later
    request still credits Attendance.marked_by at Attendance.marked_at.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendance_audit_log")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_audit_log",
    )
    action = models.CharField(max_length=20, choices=AttendanceAction.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=AttendanceAuditStatus.choices,
        default=AttendanceAuditStatus.COMPLETED,
    )
    change_key = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
        help_text="Stable idempotency token: 'mark:<attendance_pk>' or 'unmark:<attendance_pk>'.",
    )

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.actor} {self.action} {self.user} for {self.event}"
