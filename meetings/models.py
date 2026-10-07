"""
AI meeting drafts and officer review (FR-06, FR-12; WBS 1.9).

Ported from the Software-Eng "AI drafts" feature. An officer submits meeting
notes; the AI produces a summary and proposed action items; an officer then
reviews the draft. Nothing becomes official until a reviewer approves it.

Status lifecycle:
    pending_review -> approved
    pending_review -> rejected
    pending_review -> revision_requested -> pending_review (notes revised)

Approved action items will be turned into tasks once the task module
(WBS 1.6) exists; that connection is planned for WBS 1.10.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from .ai import summarize_meeting


class DraftStatus(models.TextChoices):
    PENDING_REVIEW = "pending_review", "Pending review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


REVIEW_DECISIONS = [DraftStatus.APPROVED, DraftStatus.REJECTED, DraftStatus.REVISION_REQUESTED]


class MeetingDraft(models.Model):
    title = models.CharField(max_length=200)
    notes = models.TextField()
    summary = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=DraftStatus.choices,
        default=DraftStatus.PENDING_REVIEW,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
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
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def generate(self):
        """Run the AI over the notes, replacing any earlier summary and items."""
        result = summarize_meeting(self.notes)
        self.summary = result.summary
        self.save()
        self.action_items.all().delete()
        for position, text in enumerate(result.action_items):
            ActionItem.objects.create(draft=self, description=text, position=position)

    def review(self, reviewer, decision, note=""):
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Invalid review decision: {decision}")
        if self.status != DraftStatus.PENDING_REVIEW:
            raise ValueError("Only drafts pending review can be reviewed.")
        self.status = decision
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()

    def revise(self, notes):
        """Resubmit after a revision request: new notes, fresh AI output, back to review."""
        if self.status != DraftStatus.REVISION_REQUESTED:
            raise ValueError("Only drafts with a revision request can be revised.")
        self.notes = notes
        self.status = DraftStatus.PENDING_REVIEW
        self.reviewed_by = None
        self.reviewed_at = None
        self.generate()


class ActionItem(models.Model):
    draft = models.ForeignKey(MeetingDraft, on_delete=models.CASCADE, related_name="action_items")
    description = models.CharField(max_length=500)
    # Reviewers untick items the AI got wrong; only accepted items count once approved.
    accepted = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.description
