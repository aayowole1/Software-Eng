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


class EventQuerySet(models.QuerySet):
    def attendance_summary_for(self, user):
        """US-13: a member's own attendance since they joined.

        Counts past, non-cancelled events that started on or after the
        account was created. Returns the events newest first, each marked
        attended or not, plus the attended count, total and rounded rate
        (None when there are no past events yet).
        """
        events = list(
            self.filter(
                starts_at__lt=timezone.now(),
                cancelled=False,
                starts_at__gte=user.date_joined,
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
