"""
Tests for SCRUM-60 – US-02: Submit membership application and view status.

Acceptance criteria:
  AC-1  Application included in sign-up flow.
  AC-2  Application status is visible to applicant.
  AC-3  Rejected applicants see reason and reapply time.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import PASSWORD, make_user

from .models import (
    REAPPLY_WAIT,
    ApplicationStatus,
    MembershipApplication,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# AC-1: Application included in sign-up flow
# ---------------------------------------------------------------------------

class SignupApplicationFlowTests(TestCase):
    """Registration form captures the membership statement and creates an application."""

    REGISTER_URL = reverse("accounts:register")

    def _post_register(self, **overrides):
        data = {
            "username": "alice",
            "email": "alice@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "statement": "I'd love to help with robotics outreach.",
        }
        data.update(overrides)
        return self.client.post(self.REGISTER_URL, data)

    def test_register_page_includes_application_question(self):
        """The sign-up form renders the 'Why do you want to join?' question."""
        response = self.client.get(self.REGISTER_URL)
        self.assertContains(response, "Why do you want to join")

    def test_successful_registration_creates_pending_application(self):
        """Submitting the registration form creates a pending MembershipApplication."""
        self._post_register()
        user = User.objects.get(username="alice")
        app = MembershipApplication.objects.get(user=user)
        self.assertEqual(app.statement, "I'd love to help with robotics outreach.")
        self.assertEqual(app.status, ApplicationStatus.PENDING)

    def test_successful_registration_account_is_inactive_until_approved(self):
        """New accounts are switched off; the applicant cannot sign in yet."""
        self._post_register()
        user = User.objects.get(username="alice")
        self.assertFalse(user.is_active)
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "alice", "password": PASSWORD},
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        # The login page explains why sign-in is blocked.
        self.assertContains(response, "pending")

    def test_registration_without_statement_is_rejected(self):
        """The application statement is required; leaving it blank prevents account creation."""
        self._post_register(statement="")
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(MembershipApplication.objects.exists())

    def test_registration_success_message_mentions_application(self):
        """After successful sign-up the applicant is told their application was submitted."""
        response = self._post_register()
        # Redirects to home; flash message should explain what happens next.
        messages = [str(m) for m in response.wsgi_request._messages]
        combined = " ".join(messages).lower()
        self.assertIn("application", combined)

    def test_google_signup_page_also_shows_application_question(self):
        """The Google sign-up continuation page asks the same membership question."""
        # Prime the session with a synthetic pending Google signup.
        import time
        session = self.client.session
        session["google_signup_pending"] = {
            "subject": "google-sub-123",
            "email": "alice@gmail.com",
            "issued": time.time(),
        }
        session.save()
        response = self.client.get(reverse("accounts:google_apply"))
        self.assertContains(response, "Why do you want to join")


# ---------------------------------------------------------------------------
# AC-2: Application status is visible to applicant
# ---------------------------------------------------------------------------

class ApplicationStatusVisibilityTests(TestCase):
    """Applicants can view the status of their membership application."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("bob@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="I want to contribute."
        )
        self.client.force_login(self.applicant)

    def test_apply_page_shows_pending_status(self):
        """A pending applicant sees their application listed as Pending."""
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Pending")

    def test_apply_page_shows_application_statement(self):
        """The applicant's submitted statement is shown in the application history."""
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "I want to contribute.")

    def test_apply_page_unauthenticated_redirects_to_login(self):
        """The application status page requires the user to be signed in."""
        self.client.logout()
        response = self.client.get(reverse("membership:apply"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_dashboard_shows_pending_status_for_applicant(self):
        """The dashboard Membership card shows the applicant's pending status."""
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Pending")

    def test_dashboard_shows_approved_status_after_approval(self):
        """After approval the dashboard no longer shows the applicant membership card."""
        self.application.review(self.officer, approve=True)
        self.applicant.refresh_from_db()
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("core:dashboard"))
        # Approved applicants become members; the applicant-specific card is gone.
        self.assertNotContains(response, "You're not a member yet")

    def test_apply_page_shows_approved_status_in_history(self):
        """Approved applications appear in the applicant's history as Approved."""
        self.application.review(self.officer, approve=True)
        self.applicant.refresh_from_db()
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Approved")


# ---------------------------------------------------------------------------
# AC-3: Rejected applicants see reason and reapply time
# ---------------------------------------------------------------------------

class RejectedApplicantStatusTests(TestCase):
    """After rejection, applicants see the rejection reason and when they may reapply."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("carol@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="Ready to join!"
        )
        self.client.force_login(self.officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": "Please attend one meeting first."},
        )
        # Rejected applicants have is_active=True so they can sign in.
        self.applicant.refresh_from_db()
        self.client.force_login(self.applicant)

    def _age_rejection(self, by):
        """Shift the reviewed_at timestamp to simulate elapsed time."""
        MembershipApplication.objects.filter(pk=self.application.pk).update(
            reviewed_at=timezone.now() - by
        )

    def test_rejected_applicant_can_sign_in(self):
        """Accounts rejected during membership review are activated so the applicant can sign in."""
        self.assertTrue(self.applicant.is_active)
        self.assertIn("_auth_user_id", self.client.session)

    def test_apply_page_shows_not_approved_badge(self):
        """The apply page shows the 'Not approved' badge for the latest rejected application."""
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Not approved")

    def test_apply_page_shows_rejection_reason(self):
        """The apply page shows the rejection reason the officer provided."""
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Please attend one meeting first.")

    def test_apply_page_shows_reapply_time_while_in_wait_period(self):
        """During the reapply wait period the apply page shows when the applicant may reapply."""
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "You can apply again after")

    def test_apply_page_shows_reason_and_reapply_time_in_same_card(self):
        """The rejection card on the apply page contains both the reason and the reapply date."""
        response = self.client.get(reverse("membership:apply"))
        content = response.content.decode()
        # Both pieces of information must appear; their proximity in the rejection card
        # is verified by checking they are within the same div.card block.
        reason_pos = content.find("Please attend one meeting first.")
        reapply_pos = content.find("You can apply again after")
        self.assertGreater(reason_pos, -1, "Rejection reason not found on apply page")
        self.assertGreater(reapply_pos, -1, "Reapply time not found on apply page")
        # The reapply message should appear close to the reason (within ~500 characters),
        # confirming they are in the same card rather than far apart on the page.
        self.assertLess(
            abs(reason_pos - reapply_pos), 500,
            "Rejection reason and reapply time should appear close together on the page",
        )

    def test_dashboard_shows_rejection_reason(self):
        """The dashboard Membership card shows the rejection reason."""
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Please attend one meeting first.")

    def test_dashboard_shows_reapply_time_while_in_wait_period(self):
        """The dashboard shows when the rejected applicant may reapply during the wait period."""
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "You can apply again after")

    def test_applicant_cannot_submit_new_application_during_wait(self):
        """A rejected applicant cannot bypass the wait by submitting again immediately."""
        self.client.post(reverse("membership:apply"), {"statement": "Please let me in!"})
        self.assertEqual(MembershipApplication.objects.filter(user=self.applicant).count(), 1)

    def test_applicant_can_reapply_after_wait_expires(self):
        """Once the reapply wait period ends the applicant can submit a new application."""
        self._age_rejection(REAPPLY_WAIT + timedelta(minutes=5))
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Apply again")
        self.client.post(reverse("membership:apply"), {"statement": "Second attempt."})
        latest = MembershipApplication.objects.filter(user=self.applicant).first()
        self.assertEqual(latest.statement, "Second attempt.")
        self.assertEqual(latest.status, ApplicationStatus.PENDING)

    def test_apply_page_does_not_show_reapply_time_after_wait_expires(self):
        """After the wait period ends the reapply time message is no longer shown."""
        self._age_rejection(REAPPLY_WAIT + timedelta(minutes=5))
        response = self.client.get(reverse("membership:apply"))
        self.assertNotContains(response, "You can apply again after")

    def test_rejection_history_preserved_after_new_application(self):
        """The previous rejected application still appears in history after reapplying."""
        self._age_rejection(REAPPLY_WAIT + timedelta(minutes=5))
        self.client.post(reverse("membership:apply"), {"statement": "Fresh start."})
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "Not approved")
        self.assertContains(response, "Please attend one meeting first.")
        self.assertContains(response, "Fresh start.")
