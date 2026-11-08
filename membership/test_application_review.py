"""Unit tests for membership/models.py — MembershipApplication model methods."""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, get_role
from accounts.testing import make_user

from .models import ApplicationStatus, MembershipApplication


class MembershipApplicationReviewTests(TestCase):
    """Direct unit tests for MembershipApplication.review()."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("ada@example.com")
        self.app = MembershipApplication.objects.create(user=self.applicant, statement="I want to join.")

    def test_is_pending_true_before_review(self):
        self.assertTrue(self.app.is_pending)

    def test_approve_sets_status_and_reviewer(self):
        self.app.review(self.officer, approve=True)
        self.assertEqual(self.app.status, ApplicationStatus.APPROVED)
        self.assertEqual(self.app.reviewed_by, self.officer)
        self.assertIsNotNone(self.app.reviewed_at)

    def test_approve_activates_inactive_account(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.app.review(self.officer, approve=True)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

    def test_approve_promotes_applicant_to_member(self):
        self.app.review(self.officer, approve=True)
        self.assertEqual(get_role(self.applicant), Role.MEMBER)

    def test_approve_does_not_demote_officer(self):
        officer_app = MembershipApplication.objects.create(user=self.officer, statement="Testing")
        officer_app.review(self.officer, approve=True)
        self.assertEqual(get_role(self.officer), Role.OFFICER)

    def test_reject_sets_status_and_stores_reason(self):
        self.app.review(self.officer, approve=False, note="Not this semester.")
        self.assertEqual(self.app.status, ApplicationStatus.REJECTED)
        self.assertEqual(self.app.review_note, "Not this semester.")
        self.assertEqual(self.app.reviewed_by, self.officer)

    def test_reject_activates_account_as_applicant(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.app.review(self.officer, approve=False, note="Come to a meeting first.")
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def test_reject_without_note_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.app.review(self.officer, approve=False, note="")

    def test_reject_with_whitespace_only_note_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.app.review(self.officer, approve=False, note="   ")

    def test_reviewing_already_reviewed_application_raises(self):
        self.app.review(self.officer, approve=True)
        with self.assertRaises(ValueError):
            self.app.review(self.officer, approve=False, note="Too late.")

    def test_is_pending_false_after_approval(self):
        self.app.review(self.officer, approve=True)
        self.assertFalse(self.app.is_pending)

    def test_review_note_defaults_to_empty_on_approve(self):
        self.app.review(self.officer, approve=True)
        self.assertEqual(self.app.review_note, "")

    def test_review_timestamps_are_set(self):
        # MongoDB stores milliseconds, so compare from the start of this millisecond.
        before = timezone.now()
        before = before.replace(microsecond=before.microsecond // 1000 * 1000)
        self.app.review(self.officer, approve=True)
        after = timezone.now()
        self.assertGreaterEqual(self.app.reviewed_at, before)
        self.assertLessEqual(self.app.reviewed_at, after)

    def test_note_is_stripped_of_surrounding_whitespace(self):
        self.app.review(self.officer, approve=False, note="  Valid reason.  ")
        self.app.refresh_from_db()
        self.assertEqual(self.app.review_note, "Valid reason.")
