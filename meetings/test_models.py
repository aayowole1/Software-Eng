"""Unit tests for meetings/models.py — MeetingDraft and ActionItem model methods.

These target the model methods directly (generate, review, revise) without
going through the HTTP views, complementing the view-level tests in tests.py.
"""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .models import ActionItem, DraftStatus, MeetingDraft


SIMPLE_NOTES = (
    "We discussed the conference agenda.\n"
    "The speakers have been confirmed.\n"
    "Budget approval is still pending.\n"
    "Action: Reserve the main hall by end of week\n"
    "TODO - Send confirmation emails to speakers\n"
)


class MeetingDraftGenerateTests(TestCase):
    """Unit tests for MeetingDraft.generate()."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)

    def _draft(self, notes=SIMPLE_NOTES):
        return MeetingDraft.objects.create(
            title="Sprint Review",
            notes=notes,
            created_by=self.officer,
        )

    def test_generate_populates_summary(self):
        draft = self._draft()
        draft.generate()
        self.assertIsInstance(draft.summary, str)
        self.assertTrue(draft.summary)

    def test_generate_creates_action_items(self):
        draft = self._draft()
        draft.generate()
        self.assertEqual(draft.action_items.count(), 2)

    def test_generate_replaces_existing_action_items(self):
        draft = self._draft()
        draft.generate()
        first_items = list(draft.action_items.values_list("description", flat=True))
        # Run again with different notes.
        draft.notes = "Action: Completely new task\n"
        draft.generate()
        new_items = list(draft.action_items.values_list("description", flat=True))
        self.assertNotEqual(first_items, new_items)
        self.assertEqual(draft.action_items.count(), 1)
        self.assertIn("Completely new task", new_items)

    def test_generate_does_not_include_action_lines_in_summary(self):
        draft = self._draft()
        draft.generate()
        self.assertNotIn("Reserve the main hall", draft.summary)
        self.assertNotIn("Send confirmation emails", draft.summary)

    def test_generate_with_no_action_items_creates_no_action_item_records(self):
        draft = self._draft(notes="Just a regular sentence. And another one.")
        draft.generate()
        self.assertEqual(draft.action_items.count(), 0)

    def test_generate_persists_summary_to_database(self):
        draft = self._draft()
        draft.generate()
        refreshed = MeetingDraft.objects.get(pk=draft.pk)
        self.assertEqual(refreshed.summary, draft.summary)

    def test_action_items_have_sequential_positions(self):
        draft = self._draft()
        draft.generate()
        positions = list(draft.action_items.values_list("position", flat=True))
        self.assertEqual(positions, list(range(len(positions))))

    def test_action_items_default_to_accepted(self):
        draft = self._draft()
        draft.generate()
        self.assertTrue(all(item.accepted for item in draft.action_items.all()))


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
        before = timezone.now()
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


class MeetingDraftReviseTests(TestCase):
    """Unit tests for MeetingDraft.revise()."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.draft = MeetingDraft.objects.create(
            title="Sprint Review",
            notes=SIMPLE_NOTES,
            created_by=self.officer,
            status=DraftStatus.REVISION_REQUESTED,
            reviewed_by=self.officer,
            reviewed_at=timezone.now(),
            review_note="Add more detail.",
        )

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
        new_notes = "New discussion on strategy.\nAction: Revise the roadmap\n"
        self.draft.revise(new_notes)
        self.assertIn("strategy", self.draft.summary)
        actions = list(self.draft.action_items.values_list("description", flat=True))
        self.assertIn("Revise the roadmap", actions)

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


class ActionItemTests(TestCase):
    """Unit tests for ActionItem model defaults and behaviour."""

    def setUp(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        self.draft = MeetingDraft.objects.create(
            title="Test Draft",
            notes=SIMPLE_NOTES,
            created_by=officer,
        )
        self.draft.generate()

    def test_action_items_are_ordered_by_position(self):
        positions = list(self.draft.action_items.values_list("position", flat=True))
        self.assertEqual(positions, sorted(positions))

    def test_action_items_default_to_accepted_true(self):
        for item in self.draft.action_items.all():
            self.assertTrue(item.accepted)

    def test_action_item_can_be_unaccepted(self):
        item = self.draft.action_items.first()
        item.accepted = False
        item.save()
        item.refresh_from_db()
        self.assertFalse(item.accepted)

    def test_str_returns_description(self):
        item = self.draft.action_items.first()
        self.assertEqual(str(item), item.description)

    def test_deleting_draft_deletes_action_items(self):
        draft_pk = self.draft.pk
        self.draft.delete()
        self.assertFalse(ActionItem.objects.filter(draft_id=draft_pk).exists())
