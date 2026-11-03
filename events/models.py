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


class AttendanceAuditLog(models.Model):
    """Immutable record of attendance mark/unmark actions for FR-09 audit history.

    change_key is a stable idempotency token set by the caller:
      - mark events:   "mark:<attendance_pk>"
      - unmark events: "unmark:<attendance_pk>"
    Using the Attendance PK as the anchor ensures that retrying a partial write
    after a database failure produces exactly one audit entry per attendance change,
    even when one of the two writes (attendance and audit log) succeeded while the
    other did not.
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
    at = models.DateTimeField(auto_now_add=True)
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
