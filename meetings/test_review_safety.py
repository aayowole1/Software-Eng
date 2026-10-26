"""Review decision conflicts against the standalone MongoDB test database."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import OperationalError, close_old_connections
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from meetings.models import DraftStatus, MeetingDraft


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MeetingReviewSafetyTests(TestCase):
    def setUp(self):
        self.officer = make_user("meeting-reviewer@example.com", Role.OFFICER)
        self.other = make_user("other-reviewer@example.com", Role.OFFICER)
        self.draft = MeetingDraft.objects.create(
            title="Synthetic meeting", notes="Synthetic notes", created_by=self.officer,
        )

    def test_stale_review_cannot_replace_approval_or_its_metadata(self):
        stale = MeetingDraft.objects.get(pk=self.draft.pk)
        self.draft.review(self.officer, DraftStatus.APPROVED, "Accepted by first reviewer")
        expected = (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note)

        with self.assertRaisesMessage(ValueError, "Only drafts pending review"):
            stale.review(self.other, DraftStatus.REJECTED, "Stale rejection")

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, DraftStatus.APPROVED)
        self.assertEqual(
            (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note), expected,
        )

    def test_invalid_decision_does_not_change_pending_draft(self):
        with self.assertRaisesMessage(ValueError, "Invalid review decision"):
            self.draft.review(self.officer, "invalid")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, DraftStatus.PENDING_REVIEW)
        self.assertIsNone(self.draft.reviewed_by_id)
        self.assertIsNone(self.draft.reviewed_at)

    def test_failed_decision_write_leaves_pending_draft_retryable(self):
        with patch("django.db.models.query.QuerySet.update", side_effect=OperationalError("Synthetic write failure")):
            with self.assertRaises(OperationalError):
                self.draft.review(self.officer, DraftStatus.APPROVED, "First attempt")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, DraftStatus.PENDING_REVIEW)
        self.assertIsNone(self.draft.reviewed_by_id)
        self.assertIsNone(self.draft.reviewed_at)
        self.draft.review(self.officer, DraftStatus.APPROVED, "Retry")
        self.assertEqual(self.draft.status, DraftStatus.APPROVED)
        self.assertEqual(self.draft.review_note, "Retry")

    def test_actual_competing_reviews_record_exactly_one_decision(self):
        barrier = Barrier(2)

        def submit(user, decision):
            close_old_connections()
            try:
                draft = MeetingDraft.objects.get(pk=self.draft.pk)
                barrier.wait(timeout=10)
                try:
                    draft.review(user, decision, decision)
                except ValueError:
                    return "conflict"
                return decision
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(submit, self.officer, DraftStatus.APPROVED)
            second = workers.submit(submit, self.other, DraftStatus.REJECTED)
            results = [first.result(timeout=20), second.result(timeout=20)]

        self.assertEqual(results.count("conflict"), 1)
        winner = next(result for result in results if result != "conflict")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, winner)
        self.assertEqual(self.draft.review_note, winner)
        self.assertEqual(
            self.draft.reviewed_by_id,
            self.officer.pk if winner == DraftStatus.APPROVED else self.other.pk,
        )

    def test_losing_http_review_redirects_with_truthful_conflict_feedback(self):
        stale = MeetingDraft.objects.get(pk=self.draft.pk)
        self.draft.review(self.officer, DraftStatus.APPROVED, "First decision")
        self.client.force_login(self.other)
        # This models a request that loaded the pending draft before another
        # reviewer committed. Related item editing is not a transaction.
        with patch("meetings.views.get_object_or_404", return_value=stale):
            response = self.client.post(
                reverse("meetings:review", args=[self.draft.pk]),
                {"decision": DraftStatus.REJECTED, "note": "Stale", "new_items": ""},
            )
        self.assertRedirects(response, reverse("meetings:detail", args=[self.draft.pk]))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, DraftStatus.APPROVED)
        self.assertEqual(self.draft.reviewed_by_id, self.officer.pk)
        self.assertIn("status changed during review", str(list(response.wsgi_request._messages)[0]))
