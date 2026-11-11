from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee
from membership.models import MembershipApplication, REAPPLY_WAIT


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


class AboutSectionTests(TestCase):
    """SCRUM-98: About section on the signed-out dashboard."""

    def _get(self):
        return self.client.get(reverse("core:dashboard"))

    @override_settings(ORG_NAME="Test Org")
    def test_signed_out_sees_org_name(self):
        self.assertContains(self._get(), "Test Org")

    @override_settings(ORG_MISSION="Empowering students everywhere")
    def test_signed_out_sees_org_mission(self):
        self.assertContains(self._get(), "Empowering students everywhere")

    @override_settings(ORG_BENEFITS=["Networking", "Leadership"])
    def test_signed_out_sees_org_benefits(self):
        response = self._get()
        self.assertContains(response, "Networking")
        self.assertContains(response, "Leadership")

    @override_settings(ORG_CONTACT_EMAIL="officers@example.com")
    def test_signed_out_sees_contact_email_as_mailto(self):
        response = self._get()
        self.assertContains(response, "mailto:officers@example.com")
        self.assertContains(response, "officers@example.com")

    @override_settings(ORG_CONTACT_EMAIL="")
    def test_contact_fallback_when_email_empty(self):
        response = self._get()
        self.assertContains(response, "Contact an officer after you sign in")
        self.assertNotContains(response, "mailto:")

    def test_waiting_period_follows_reapply_wait(self):
        days = REAPPLY_WAIT.days
        response = self._get()
        self.assertContains(response, f"{days} day")

    def test_signed_out_member_only_content_hidden(self):
        response = self._get()
        self.assertNotContains(response, "Recent announcements")
        self.assertNotContains(response, "My tasks")
        self.assertNotContains(response, "Upcoming events")
        self.assertNotContains(response, "My committees")

    def test_signed_in_about_section_not_shown(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "about-section")

    @override_settings(ORG_NAME="Visible Org", ORG_MISSION="Our mission")
    def test_signed_in_does_not_see_org_name_or_mission(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "about-section")
        # The org name may appear in the page title/navigation, so we check
        # specifically the About section content doesn't bleed through
        self.assertNotContains(response, "Our mission")
