"""Unit tests for membership/models.py helper functions.

Complements the integration-level coverage in tests.py with focused tests on
inactive_account_message(), next_application_allowed_at(), and
purge_old_rejected_applications().
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .models import (
    REAPPLY_WAIT,
    REJECTED_RETENTION,
    ApplicationStatus,
    MembershipApplication,
    inactive_account_message,
    next_application_allowed_at,
    purge_old_rejected_applications,
)


class InactiveAccountMessageTests(TestCase):
    """Unit tests for inactive_account_message()."""

    def test_no_applications_returns_generic_inactive_message(self):
        user = make_user("new@example.com")
        msg = inactive_account_message(user)
        self.assertIn("inactive", msg.lower())

    def test_pending_application_mentions_pending(self):
        user = make_user("pending@example.com")
        MembershipApplication.objects.create(user=user, statement="Hi")
        msg = inactive_account_message(user)
        self.assertIn("pending", msg.lower())
        self.assertIn("officer", msg.lower())

    def test_rejected_application_returns_inactive_message(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("rejected@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=False, note="Not yet.")
        # After rejection the account is activated; the function is still useful
        # if it's deactivated again later.
        user.is_active = False
        user.save()
        msg = inactive_account_message(user)
        self.assertIn("inactive", msg.lower())

    def test_approved_application_returns_inactive_message(self):
        # Approved accounts are active, but the function should still behave
        # gracefully if called for an approved-but-then-disabled account.
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("member@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=True)
        user.is_active = False
        user.save()
        msg = inactive_account_message(user)
        self.assertIn("inactive", msg.lower())

    def test_multiple_applications_uses_most_recent_one(self):
        user = make_user("multi@example.com")
        officer = make_user("officer@example.com", Role.OFFICER)
        app1 = MembershipApplication.objects.create(user=user, statement="First")
        app1.review(officer, approve=False, note="Not yet.")
        # Age the first rejection so the wait is over.
        MembershipApplication.objects.filter(pk=app1.pk).update(
            reviewed_at=timezone.now() - REAPPLY_WAIT - timedelta(minutes=1)
        )
        # Second pending application.
        MembershipApplication.objects.create(user=user, statement="Second")
        msg = inactive_account_message(user)
        # Most recent is pending, so the message should say pending.
        self.assertIn("pending", msg.lower())


class NextApplicationAllowedAtTests(TestCase):
    """Unit tests for next_application_allowed_at()."""

    def test_no_applications_returns_none(self):
        user = make_user("none@example.com")
        self.assertIsNone(next_application_allowed_at(user))

    def test_pending_application_returns_none(self):
        user = make_user("pending@example.com")
        MembershipApplication.objects.create(user=user, statement="Hi")
        self.assertIsNone(next_application_allowed_at(user))

    def test_approved_application_returns_none(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("member@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=True)
        self.assertIsNone(next_application_allowed_at(user))

    def test_recent_rejection_returns_future_datetime(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("rejected@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=False, note="Not yet.")
        allowed_at = next_application_allowed_at(user)
        self.assertIsNotNone(allowed_at)
        self.assertGreater(allowed_at, timezone.now())

    def test_old_rejection_returns_none(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("old_rejected@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=False, note="Not yet.")
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=timezone.now() - REAPPLY_WAIT - timedelta(minutes=1)
        )
        self.assertIsNone(next_application_allowed_at(user))

    def test_wait_expires_exactly_after_reapply_wait(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        user = make_user("edge@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(officer, approve=False, note="Not yet.")
        # Just inside the wait window.
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=timezone.now() - REAPPLY_WAIT + timedelta(minutes=1)
        )
        self.assertIsNotNone(next_application_allowed_at(user))
        # Just outside the wait window.
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=timezone.now() - REAPPLY_WAIT - timedelta(minutes=1)
        )
        self.assertIsNone(next_application_allowed_at(user))


class PurgeOldRejectedApplicationsTests(TestCase):
    """Unit tests for purge_old_rejected_applications()."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)

    def _rejected(self, email, days_ago):
        user = make_user(email)
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(self.officer, approve=False, note="Reason.")
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=timezone.now() - timedelta(days=days_ago)
        )
        return app

    def test_returns_zero_when_nothing_to_purge(self):
        count = purge_old_rejected_applications()
        self.assertEqual(count, 0)

    def test_deletes_old_rejected_applications(self):
        old = self._rejected("old@example.com", REJECTED_RETENTION.days + 1)
        count = purge_old_rejected_applications()
        self.assertEqual(count, 1)
        self.assertFalse(MembershipApplication.objects.filter(pk=old.pk).exists())

    def test_preserves_recent_rejections(self):
        recent = self._rejected("recent@example.com", REJECTED_RETENTION.days - 1)
        purge_old_rejected_applications()
        self.assertTrue(MembershipApplication.objects.filter(pk=recent.pk).exists())

    def test_does_not_delete_pending_or_approved_applications(self):
        user_p = make_user("pending@example.com")
        pending = MembershipApplication.objects.create(user=user_p, statement="Hi")
        user_a = make_user("approved@example.com")
        approved = MembershipApplication.objects.create(user=user_a, statement="Hi")
        approved.review(self.officer, approve=True)
        purge_old_rejected_applications()
        self.assertTrue(MembershipApplication.objects.filter(pk=pending.pk).exists())
        self.assertTrue(MembershipApplication.objects.filter(pk=approved.pk).exists())

    def test_user_accounts_are_kept_after_purge(self):
        old = self._rejected("purged@example.com", REJECTED_RETENTION.days + 1)
        user_pk = old.user_id
        purge_old_rejected_applications()
        self.assertTrue(User.objects.filter(pk=user_pk).exists())

    def test_accepts_explicit_now_argument(self):
        # One week ago from today, the purge was run with a custom 'now'.
        user = make_user("custom@example.com")
        app = MembershipApplication.objects.create(user=user, statement="Hi")
        app.review(self.officer, approve=False, note="Reason.")
        # Reviewed exactly at REJECTED_RETENTION + 1 day before our custom now.
        custom_now = timezone.now()
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=custom_now - REJECTED_RETENTION - timedelta(days=1)
        )
        count = purge_old_rejected_applications(now=custom_now)
        self.assertEqual(count, 1)


# Bring User into scope for the user-account-stays check.
from django.contrib.auth import get_user_model
User = get_user_model()
