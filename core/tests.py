from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from membership.models import MembershipApplication


class CoreTests(TestCase):
    def test_home_is_public(self):
        self.assertContains(self.client.get(reverse("core:home")), "Create an account")

    def test_home_redirects_signed_in_users(self):
        self.client.force_login(make_user("ada@example.com"))
        self.assertRedirects(self.client.get(reverse("core:home")), reverse("core:dashboard"))

    def test_health(self):
        self.assertEqual(self.client.get(reverse("core:health")).json(), {"status": "ok"})

    def test_dashboard_requires_sign_in(self):
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

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
