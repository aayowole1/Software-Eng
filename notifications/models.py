"""In-app notifications for published announcements and assigned tasks (FR-5.4)."""

from django.conf import settings
from django.db import models


class NotificationKind(models.TextChoices):
    ANNOUNCEMENT = "announcement", "Announcement"
    TASK = "task", "Task"


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=NotificationKind.choices)
    # Stores the string representation of the linked object's pk (ObjectId).
    object_id = models.CharField(max_length=100)
    # Human-readable headline so it can be shown without an extra query.
    headline = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} notification for {self.user_id}"

    def get_target_url(self):
        from django.urls import reverse
        if self.kind == NotificationKind.ANNOUNCEMENT:
            return reverse("announcements:detail", args=[self.object_id])
        return reverse("tasks:detail", args=[self.object_id])
