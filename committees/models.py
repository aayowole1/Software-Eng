"""
Committees and their rosters (FR-04).

Ported from the Software-Eng "teams" feature (WBS 1.4). Each committee
member has a committee role: `chair` (the creator) or `member`. Committee
roles are separate from organization roles (applicant/member/officer/admin).
"""

from django.conf import settings
from django.db import models


class CommitteeRole(models.TextChoices):
    CHAIR = "chair", "Chair"
    MEMBER = "member", "Member"


class Committee(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CommitteeMember(models.Model):
    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="committee_memberships",
    )
    role = models.CharField(max_length=20, choices=CommitteeRole.choices, default=CommitteeRole.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        constraints = [
            models.UniqueConstraint(fields=["committee", "user"], name="unique_committee_member"),
        ]

    def __str__(self):
        return f"{self.user} in {self.committee} ({self.role})"
