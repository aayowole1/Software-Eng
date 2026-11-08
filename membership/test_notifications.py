"""Tests for membership decision email notifications (SCRUM-79)."""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user

from .models import ApplicationStatus, MembershipApplication


class ApplicationApprovedEmailTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("ada@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="I want to join."
        )
        self.client.force_login(self.officer)

    def _review(self, decision, note=""):
        return self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": decision, "note": note},
        )

    def test_approval_sends_one_email(self):
        self._review("approve")
        self.assertEqual(len(mail.outbox), 1)

    def test_approval_email_recipient_is_applicant(self):
        self._review("approve")
        self.assertIn("ada@example.com", mail.outbox[0].to)

    def test_approval_email_subject_mentions_approved(self):
        self._review("approve")
        self.assertIn("approved", mail.outbox[0].subject.lower())

    def test_approval_email_body_greets_applicant(self):
        self._review("approve")
        self.assertIn(self.applicant.username, mail.outbox[0].body)

    def test_approval_email_body_mentions_sign_in(self):
        self._review("approve")
        self.assertIn("sign in", mail.outbox[0].body.lower())

    def test_approval_email_does_not_include_review_note(self):
        self._review("approve")
        # No note is set on approval, but we also verify no stray content
        self.assertNotIn("None", mail.outbox[0].body)


class ApplicationRejectedEmailTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("ada@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="I want to join."
        )
        self.client.force_login(self.officer)

    def _review(self, note="Please attend a meeting first."):
        return self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": note},
        )

    def test_rejection_sends_one_email(self):
        self._review()
        self.assertEqual(len(mail.outbox), 1)

    def test_rejection_email_recipient_is_applicant(self):
        self._review()
        self.assertIn("ada@example.com", mail.outbox[0].to)

    def test_rejection_email_subject_mentions_not_approved(self):
        self._review()
        self.assertIn("not approved", mail.outbox[0].subject.lower())

    def test_rejection_email_body_greets_applicant(self):
        self._review()
        self.assertIn(self.applicant.username, mail.outbox[0].body)

    def test_rejection_email_body_includes_reason(self):
        self._review("Please attend a meeting first.")
        self.assertIn("Please attend a meeting first.", mail.outbox[0].body)

    def test_rejection_email_mentions_reapply(self):
        self._review()
        self.assertIn("apply again", mail.outbox[0].body.lower())

    def test_failed_review_sends_no_email(self):
        """A review that is rejected by the model does not send a notification."""
        # Submit a rejection without a reason; the form is invalid, no review occurs.
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": ""},
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_already_reviewed_application_sends_no_second_email(self):
        self._review()
        self.assertEqual(len(mail.outbox), 1)
        # A second review attempt is rejected; no additional email is sent.
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "approve"},
        )
        self.assertEqual(len(mail.outbox), 1)


class NotificationDeliveryFailureTests(TestCase):
    """The review decision is not rolled back when email delivery fails."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("ada@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="I want to join."
        )
        self.client.force_login(self.officer)

    def test_approval_decision_persists_even_when_email_raises(self):
        from unittest.mock import patch
        from membership import emails as membership_emails

        with patch.object(membership_emails, "send_mail", side_effect=Exception("SMTP down")):
            self.client.post(
                reverse("membership:review_application", args=[self.application.pk]),
                {"decision": "approve"},
            )

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)

    def test_rejection_decision_persists_even_when_email_raises(self):
        from unittest.mock import patch
        from membership import emails as membership_emails

        with patch.object(membership_emails, "send_mail", side_effect=Exception("SMTP down")):
            self.client.post(
                reverse("membership:review_application", args=[self.application.pk]),
                {"decision": "reject", "note": "Not this time."},
            )

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
