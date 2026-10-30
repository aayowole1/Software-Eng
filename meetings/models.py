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
    generation_token = models.CharField(max_length=32, default="", blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def current_action_items(self):
        return self.action_items.filter(generation_filter(self.generation_token))

    def cleanup_unpublished_generation(self):
        """Delete only this attempt's uncommitted stage, never a published draft."""
        token = getattr(self, "_staged_generation", None)
        if token is None:
            return True
        if getattr(self, "_publication_uncertain", False):
            return False
        try:
            if type(self).objects.filter(pk=self.pk, generation_token=token).exists():
                return False
            staged = ActionItem.objects.filter(draft_id=self.pk, generation_token=token)
            staged.delete()
            return not staged.exists()
        except Exception:
            logger.error("Unpublished meeting actions could not be cleaned up; operator recovery is required.")
            return False

    def _publish_generation(self, notes, title, *, new, expected_generation=""):
        # Provider work and all action inserts happen before the draft becomes
        # reviewable. Each attempt owns different IDs and a different token.
        self._staged_generation = None
        self._publication_uncertain = False
        result = summarize_meeting(notes)
        self.pk = self.pk or ObjectId()
        token = uuid4().hex
        self._staged_generation = token
        publishing = False
        try:
            for position, text in enumerate(result.action_items):
                ActionItem.objects.create(
                    draft_id=self.pk, generation_token=token, description=text, position=position,
                )
            publishing = True
            self._publication_uncertain = True
            if new:
                self.summary = result.summary
                self.generation_token = token
                self.status = DraftStatus.PENDING_REVIEW
                self.save(force_insert=True)
            else:
                changed = type(self).objects.filter(
                    generation_filter(expected_generation), pk=self.pk,
                    status=DraftStatus.REVISION_REQUESTED,
                ).exclude(review_update_pending=True).update(
                    title=title, notes=notes, summary=result.summary, generation_token=token,
                    status=DraftStatus.PENDING_REVIEW, reviewed_by=None, reviewed_at=None,
                    review_note="", review_item_intent=None, review_update_pending=False,
                )
                if changed != 1:
                    publishing = False
                    self._publication_uncertain = False
                    raise MeetingReviewConflict("This meeting changed during generation. Reload it before trying again.")
        except DatabaseError as error:
            if publishing and not isinstance(error, IntegrityError):
                # A lost acknowledgement can follow a committed publication.
                # Never compensate its draft or its action set, even if a newer
                # review/generation has already advanced it before our read.
                self._publication_uncertain = True
                try:
                    if type(self).objects.filter(pk=self.pk, generation_token=token).exists():
                        self.refresh_from_db()
                        return self
                except DatabaseError:
                    pass
            else:
                self._publication_uncertain = False
                self.cleanup_unpublished_generation()
            raise
        except Exception:
            self.cleanup_unpublished_generation()
            raise
        self.refresh_from_db()
        return self

    def generate(self, *, force_insert=False):
        """Generate a new draft, or safely revise an existing revision request."""
        if self._state.adding:
            return self._publish_generation(self.notes, self.title, new=True)
        if force_insert:
            raise ValueError("Only a new meeting draft can be inserted.")
        return self.revise(self.notes, title=self.title)

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
            if item.draft_id != self.pk or (item.generation_token or "") != (self.generation_token or ""):
                raise ValueError("An action item belongs to a different meeting draft or generation.")
        return normalized

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
