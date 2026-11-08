"""
AI meeting drafts and officer review (FR-06, FR-12; WBS 1.9).

Ported from the Software-Eng "AI drafts" feature. An officer submits meeting
notes; the AI produces a summary and proposed action items; an officer then
reviews the draft. Nothing becomes official until a reviewer approves it.

Status lifecycle:
    pending_review -> approved
    pending_review -> rejected
    pending_review -> revision_requested -> pending_review (notes revised)

Finished approved reviews feed the explicit task conversion workflow (WBS 1.10).
"""

import logging
from uuid import uuid4

from bson import ObjectId
from django.conf import settings
from django.db import DatabaseError, IntegrityError, models
from django.db.models import Q
from django.utils import timezone

from .ai import summarize_meeting


logger = logging.getLogger(__name__)


def generation_filter(token):
    # Also support documents inserted outside migrations before this field existed.
    if not token:
        return Q(generation_token="") | Q(generation_token__isnull=True)
    return Q(generation_token=token)


class DraftStatus(models.TextChoices):
    PENDING_REVIEW = "pending_review", "Pending review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


REVIEW_DECISIONS = [DraftStatus.APPROVED, DraftStatus.REJECTED, DraftStatus.REVISION_REQUESTED]


class MeetingReviewConflict(ValueError):
    """A different request has already recorded this draft's decision."""


class MeetingDraft(models.Model):
    title = models.CharField(max_length=200)
    transcript = models.TextField(blank=True)
    notes = models.TextField(blank=True)
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
    review_update_pending = models.BooleanField(default=False)
    review_item_intent = models.JSONField(default=None, null=True, blank=True, editable=False)
    generation_token = models.CharField(max_length=32, default="", blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def generate(self):
        """Run the AI over the transcript and officer notes."""
        result = summarize_meeting(self.transcript, self.notes)
        self.summary = result.summary
        self.save()
        self.action_items.all().delete()
        for position, text in enumerate(result.action_items):
            ActionItem.objects.create(draft=self, description=text, position=position)

    def review(self, reviewer, decision, note="", *, item_intent=None, expected_generation=None):
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Invalid review decision: {decision}")
        if expected_generation is not None and (expected_generation or "") != (self.generation_token or ""):
            raise MeetingReviewConflict("This meeting generation changed. Reload the draft before reviewing it.")
        if item_intent is None:
            item_intent = [
                {"id": str(item.pk), "description": item.description, "accepted": item.accepted}
                for item in self.current_action_items
            ]
        item_intent = self._normalize_review_items(item_intent)
        # Two requests can load the same pending draft. Keep the decision and
        # complete item intent in one conditional update. Only its winner may
        # write the separate ActionItems; imports stay blocked until completion.
        changed = type(self).objects.filter(
            generation_filter(self.generation_token if expected_generation is None else expected_generation),
            pk=self.pk, status=DraftStatus.PENDING_REVIEW
        ).exclude(review_update_pending=True).update(
            status=decision, reviewed_by=reviewer.pk,
            reviewed_at=timezone.now(), review_note=note,
            review_update_pending=True, review_item_intent=item_intent,
        )
        if changed != 1:
            raise MeetingReviewConflict("Only drafts pending review can be reviewed.")
        self.refresh_from_db()
        self.complete_review_update()

    def complete_review_update(self):
        """Retry the recorded item intent without replacing review metadata."""
        current = type(self).objects.get(pk=self.pk)
        if current.status not in REVIEW_DECISIONS:
            raise ValueError("This meeting has no recorded decision to finish.")
        if not current.review_update_pending:
            self.refresh_from_db()
            return self
        intent = current._normalize_review_items(current.review_item_intent)
        for item in intent:
            ActionItem.objects.filter(generation_filter(current.generation_token)).update_or_create(
                pk=ObjectId(item["id"]), draft_id=current.pk,
                defaults={
                    "description": item["description"], "accepted": item["accepted"],
                    "position": item["position"], "generation_token": current.generation_token or "",
                },
            )
        # A failed item write leaves this marker true. Retrying the same IDs
        # updates existing records rather than duplicating newly added items.
        type(self).objects.filter(
            generation_filter(current.generation_token),
            pk=current.pk, status=current.status, review_update_pending=True,
        ).update(review_update_pending=False)
        self.refresh_from_db()
        if (self.generation_token or "") != (current.generation_token or ""):
            raise MeetingReviewConflict("This meeting generation changed while completing review. Reload the draft.")
        if self.review_update_pending:
            raise ValueError("The review could not be finalized. Its saved action updates remain unfinished.")
        return self

    def revise(self, notes, *, title=None, expected_generation=None):
        """Resubmit after a revision request: new notes, fresh AI output, back to review."""
        expected_generation = self.generation_token if expected_generation is None else expected_generation
        current = type(self).objects.get(pk=self.pk)
        if current.status != DraftStatus.REVISION_REQUESTED or (current.generation_token or "") != (expected_generation or ""):
            raise MeetingReviewConflict("Only drafts with a current revision request can be revised. Reload the meeting.")
        if current.review_update_pending:
            raise ValueError("Finish the recorded action-item review before revising notes.")
        return self._publish_generation(
            notes, self.title if title is None else title, new=False, expected_generation=expected_generation,
        )


class ActionItem(models.Model):
    draft = models.ForeignKey(MeetingDraft, on_delete=models.CASCADE, related_name="action_items")
    description = models.CharField(max_length=500)
    # Reviewers untick items the AI got wrong; only accepted items count once approved.
    accepted = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    generation_token = models.CharField(max_length=32, default="", blank=True, editable=False)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.description
