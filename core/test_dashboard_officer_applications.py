"""FR-6.1: the dashboard's Pending approvals include officer applications (FR-2.3)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from meetings.models import MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication
from officer_applications.models import OfficerApplication


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PendingOfficerApplicationTests(TestCase):
    def setUp(self):
        self.admin = make_user("pending-admin@example.com", Role.ADMIN)
        self.officer = make_user("pending-officer@example.com", Role.OFFICER)
        member_a = make_user("pending-a@example.com", Role.MEMBER)
        member_b = make_user("pending-b@example.com", Role.MEMBER)
        applicant = make_user("pending-applicant@example.com")
        OfficerApplication.objects.create(user=member_a, statement="I'd like to help.")
        OfficerApplication.objects.create(
            user=member_b, statement="Earlier request.", status=ApplicationStatus.REJECTED, review_note="Not this term.",
        )
        MembershipApplication.objects.create(user=applicant, statement="Please let me join.")
        MeetingDraft.objects.create(title="Pending draft", notes="Notes", created_by=self.officer)

    def dashboard(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("core:dashboard"))

    def test_total_counts_membership_and_officer_applications_and_drafts(self):
        response = self.dashboard(self.admin)
        self.assertEqual(response.context["pending_officer_applications"], 1)
        self.assertEqual(response.context["summary_pending_approvals"], 3)

    def test_attention_list_links_to_officer_applications(self):
        response = self.dashboard(self.admin)
        self.assertContains(response, "1 officer application</a> pending", html=False)
        self.assertContains(response, f'{reverse("membership:application_list")}?type=officer')
        self.assertNotContains(response, "an Admin reviews these")

    def test_officers_are_told_an_admin_reviews_officer_applications(self):
        response = self.dashboard(self.officer)
        self.assertEqual(response.context["summary_pending_approvals"], 3)
        self.assertContains(response, "an Admin reviews these")

    def test_members_do_not_see_the_count(self):
        member = make_user("pending-member@example.com", Role.MEMBER)
        response = self.dashboard(member)
        self.assertNotIn("pending_officer_applications", response.context)
        self.assertNotContains(response, "officer application</a> pending", html=False)
