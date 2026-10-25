"""
Membership applications (FR-02).

Signing up submits an application along with the new account, which stays
switched off (inactive) until an officer approves it. Approving switches the
account on and promotes the applicant to the `member` role. Rejecting needs a
reason; it also switches the account on, but only with applicant access, so
the person can sign in, read the reason, and apply again once
REAPPLY_WAIT has passed. Applications are kept with who reviewed them, when,
and why; rejected ones are deleted REJECTED_RETENTION after the decision
(see `purge_old_rejected_applications`).
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Role, get_role, set_role


# How long a rejected applicant waits before applying again.
REAPPLY_WAIT = timedelta(days=1)
# How long a rejected application (with its reason and reviewer) is kept.
REJECTED_RETENTION = timedelta(days=7)


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
        """Approve or reject a pending membership application.

        Administratively suspended accounts cannot be reviewed.
        Rejecting an application requires a reason.
        """

        # Prevent reviewing an application more than once.
        if not self.is_pending:
            raise ValueError(
                "This application has already been reviewed."
            )

        # R-02: Block reviews of administratively suspended accounts.
        if self.user.profile.is_suspended:
            raise ValueError(
                "This account is administratively suspended and cannot be reviewed."
            )

        # Validate the rejection reason.
        note = (note or "").strip()

        if not approve and not note:
            raise ValueError(
                "Give a reason when rejecting an application."
            )

        # Update the application decision.
        self.status = (
            ApplicationStatus.APPROVED
            if approve
            else ApplicationStatus.REJECTED
        )

        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()

        # Activate the account only when it is not suspended.
        if not self.user.profile.is_suspended and not self.user.is_active:
            self.user.is_active = True
            self.user.save(update_fields=["is_active"])

        # Promote approved applicants to the Member role.
        # Existing Officers and Admins retain their roles.
        if approve and get_role(self.user) == Role.APPLICANT:
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


def next_application_allowed_at(user):
    """When `user` may apply again after a rejection, or None if there's no wait."""
    latest = user.membership_applications.order_by("-submitted_at").first()
    if latest is None or latest.status != ApplicationStatus.REJECTED or latest.reviewed_at is None:
        return None
    allowed_at = latest.reviewed_at + REAPPLY_WAIT
    return allowed_at if allowed_at > timezone.now() else None


def purge_old_rejected_applications(now=None):
    """Delete rejected applications decided more than REJECTED_RETENTION ago.

    Only the application is deleted; the person's account stays, so they can
    still sign in and apply again. Returns how many were deleted.
    """
    cutoff = (now or timezone.now()) - REJECTED_RETENTION
    old = MembershipApplication.objects.filter(
        status=ApplicationStatus.REJECTED, reviewed_at__lt=cutoff
    )
    count = old.count()
    old.delete()
    return count
