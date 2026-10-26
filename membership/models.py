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
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from accounts.models import Profile, Role, set_role


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
    access_update_pending = models.BooleanField(
        default=False,
        help_text="A recorded review still needs its account access update completed.",
    )

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

        current = type(self).objects.get(pk=self.pk)
        if not current.is_pending:
            raise ValueError("This application has already been reviewed.")

        profile = Profile.objects.filter(user_id=current.user_id).first()
        if profile is None:
            raise ValueError("This account needs a profile before it can be reviewed.")
        # Re-read suspension state rather than trusting a cached related object.
        if profile.is_suspended:
            raise ValueError(
                "This account is administratively suspended and cannot be reviewed."
            )

        # Validate the rejection reason.
        note = (note or "").strip()

        if not approve and not note:
            raise ValueError(
                "Give a reason when rejecting an application."
            )

        decision = (
            ApplicationStatus.APPROVED
            if approve
            else ApplicationStatus.REJECTED
        )

        # Recording both the decision and its unfinished access intent in one
        # conditional document update prevents competing stale reviewers from
        # replacing each other's decisions. No MongoDB transaction is assumed.
        changed = type(self).objects.filter(
            pk=self.pk, status=ApplicationStatus.PENDING
        ).update(
            status=decision, reviewed_by=reviewer.pk, reviewed_at=timezone.now(),
            review_note=note, access_update_pending=True,
        )
        if changed != 1:
            raise ValueError("This application has already been reviewed.")
        self.refresh_from_db()
        self.complete_access_update()

    def complete_access_update(self):
        """Finish only a recorded, explicitly unfinished review's access work.

        This retry preserves the original decision, reviewer, note and date.
        The intent flag stays set until every effect completes, so authentication
        can fail closed even if a later write fails after account activation.
        """
        current = type(self).objects.get(pk=self.pk)
        if current.status not in (ApplicationStatus.APPROVED, ApplicationStatus.REJECTED) or not current.access_update_pending:
            raise ValueError("This application has no unfinished review access update.")
        user = get_user_model().objects.get(pk=current.user_id)
        profile = Profile.objects.filter(user_id=user.pk).first()
        if profile is None or profile.role not in Role.values:
            raise ValueError("This account needs a valid profile before access can be updated.")
        if profile.is_suspended:
            raise ValueError("This account is administratively suspended and cannot be activated.")
        if current.status == ApplicationStatus.REJECTED and (user.is_superuser or profile.role != Role.APPLICANT):
            raise ValueError(
                "The rejection is recorded, but this account has an elevated role. "
                "An administrator must restore Applicant before account access can finish."
            )

        # Promote before activation. Conditional promotion preserves a newer
        # officer/admin assignment and makes a partially completed retry harmless.
        if current.status == ApplicationStatus.APPROVED and not user.is_superuser:
            set_role(
                user, Role.MEMBER, actor=current.reviewed_by,
                source=f"membership_review:{current.pk}",
                expected_role=Role.APPLICANT, require_unsuspended=True,
                membership_review=current,
            )

        # Suspension may have changed while promotion was being applied.
        profile.refresh_from_db()
        if profile.is_suspended:
            raise ValueError("This account is administratively suspended and cannot be activated.")
        user.refresh_from_db()
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        profile.refresh_from_db()
        if profile.is_suspended:
            raise ValueError("This account is administratively suspended; access remains pending.")
        if current.status == ApplicationStatus.REJECTED and (user.is_superuser or profile.role != Role.APPLICANT):
            raise ValueError("The account's role changed; rejected membership access remains pending.")
        # Only this flag changes on completion. Review metadata is immutable.
        type(self).objects.filter(
            pk=current.pk, status=current.status, access_update_pending=True
        ).update(access_update_pending=False)
        self.refresh_from_db()
        if self.access_update_pending:
            raise ValueError("The review changed while access was being updated. Account access remains pending.")



def inactive_account_message(user):
    """Explain to a switched-off account why it can't sign in yet."""
    latest = user.membership_applications.order_by("-submitted_at").first()
    if latest is None:
        return "This account is inactive."
    if latest.access_update_pending:
        return (
            "Your membership decision is recorded, but account access is still "
            "being updated. Please contact an officer."
        )
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
        status=ApplicationStatus.REJECTED, reviewed_at__lt=cutoff,
        access_update_pending=False,
    )
    count = old.count()
    old.delete()
    return count
