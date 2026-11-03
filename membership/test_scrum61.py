"""SCRUM-61: Officer approves/rejects applications and manages roster.

Acceptance criteria:
  AC-1  Rejection requires a reason.
  AC-2  Approval promotes applicant to Member.
  AC-3  Roster updates reflect membership changes.

These tests sit alongside the broader review and recovery suites and are
focused exclusively on demonstrating that the three acceptance criteria are
met end-to-end through both the model layer and the HTTP views.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, get_role
from accounts.testing import make_user

from .models import (
    REAPPLY_WAIT,
    ApplicationStatus,
    MembershipApplication,
    next_application_allowed_at,
)


# ---------------------------------------------------------------------------
# AC-1  Rejection requires a reason
# ---------------------------------------------------------------------------

class RejectionRequiresReasonTests(TestCase):
    """AC-1: A rejection without a note must be blocked at every layer."""

    def setUp(self):
        self.officer = make_user("ac1-officer@example.com", Role.OFFICER)
        self.applicant = make_user("ac1-applicant@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="Please let me in."
        )

    def _post_review(self, decision, note=""):
        self.client.force_login(self.officer)
        return self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": decision, "note": note},
        )

    # --- model layer ---

    def test_model_raises_on_empty_note(self):
        with self.assertRaises(ValueError):
            self.application.review(self.officer, approve=False, note="")

    def test_model_raises_on_whitespace_only_note(self):
        with self.assertRaises(ValueError):
            self.application.review(self.officer, approve=False, note="   \t\n")

    def test_model_accepts_non_empty_note(self):
        self.application.review(self.officer, approve=False, note="We are full.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)

    def test_model_strips_surrounding_whitespace_from_note(self):
        self.application.review(self.officer, approve=False, note="  Good reason.  ")
        self.application.refresh_from_db()
        self.assertEqual(self.application.review_note, "Good reason.")

    # --- HTTP view layer ---

    def test_view_blocks_rejection_without_note(self):
        self._post_review("reject", note="")
        self.application.refresh_from_db()
        self.assertEqual(
            self.application.status,
            ApplicationStatus.PENDING,
            "Application must remain PENDING when no note is provided.",
        )

    def test_view_blocks_rejection_with_whitespace_note(self):
        self._post_review("reject", note="   ")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.PENDING)

    def test_view_records_rejection_with_valid_note(self):
        self._post_review("reject", note="Not this semester.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
        self.assertEqual(self.application.review_note, "Not this semester.")
        self.assertEqual(self.application.reviewed_by, self.officer)
        self.assertIsNotNone(self.application.reviewed_at)

    def test_view_shows_error_message_when_note_missing(self):
        """The officer should see an error flash when they forget the note."""
        response = self._post_review("reject", note="")
        # Must redirect to the application list.
        self.assertEqual(response.status_code, 302)
        # Follow and check for the error.
        follow = self.client.get(response["Location"])
        msgs = [str(m) for m in follow.context["messages"]]
        self.assertTrue(
            any("reason" in m.lower() for m in msgs),
            f"Expected a 'reason' error in flash messages, got: {msgs}",
        )

    def test_reason_is_stored_and_visible_on_application_list(self):
        """Officer sees the rejection reason in the reviewed-applications table."""
        self._post_review("reject", note="Come to a meeting first.")
        response = self.client.get(reverse("membership:application_list"))
        self.assertContains(response, "Come to a meeting first.")
        self.assertContains(response, self.officer.email)

    def test_approved_application_stores_no_mandatory_note(self):
        """Approval does not need a note; note remains empty."""
        self._post_review("approve", note="")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)
        self.assertEqual(self.application.review_note, "")

    def test_only_officers_can_reject(self):
        """A regular member must not be able to reject an application."""
        member = make_user("ac1-member@example.com", Role.MEMBER)
        self.client.force_login(member)
        response = self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": "No reason needed from a non-officer."},
        )
        self.assertEqual(response.status_code, 403)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.PENDING)

    def test_application_cannot_be_rejected_twice(self):
        """A decision is final; re-rejecting must not overwrite the first one."""
        self._post_review("reject", note="First rejection.")
        self.application.refresh_from_db()
        first_at = self.application.reviewed_at

        second_officer = make_user("ac1-officer2@example.com", Role.OFFICER)
        self.client.force_login(second_officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": "Overwrite attempt."},
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.review_note, "First rejection.")
        self.assertEqual(self.application.reviewed_at, first_at)


# ---------------------------------------------------------------------------
# AC-2  Approval promotes applicant to Member
# ---------------------------------------------------------------------------

class ApprovalPromotesToMemberTests(TestCase):
    """AC-2: Approving an application must promote the applicant to Member."""

    def setUp(self):
        self.officer = make_user("ac2-officer@example.com", Role.OFFICER)
        self.applicant = make_user("ac2-applicant@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="I want to join."
        )

    def _approve(self, note=""):
        self.client.force_login(self.officer)
        return self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "approve", "note": note},
        )

    # --- model layer ---

    def test_model_approve_sets_member_role(self):
        self.application.review(self.officer, approve=True)
        self.assertEqual(get_role(self.applicant), Role.MEMBER)

    def test_model_approve_does_not_demote_officer(self):
        """An officer with a pending application keeps their role on approval."""
        officer_app = MembershipApplication.objects.create(
            user=self.officer, statement="Test"
        )
        officer_app.review(self.officer, approve=True)
        self.assertEqual(get_role(self.officer), Role.OFFICER)

    def test_model_approve_activates_inactive_account(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.application.review(self.officer, approve=True)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

    def test_model_approve_marks_application_approved(self):
        self.application.review(self.officer, approve=True)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)
        self.assertEqual(self.application.reviewed_by, self.officer)
        self.assertIsNotNone(self.application.reviewed_at)
        self.assertFalse(self.application.access_update_pending)

    # --- HTTP view layer ---

    def test_view_approve_promotes_to_member(self):
        self._approve()
        self.assertEqual(get_role(self.applicant), Role.MEMBER)

    def test_view_approve_activates_inactive_account(self):
        self.applicant.is_active = False
        self.applicant.save()
        self._approve()
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

    def test_view_approve_shows_success_message(self):
        response = self._approve()
        self.assertEqual(response.status_code, 302)
        follow = self.client.get(response["Location"])
        msgs = [str(m) for m in follow.context["messages"]]
        self.assertTrue(
            any("approved" in m.lower() for m in msgs),
            f"Expected an approval confirmation message, got: {msgs}",
        )

    def test_view_approve_records_reviewer(self):
        self._approve()
        self.application.refresh_from_db()
        self.assertEqual(self.application.reviewed_by, self.officer)

    def test_approved_applicant_cannot_apply_again(self):
        """Once a member, the user should not be able to resubmit an application."""
        self._approve()
        self.client.force_login(self.applicant)
        self.client.post(
            reverse("membership:apply"), {"statement": "Apply again?"}
        )
        # Only the original approved application should exist.
        self.assertEqual(
            MembershipApplication.objects.filter(user=self.applicant).count(), 1
        )

    def test_approved_member_sees_already_member_on_apply_page(self):
        """A member visiting the apply page should see a friendly message."""
        self._approve()
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("membership:apply"))
        self.assertContains(response, "already a member")

    def test_only_officers_can_approve(self):
        member = make_user("ac2-member@example.com", Role.MEMBER)
        self.client.force_login(member)
        response = self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "approve"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def test_invalid_decision_leaves_application_pending(self):
        self.client.force_login(self.officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "maybe"},
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.PENDING)

    def test_application_cannot_be_approved_twice(self):
        self._approve()
        second_officer = make_user("ac2-officer2@example.com", Role.OFFICER)
        self.client.force_login(second_officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": "Overwrite attempt."},
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)

    def test_rejection_activates_account_without_promoting(self):
        """Rejected applicants are activated so they can view the reason, but
        remain as APPLICANT — not promoted to MEMBER."""
        self.applicant.is_active = False
        self.applicant.save()
        self.client.force_login(self.officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": "Not this time."},
        )
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)


# ---------------------------------------------------------------------------
# AC-3  Roster updates reflect membership changes
# ---------------------------------------------------------------------------

class RosterReflectsMembershipChangesTests(TestCase):
    """AC-3: The roster must show newly approved members and exclude applicants."""

    def setUp(self):
        self.officer = make_user("ac3-officer@example.com", Role.OFFICER)
        self.applicant = make_user("ac3-applicant@example.com")
        self.application = MembershipApplication.objects.create(
            user=self.applicant, statement="Join robotics."
        )
        # A second officer who will browse the roster as an existing member.
        self.roster_url = reverse("membership:roster")

    def _approve(self):
        self.client.force_login(self.officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "approve"},
        )

    def _reject(self, note="Not now."):
        self.client.force_login(self.officer)
        self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": "reject", "note": note},
        )

    # --- access control ---

    def test_applicant_cannot_access_roster_before_approval(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.roster_url).status_code, 403)

    def test_rejected_applicant_cannot_access_roster(self):
        self._reject()
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.roster_url).status_code, 403)

    def test_approved_member_can_access_roster(self):
        self._approve()
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.roster_url).status_code, 200)

    # --- roster content ---

    def test_approved_member_appears_on_roster(self):
        self._approve()
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url)
        self.assertContains(response, self.applicant.email)

    def test_pending_applicant_does_not_appear_on_roster(self):
        """Before a decision the applicant must not be listed on the roster."""
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url)
        self.assertNotContains(response, self.applicant.email)

    def test_rejected_applicant_does_not_appear_on_roster(self):
        self._reject()
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url)
        self.assertNotContains(response, self.applicant.email)

    def test_roster_shows_officers_and_admins_too(self):
        admin = make_user("ac3-admin@example.com", Role.ADMIN)
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url)
        self.assertContains(response, self.officer.email)
        self.assertContains(response, admin.email)

    # --- roster search ---

    def test_roster_search_finds_member_by_email(self):
        self._approve()
        self.client.force_login(self.officer)
        response = self.client.get(
            self.roster_url, {"q": "ac3-applicant"}
        )
        self.assertContains(response, self.applicant.email)

    def test_roster_search_excludes_non_matching_members(self):
        self._approve()
        other = make_user("ac3-other@example.com", Role.MEMBER)
        self.client.force_login(self.officer)
        response = self.client.get(
            self.roster_url, {"q": "ac3-applicant"}
        )
        self.assertNotContains(response, other.email)

    def test_roster_role_filter_shows_only_officers(self):
        self._approve()
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url, {"role": Role.OFFICER})
        self.assertContains(response, self.officer.email)
        self.assertNotContains(response, self.applicant.email)

    def test_roster_role_filter_shows_only_members(self):
        self._approve()
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url, {"role": Role.MEMBER})
        self.assertContains(response, self.applicant.email)
        self.assertNotContains(response, self.officer.email)

    def test_roster_invalid_role_filter_shows_all_roster_roles(self):
        self._approve()
        self.client.force_login(self.officer)
        response = self.client.get(self.roster_url, {"role": "applicant"})
        # Applicant is not a roster role; filtering by it should show all members.
        self.assertContains(response, self.applicant.email)
        self.assertContains(response, self.officer.email)


# ---------------------------------------------------------------------------
# AC-1 + AC-2 + AC-3  End-to-end officer workflow
# ---------------------------------------------------------------------------

class OfficerWorkflowEndToEndTests(TestCase):
    """Full officer workflow: review applications, check roster reflects result."""

    def setUp(self):
        self.officer = make_user("e2e-officer@example.com", Role.OFFICER)

    def test_full_approval_flow(self):
        """Applicant applies → officer approves → member on roster."""
        applicant = make_user("e2e-alice@example.com")
        app = MembershipApplication.objects.create(user=applicant, statement="I love robotics.")

        roster_url = reverse("membership:roster")
        review_url = reverse("membership:review_application", args=[app.pk])

        # Applicant cannot see roster yet.
        self.client.force_login(applicant)
        self.assertEqual(self.client.get(roster_url).status_code, 403)

        # Officer sees the application.
        self.client.force_login(self.officer)
        list_response = self.client.get(reverse("membership:application_list"))
        self.assertContains(list_response, "e2e-alice@example.com")

        # Officer approves.
        self.client.post(review_url, {"decision": "approve"})

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.APPROVED)
        self.assertEqual(get_role(applicant), Role.MEMBER)

        # New member can see roster and is listed on it.
        self.client.force_login(applicant)
        roster_response = self.client.get(roster_url)
        self.assertEqual(roster_response.status_code, 200)
        self.assertContains(roster_response, "e2e-alice@example.com")

    def test_full_rejection_flow(self):
        """Applicant applies → officer rejects with reason → applicant sees reason →
        applicant can reapply after the wait → roster still excludes them."""
        applicant = make_user("e2e-bob@example.com")
        app = MembershipApplication.objects.create(user=applicant, statement="Let me in.")

        review_url = reverse("membership:review_application", args=[app.pk])
        roster_url = reverse("membership:roster")
        apply_url = reverse("membership:apply")

        # Officer rejects without a reason → blocked.
        self.client.force_login(self.officer)
        self.client.post(review_url, {"decision": "reject", "note": ""})
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PENDING)

        # Officer rejects with a valid reason.
        self.client.post(review_url, {"decision": "reject", "note": "Come to a meeting."})
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REJECTED)
        self.assertEqual(app.review_note, "Come to a meeting.")

        # Applicant is still APPLICANT, not MEMBER.
        self.assertEqual(get_role(applicant), Role.APPLICANT)
        # Applicant account is activated so they can see the reason.
        applicant.refresh_from_db()
        self.assertTrue(applicant.is_active)

        # Applicant can see the rejection reason.
        self.client.force_login(applicant)
        apply_page = self.client.get(apply_url)
        self.assertContains(apply_page, "Not approved")
        self.assertContains(apply_page, "Come to a meeting.")

        # Applicant cannot access roster.
        self.assertEqual(self.client.get(roster_url).status_code, 403)

        # Still within the wait period — cannot reapply.
        self.assertIsNotNone(next_application_allowed_at(applicant))
        self.client.post(apply_url, {"statement": "Too soon."})
        self.assertEqual(
            MembershipApplication.objects.filter(user=applicant).count(), 1
        )

        # Age the rejection past the wait.
        MembershipApplication.objects.filter(pk=app.pk).update(
            reviewed_at=timezone.now() - REAPPLY_WAIT - timedelta(minutes=5)
        )
        self.assertIsNone(next_application_allowed_at(applicant))

        # Applicant can now reapply.
        self.client.post(apply_url, {"statement": "Second try."})
        self.assertEqual(
            MembershipApplication.objects.filter(user=applicant).count(), 2
        )
        new_app = MembershipApplication.objects.filter(user=applicant).first()
        self.assertEqual(new_app.status, ApplicationStatus.PENDING)
        self.assertEqual(new_app.statement, "Second try.")

        # Applicant STILL cannot access the roster.
        self.assertEqual(self.client.get(roster_url).status_code, 403)

    def test_application_list_status_filter(self):
        """Officer can filter the application list by status."""
        alice = make_user("e2e-filter-alice@example.com")
        bob = make_user("e2e-filter-bob@example.com")
        charlie = make_user("e2e-filter-charlie@example.com")

        app_alice = MembershipApplication.objects.create(user=alice, statement="A")
        app_bob = MembershipApplication.objects.create(user=bob, statement="B")
        app_charlie = MembershipApplication.objects.create(user=charlie, statement="C")

        # Approve Alice, reject Bob, leave Charlie pending.
        app_alice.review(self.officer, approve=True)
        app_bob.review(self.officer, approve=False, note="No capacity.")

        self.client.force_login(self.officer)
        list_url = reverse("membership:application_list")

        # Filter: pending → only Charlie.
        response = self.client.get(list_url, {"status": "pending"})
        self.assertContains(response, charlie.email)
        self.assertNotContains(response, alice.email)
        self.assertNotContains(response, bob.email)

        # Filter: approved → only Alice.
        response = self.client.get(list_url, {"status": "approved"})
        self.assertContains(response, alice.email)
        self.assertNotContains(response, charlie.email)
        self.assertNotContains(response, bob.email)

        # Filter: rejected → only Bob.
        response = self.client.get(list_url, {"status": "rejected"})
        self.assertContains(response, bob.email)
        self.assertNotContains(response, alice.email)
        self.assertNotContains(response, charlie.email)

    def test_application_list_search_by_email(self):
        """Officer can search the application list by applicant email."""
        alice = make_user("e2e-search-alice@example.com")
        bob = make_user("e2e-search-bob@example.com")

        MembershipApplication.objects.create(user=alice, statement="A")
        MembershipApplication.objects.create(user=bob, statement="B")

        self.client.force_login(self.officer)
        list_url = reverse("membership:application_list")

        response = self.client.get(list_url, {"q": "search-alice"})
        self.assertContains(response, alice.email)
        self.assertNotContains(response, bob.email)

    def test_member_detail_page_is_accessible_after_approval(self):
        """After approval the officer can view the new member's detail page."""
        applicant = make_user("e2e-detail@example.com")
        app = MembershipApplication.objects.create(user=applicant, statement="Hi")
        app.review(self.officer, approve=True)

        from accounts.models import Profile
        profile = Profile.objects.get(user=applicant)

        self.client.force_login(self.officer)
        response = self.client.get(
            reverse("membership:member_detail", args=[profile.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "e2e-detail@example.com")
