from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee
from membership.models import MembershipApplication


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
