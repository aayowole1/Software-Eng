from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Profile, Role, set_role
from membership.models import ApplicationStatus


class OfficerApplication(models.Model):
    """An existing member's request for promotion, independent of signup."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    statement = models.TextField(max_length=5000)
    status = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    approval_role_version = models.PositiveIntegerField(null=True, blank=True)

    is_officer_application = True

    class Meta:
        ordering = ["-submitted_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(status=ApplicationStatus.PENDING),
                name="one_pending_officer_application",
            ),
        ]

    @property
    def approval_in_progress(self):
        return self.approval_role_version is not None

    def review(self, reviewer, approve, note=""):
        """Record one decision and make approval safe to retry after a failed write."""
        current = type(self).objects.get(pk=self.pk)
        if current.status != ApplicationStatus.PENDING:
            raise ValueError("This application has already been reviewed.")

        pending = type(self).objects.filter(pk=current.pk, status=ApplicationStatus.PENDING)
        unclaimed = pending.filter(approval_role_version__isnull=True)
        note = (note or "").strip()
        if not approve:
            if not note:
                raise ValueError("Give a reason when rejecting an application.")
            if unclaimed.update(
                status=ApplicationStatus.REJECTED, reviewed_by=reviewer,
                reviewed_at=timezone.now(), review_note=note,
            ) != 1:
                raise ValueError("An approval is already in progress or this application was reviewed.")
            return

        profile = Profile.objects.filter(user_id=current.user_id).first()
        if profile is None:
            raise ValueError("The applicant needs a profile before approval.")
        if not current.approval_in_progress:
            if not current._eligible_for_promotion(profile):
                raise ValueError("Only an active member can be promoted to Officer.")
            if unclaimed.update(
                approval_role_version=profile.role_version or 0,
                reviewed_by=reviewer, reviewed_at=timezone.now(), review_note=note,
            ) != 1:
                raise ValueError("The application changed. Reload it before reviewing again.")
            current.refresh_from_db()
        current._finish_approval(profile, reviewer)

    def _eligible_for_promotion(self, profile):
        return (
            self.user.is_active and not self.user.is_superuser
            and profile.role == Role.MEMBER and not profile.is_suspended
            and not profile.suspension_update_pending
        )

    def _finish_approval(self, profile, reviewer):
        version = self.approval_role_version
        intent = type(self).objects.filter(
            pk=self.pk, status=ApplicationStatus.PENDING, approval_role_version=version,
        )
        source = f"officer_application:{self.pk}"
        # An acknowledged or unacknowledged role write is identifiable by its
        # audit entry, even if someone later changes the member's role again.
        if not any(entry.get("source") == source for entry in profile.role_history):
            if (profile.role_version or 0) != version:
                intent.update(approval_role_version=None, reviewed_by=None, reviewed_at=None, review_note="")
                raise ValueError("The member's role changed. Review the application again.")
            if not self._eligible_for_promotion(profile):
                raise ValueError("Only an active member can be promoted to Officer.")
            profile = set_role(
                self.user, Role.OFFICER, actor=self.reviewed_by or reviewer, source=source,
                expected_role=Role.MEMBER, expected_version=version, require_unsuspended=True,
            )
            if not any(entry.get("source") == source for entry in profile.role_history):
                raise ValueError("The member's role changed. Reload the application before continuing.")
        if intent.update(status=ApplicationStatus.APPROVED, approval_role_version=None) != 1:
            if not type(self).objects.filter(pk=self.pk, status=ApplicationStatus.APPROVED).exists():
                raise ValueError("The application changed. Reload it to confirm the decision.")
