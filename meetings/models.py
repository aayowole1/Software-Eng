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

from bson import ObjectId
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


class MeetingReviewConflict(ValueError):
    """A different request has already recorded this draft's decision."""


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
    review_update_pending = models.BooleanField(default=False)
    review_item_intent = models.JSONField(default=None, null=True, blank=True, editable=False)

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

    def _normalize_review_items(self, items):
        if not isinstance(items, list):
            raise ValueError("The action-item review must be a list.")
        normalized = []
        seen = set()
        for position, item in enumerate(items):
            if not isinstance(item, dict) or not ObjectId.is_valid(str(item.get("id", ""))):
                raise ValueError("The action-item review contains an invalid identifier.")
            item_id = str(ObjectId(str(item["id"])))
            if item_id in seen:
                raise ValueError("The action-item review contains duplicate identifiers.")
            description = item.get("description")
            if not isinstance(description, str) or not description.strip() or len(description.strip()) > 500:
                raise ValueError("Action items must contain between 1 and 500 characters.")
            if type(item.get("accepted")) is not bool:
                raise ValueError("Choose whether each action item is accepted.")
            normalized.append({
                "id": item_id, "description": description.strip(),
                "accepted": item["accepted"], "position": position,
            })
            seen.add(item_id)
        for item in ActionItem.objects.filter(pk__in=list(seen)):
            if item.draft_id != self.pk:
                raise ValueError("An action item belongs to a different meeting draft.")
        return normalized

    def review(self, reviewer, decision, note="", *, item_intent=None):
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Invalid review decision: {decision}")
        if item_intent is None:
            item_intent = [
                {"id": str(item.pk), "description": item.description, "accepted": item.accepted}
                for item in self.action_items.all()
            ]
        item_intent = self._normalize_review_items(item_intent)
        # Two requests can load the same pending draft. Keep the decision and
        # complete item intent in one conditional update. Only its winner may
        # write the separate ActionItems; imports stay blocked until completion.
        changed = type(self).objects.filter(
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
            ActionItem.objects.update_or_create(
                pk=ObjectId(item["id"]), draft_id=current.pk,
                defaults={
                    "description": item["description"], "accepted": item["accepted"],
                    "position": item["position"],
                },
            )
        # A failed item write leaves this marker true. Retrying the same IDs
        # updates existing records rather than duplicating newly added items.
        type(self).objects.filter(
            pk=current.pk, status=current.status, review_update_pending=True,
        ).update(review_update_pending=False)
        self.refresh_from_db()
        if self.review_update_pending:
            raise ValueError("The review could not be finalized. Its saved action updates remain unfinished.")
        return self

    def revise(self, notes):
        """Resubmit after a revision request: new notes, fresh AI output, back to review."""
        if self.status != DraftStatus.REVISION_REQUESTED:
            raise ValueError("Only drafts with a revision request can be revised.")
        if self.review_update_pending:
            raise ValueError("Finish the recorded action-item review before revising notes.")
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
