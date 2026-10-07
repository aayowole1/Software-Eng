"""
Membership applications (FR-02).

An applicant submits an application; an officer approves or rejects it.
Approving an application promotes the applicant to the `member` role.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Role, get_role, set_role


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class MembershipApplication(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership_applications",
    )
    statement = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user} – {self.status}"

    @property
    def is_pending(self):
        return self.status == ApplicationStatus.PENDING

    def review(self, reviewer, approve, note=""):
        """Approve or reject this application. Only pending applications can be reviewed."""
        if not self.is_pending:
            raise ValueError("This application has already been reviewed.")
        self.status = ApplicationStatus.APPROVED if approve else ApplicationStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()
        # Only promote applicants; never demote an officer/admin who applied.
        if approve and get_role(self.user) == Role.APPLICANT:
            set_role(self.user, Role.MEMBER)
