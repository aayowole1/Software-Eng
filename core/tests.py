from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee
from events.models import Event
from meetings.models import DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication
from tasks.models import Task, TaskStatus


class CoreTests(TestCase):
    def test_home_is_public(self):
        self.assertContains(self.client.get(reverse("core:home")), "Create an account and apply")

    def test_dashboard_is_public(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How joining works")

    def test_public_dashboard_lists_committees_without_member_links(self):
        committee = Committee.objects.create(name="Events", description="Plans events")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Events")
        self.assertContains(response, "Plans events")
        self.assertNotContains(response, reverse("committees:detail", args=[committee.pk]))

    def test_members_get_committee_links(self):
        committee = Committee.objects.create(name="Events")
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, reverse("committees:detail", args=[committee.pk]))

    def test_signed_in_users_see_their_dashboard_at_home(self):
        self.client.force_login(make_user("ada@example.com"))
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Signed in as")
        self.assertNotContains(response, "How joining works")

    def test_health(self):
        self.assertEqual(self.client.get(reverse("core:health")).json(), {"status": "ok"})

    def test_applicant_dashboard_shows_application_status(self):
        user = make_user("ada@example.com")
        MembershipApplication.objects.create(user=user, statement="Hi")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("core:dashboard")), "Pending")

    def test_officer_dashboard_shows_pending_counts(self):
        MembershipApplication.objects.create(user=make_user("ada@example.com"), statement="Hi")
        self.client.force_login(make_user("officer@example.com", Role.OFFICER))
        self.assertContains(self.client.get(reverse("core:dashboard")), "1 membership application")

    def test_navigation_hides_officer_links_from_members(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, reverse("membership:application_list"))
        self.assertNotContains(response, reverse("accounts:user_list"))


class DashboardSummaryCardsTests(TestCase):
    """FR-6.1: summary cards visible to officers and admins."""

    def _dashboard(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("core:dashboard"))

    # --- visibility ---

    def test_officer_sees_summary_cards(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, "Active members")
        self.assertContains(response, "Upcoming events")
        self.assertContains(response, "Open tasks")
        self.assertContains(response, "Pending approvals")

    def test_admin_sees_summary_cards(self):
        admin = make_user("admin@example.com", Role.ADMIN)
        response = self._dashboard(admin)
        self.assertContains(response, "Active members")

    def test_member_does_not_see_summary_cards(self):
        member = make_user("member@example.com", Role.MEMBER)
        response = self._dashboard(member)
        self.assertNotContains(response, "Active members")

    def test_applicant_does_not_see_summary_cards(self):
        applicant = make_user("applicant@example.com")
        response = self._dashboard(applicant)
        self.assertNotContains(response, "Active members")

    def test_anonymous_does_not_see_summary_cards(self):
        response = self._dashboard()
        self.assertNotContains(response, "Active members")

    # --- active members count ---

    def test_active_members_count_includes_members_officers_admins(self):
        make_user("m@example.com", Role.MEMBER)
        make_user("o@example.com", Role.OFFICER)
        make_user("a@example.com", Role.ADMIN)
        officer = make_user("viewer@example.com", Role.OFFICER)
        # viewer is also an officer so total roster users visible = 4
        response = self._dashboard(officer)
        self.assertContains(response, ">4<")

    def test_active_members_excludes_applicants(self):
        make_user("applicant@example.com")  # role=applicant by default
        officer = make_user("officer@example.com", Role.OFFICER)
        # Only the officer counts
        response = self._dashboard(officer)
        self.assertContains(response, ">1<")

    def test_active_members_excludes_suspended(self):
        member = make_user("suspended@example.com", Role.MEMBER)
        Profile.objects.filter(user=member).update(is_suspended=True)
        officer = make_user("officer@example.com", Role.OFFICER)
        # Only officer counts; suspended member excluded
        response = self._dashboard(officer)
        self.assertContains(response, ">1<")

    def _active_members(self, viewer):
        return self._dashboard(viewer).context["summary_active_members"]

    def test_active_members_excludes_disabled_accounts(self):
        """Review: switched-off accounts aren't active, even with a member role."""
        disabled = make_user("disabled@example.com", Role.MEMBER)
        type(disabled).objects.filter(pk=disabled.pk).update(is_active=False)
        make_user("active@example.com", Role.MEMBER)
        officer = make_user("count-officer@example.com", Role.OFFICER)
        self.assertEqual(self._active_members(officer), 2)  # active member + officer

    def test_active_members_excludes_unfinished_membership_approvals(self):
        """Review: an approval whose account access is still updating isn't active yet."""
        pending = make_user("pending-access@example.com", Role.MEMBER)
        MembershipApplication.objects.create(
            user=pending, statement="Joining.", status=ApplicationStatus.APPROVED,
            access_update_pending=True,
        )
        officer = make_user("count-officer@example.com", Role.OFFICER)
        self.assertEqual(self._active_members(officer), 1)  # only the officer

    def test_active_members_excludes_suspension_in_progress(self):
        member = make_user("mid-suspension@example.com", Role.MEMBER)
        Profile.objects.filter(user=member).update(suspension_update_pending=True)
        officer = make_user("count-officer@example.com", Role.OFFICER)
        self.assertEqual(self._active_members(officer), 1)

    def test_active_members_counts_each_usable_role_once(self):
        make_user("count-member@example.com", Role.MEMBER)
        make_user("count-admin@example.com", Role.ADMIN)
        make_user("count-applicant@example.com")  # applicants never count
        officer = make_user("count-officer@example.com", Role.OFFICER)
        self.assertEqual(self._active_members(officer), 3)

    # --- upcoming events count ---

    def test_upcoming_events_count(self):
        future = timezone.now() + timezone.timedelta(days=1)
        Event.objects.create(title="Future", location="Hall", starts_at=future, created_by=None)
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, ">1<")

    def test_upcoming_events_excludes_past(self):
        past = timezone.now() - timezone.timedelta(days=1)
        Event.objects.create(title="Past", location="Hall", starts_at=past, created_by=None)
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, ">0<")

    def test_upcoming_events_excludes_cancelled(self):
        future = timezone.now() + timezone.timedelta(days=1)
        Event.objects.create(title="Cancelled", location="Hall", starts_at=future, cancelled=True, created_by=None)
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, ">0<")

    # --- open tasks count ---

    def test_open_tasks_count_excludes_done(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        Task.objects.create(title="Todo", status=TaskStatus.TODO, created_by=officer)
        Task.objects.create(title="Done", status=TaskStatus.DONE, created_by=officer)
        response = self._dashboard(officer)
        self.assertContains(response, ">1<")

    def test_open_tasks_counts_all_statuses_except_done(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        Task.objects.create(title="Todo", status=TaskStatus.TODO, created_by=officer)
        Task.objects.create(title="In Progress", status=TaskStatus.IN_PROGRESS, created_by=officer)
        response = self._dashboard(officer)
        self.assertContains(response, ">2<")

    # --- pending approvals count ---

    def test_pending_approvals_sums_applications_and_drafts(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        applicant = make_user("applicant@example.com")
        MembershipApplication.objects.create(user=applicant, statement="Hi", status=ApplicationStatus.PENDING)
        MeetingDraft.objects.create(title="Minutes", status=DraftStatus.PENDING_REVIEW, created_by=officer)
        response = self._dashboard(officer)
        self.assertContains(response, ">2<")

    def test_pending_approvals_excludes_reviewed_applications(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        applicant = make_user("applicant@example.com")
        MembershipApplication.objects.create(user=applicant, statement="Hi", status=ApplicationStatus.APPROVED)
        response = self._dashboard(officer)
        self.assertContains(response, ">0<")

    # --- links ---

    def test_summary_cards_link_to_roster(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, reverse("membership:roster"))

    def test_summary_cards_link_to_events(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, reverse("events:list"))

    def test_summary_cards_link_to_tasks(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, reverse("tasks:list"))

    def test_summary_cards_link_to_applications_and_meeting_drafts(self):
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self._dashboard(officer)
        self.assertContains(response, reverse("membership:application_list"))
        self.assertContains(response, reverse("meetings:list"))
