"""
Membership applications (FR-02).

Signing up submits an application along with the new account, which stays
switched off (inactive) until an officer approves it. Approving switches the
account on and promotes the applicant to the `member` role. Rejecting deletes
what the person submitted so they can apply again from scratch.
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
        """Approve or reject this application. Only pending applications can be reviewed.

        Rejecting keeps nothing the person submitted, so they can reapply with
        the same email and username:
        - an account that was never approved (still switched off) is deleted,
          along with its application, profile and any Google link;
        - an account that was already active keeps the account, and only the
          application is deleted.
        """
        if not self.is_pending:
            raise ValueError("This application has already been reviewed.")
        if not approve:
            if self.user.is_active:
                self.delete()
            else:
                self.user.delete()
            return
        self.status = ApplicationStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()
        # New accounts stay switched off until their application is approved.
        if not self.user.is_active:
            self.user.is_active = True
            self.user.save(update_fields=["is_active"])
        # Only promote applicants; never demote an officer/admin who applied.
        if get_role(self.user) == Role.APPLICANT:
            set_role(self.user, Role.MEMBER)


def inactive_account_message(user):
    """Explain to a switched-off account why it can't sign in yet."""
    latest = user.membership_applications.order_by("-submitted_at").first()
    if latest is None:
        return "This account is inactive."
    if latest.status == ApplicationStatus.PENDING:
        return (
            "Your membership application is still pending. "
            "You can sign in once an officer approves it."
        )
    return "This account is inactive."
