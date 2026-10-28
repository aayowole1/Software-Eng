"""Unit tests for meetings/models.py — MeetingDraft and ActionItem model methods.

These target the model methods directly (generate, review, revise) without
going through the HTTP views. The AI provider is replaced with a small fake
(as in test_generation_safety.py), so no OpenAI key or network call is needed.
"""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .ai import MeetingSummary
from .models import ActionItem, DraftStatus, MeetingDraft


SIMPLE_NOTES = (
    "We discussed the conference agenda.\n"
    "The speakers have been confirmed.\n"
    "Budget approval is still pending.\n"
    "Action: Reserve the main hall by end of week\n"
    "TODO: Send confirmation emails to speakers\n"
)
ACTION_PREFIXES = ("Action:", "TODO:", "- [ ]")


def fake_summarize(notes):
    """Deterministic stand-in for the OpenAI summarizer."""
    lines = [line.strip() for line in notes.splitlines() if line.strip()]
    items = [line for line in lines if line.startswith(ACTION_PREFIXES)]
    other = [line for line in lines if not line.startswith(ACTION_PREFIXES)]
    return MeetingSummary(summary=" ".join(other) or "No discussion recorded.", action_items=items)


class FakeProviderMixin:
    def setUp(self):
        super().setUp()
        patcher = patch("meetings.models.summarize_meeting", side_effect=fake_summarize)
        self.provider = patcher.start()
        self.addCleanup(patcher.stop)
        self.officer = make_user("officer@example.com", Role.OFFICER)

    def new_draft(self, notes=SIMPLE_NOTES, title="Sprint Review"):
        """Create a draft the way the app does: generate() on an unsaved draft."""
        draft = MeetingDraft(title=title, notes=notes, created_by=self.officer)
        draft.generate()
        return draft

    def descriptions(self, draft):
        return list(draft.current_action_items.values_list("description", flat=True))


class MeetingDraftGenerateTests(FakeProviderMixin, TestCase):
    """Unit tests for MeetingDraft.generate()."""

    def test_generate_populates_summary(self):
        draft = self.new_draft()
        self.assertIsInstance(draft.summary, str)
        self.assertTrue(draft.summary)

    def test_generate_creates_action_items(self):
        draft = self.new_draft()
        self.assertEqual(draft.current_action_items.count(), 2)

    def test_generate_starts_pending_review(self):
        draft = self.new_draft()
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)

    def test_regenerating_through_revision_replaces_action_items(self):
        draft = self.new_draft()
        first_items = self.descriptions(draft)
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED, note="Redo")
        draft.revise("Action: Completely new task\n")
        new_items = self.descriptions(draft)
        self.assertNotEqual(first_items, new_items)
        self.assertEqual(draft.current_action_items.count(), 1)
        self.assertIn("Action: Completely new task", new_items)

    def test_generate_does_not_include_action_lines_in_summary(self):
        draft = self.new_draft()
        self.assertNotIn("Reserve the main hall", draft.summary)
        self.assertNotIn("Send confirmation emails", draft.summary)

    def test_generate_with_no_action_items_creates_no_action_item_records(self):
        draft = self.new_draft(notes="Just a regular sentence. And another one.")
        self.assertEqual(draft.current_action_items.count(), 0)

    def test_generate_persists_summary_to_database(self):
        draft = self.new_draft()
        refreshed = MeetingDraft.objects.get(pk=draft.pk)
        self.assertEqual(refreshed.summary, draft.summary)

    def test_generate_calls_the_provider_once_with_the_notes(self):
        self.new_draft()
        self.provider.assert_called_once_with(SIMPLE_NOTES)

    def test_action_items_have_sequential_positions(self):
        draft = self.new_draft()
        positions = list(draft.current_action_items.values_list("position", flat=True))
        self.assertEqual(positions, list(range(len(positions))))

    def test_action_items_default_to_accepted(self):
        draft = self.new_draft()
        self.assertTrue(all(item.accepted for item in draft.current_action_items))


class MeetingDraftReviewTests(TestCase):
    """Unit tests for MeetingDraft.review()."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.draft = MeetingDraft.objects.create(
            title="Monthly Review",
            notes=SIMPLE_NOTES,
            created_by=self.officer,
            status=DraftStatus.PENDING_REVIEW,
        )

    def test_approve_sets_status(self):
        self.draft.review(self.officer, DraftStatus.APPROVED)
        self.assertEqual(self.draft.status, DraftStatus.APPROVED)

    def test_reject_sets_status(self):
        self.draft.review(self.officer, DraftStatus.REJECTED)
        self.assertEqual(self.draft.status, DraftStatus.REJECTED)

    def test_revision_requested_sets_status(self):
        self.draft.review(self.officer, DraftStatus.REVISION_REQUESTED, note="Please clarify.")
        self.assertEqual(self.draft.status, DraftStatus.REVISION_REQUESTED)

    def test_review_stores_reviewer(self):
        self.draft.review(self.officer, DraftStatus.APPROVED)
        self.assertEqual(self.draft.reviewed_by, self.officer)

    def test_review_stores_timestamp(self):
        # MongoDB stores milliseconds, so compare from the start of this millisecond.
        before = timezone.now()
        before = before.replace(microsecond=before.microsecond // 1000 * 1000)
        self.draft.review(self.officer, DraftStatus.APPROVED)
        after = timezone.now()
        self.assertGreaterEqual(self.draft.reviewed_at, before)
        self.assertLessEqual(self.draft.reviewed_at, after)

    def test_review_stores_note(self):
        self.draft.review(self.officer, DraftStatus.APPROVED, note="Well done.")
        self.assertEqual(self.draft.review_note, "Well done.")

    def test_invalid_decision_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.draft.review(self.officer, "pending_review")

    def test_reviewing_non_pending_draft_raises_value_error(self):
        self.draft.status = DraftStatus.APPROVED
        self.draft.save()
        with self.assertRaises(ValueError):
            self.draft.review(self.officer, DraftStatus.REJECTED)

    def test_review_persists_to_database(self):
        self.draft.review(self.officer, DraftStatus.APPROVED, note="Good work.")
        refreshed = MeetingDraft.objects.get(pk=self.draft.pk)
        self.assertEqual(refreshed.status, DraftStatus.APPROVED)
        self.assertEqual(refreshed.review_note, "Good work.")
        self.assertEqual(refreshed.reviewed_by, self.officer)


class MeetingDraftReviseTests(FakeProviderMixin, TestCase):
    """Unit tests for MeetingDraft.revise()."""

    def setUp(self):
        super().setUp()
        self.draft = self.new_draft()
        self.draft.review(self.officer, DraftStatus.REVISION_REQUESTED, note="Add more detail.")

    def test_revise_updates_notes(self):
        new_notes = "Updated meeting notes.\nAction: New task\n"
        self.draft.revise(new_notes)
        self.assertEqual(self.draft.notes, new_notes)

    def test_revise_resets_status_to_pending_review(self):
        self.draft.revise("Updated notes.")
        self.assertEqual(self.draft.status, DraftStatus.PENDING_REVIEW)

    def test_revise_clears_reviewer_and_timestamp(self):
        self.draft.revise("Updated notes.")
        self.assertIsNone(self.draft.reviewed_by)
        self.assertIsNone(self.draft.reviewed_at)

    def test_revise_regenerates_summary_and_action_items(self):
        self.draft.revise("New discussion on strategy.\nAction: Revise the roadmap\n")
        self.assertIn("strategy", self.draft.summary)
        self.assertIn("Action: Revise the roadmap", self.descriptions(self.draft))

    def test_revise_on_non_revision_requested_draft_raises(self):
        for status in [DraftStatus.PENDING_REVIEW, DraftStatus.APPROVED, DraftStatus.REJECTED]:
            with self.subTest(status=status):
                draft = MeetingDraft.objects.create(
                    title=f"Draft-{status}",
                    notes="Notes.",
                    created_by=self.officer,
                    status=status,
                )
                with self.assertRaises(ValueError):
                    draft.revise("New notes.")

    def test_revise_persists_changes_to_database(self):
        self.draft.revise("Persisted notes.\nAction: Check persistence\n")
        refreshed = MeetingDraft.objects.get(pk=self.draft.pk)
        self.assertEqual(refreshed.status, DraftStatus.PENDING_REVIEW)
        self.assertIsNone(refreshed.reviewed_by)
        self.assertIsNone(refreshed.reviewed_at)


class ActionItemTests(FakeProviderMixin, TestCase):
    """Unit tests for ActionItem model defaults and behaviour."""

    def setUp(self):
        super().setUp()
        self.draft = self.new_draft(title="Test Draft")

    def test_action_items_are_ordered_by_position(self):
        positions = list(self.draft.current_action_items.values_list("position", flat=True))
        self.assertEqual(positions, sorted(positions))

    def test_action_items_default_to_accepted_true(self):
        for item in self.draft.current_action_items:
            self.assertTrue(item.accepted)

    def test_action_item_can_be_unaccepted(self):
        item = self.draft.current_action_items.first()
        item.accepted = False
        item.save()
        item.refresh_from_db()
        self.assertFalse(item.accepted)

    def test_str_returns_description(self):
        item = self.draft.current_action_items.first()
        self.assertEqual(str(item), item.description)

    def test_deleting_draft_deletes_action_items(self):
        draft_pk = self.draft.pk
        self.draft.delete()
        self.assertFalse(ActionItem.objects.filter(draft_id=draft_pk).exists())
