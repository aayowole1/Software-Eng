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
