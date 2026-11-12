"""FR-2.2: browse, search and filter the roster by name, role, committee and status."""

import csv
from io import StringIO

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from membership.models import MembershipApplication


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RosterFilterTests(TestCase):
    def setUp(self):
        self.admin = make_user("filter-admin@example.com", Role.ADMIN)
        self.officer = make_user("filter-officer@example.com", Role.OFFICER)
        self.mia = make_user("mia@example.com", Role.MEMBER)
        self.mia.first_name, self.mia.last_name = "Mia", "Okafor"
        self.mia.save()
        self.sam = make_user("sam@example.com", Role.MEMBER)
        Profile.objects.filter(user=self.sam).update(is_suspended=True)
        self.dee = make_user("dee@example.com", Role.MEMBER)
        type(self.dee).objects.filter(pk=self.dee.pk).update(is_active=False)
        self.pat = make_user("pat@example.com", Role.MEMBER)
        MembershipApplication.objects.create(user=self.pat, statement="Hi.", access_update_pending=True)
        self.events = Committee.objects.create(name="Events", created_by=self.officer)
        self.outreach = Committee.objects.create(name="Outreach", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.events, user=self.mia)
        CommitteeMember.objects.create(committee=self.outreach, user=self.sam)

    def emails(self, user, **params):
        self.client.force_login(user)
        response = self.client.get(reverse("membership:roster"), params)
        self.assertEqual(response.status_code, 200)
        return {profile.user.email for profile in response.context["members"]}, response

    def test_search_matches_first_and_last_name(self):
        self.assertEqual(self.emails(self.mia, q="okafor")[0], {"mia@example.com"})
        self.assertEqual(self.emails(self.mia, q="Mia")[0], {"mia@example.com"})

    def test_committee_filter_is_available_to_members(self):
        emails, response = self.emails(self.mia, committee=str(self.events.pk))
        self.assertEqual(emails, {"mia@example.com"})
        self.assertContains(response, 'id="committee-filter"')
        self.assertContains(response, "Outreach")

    def test_committee_filter_combines_with_role_and_search(self):
        self.assertEqual(self.emails(self.officer, committee=str(self.outreach.pk), role="member", q="sam")[0], {"sam@example.com"})
        self.assertEqual(self.emails(self.officer, committee=str(self.outreach.pk), role="officer")[0], set())

    def test_unknown_or_invalid_committee_is_ignored(self):
        everyone, _ = self.emails(self.officer)
        self.assertEqual(self.emails(self.officer, committee="not-an-id")[0], everyone)
        self.assertEqual(self.emails(self.officer, committee="0" * 24)[0], everyone)

    def test_status_filter_for_officers(self):
        expected = {
            "active": {"filter-admin@example.com", "filter-officer@example.com", "mia@example.com"},
            "suspended": {"sam@example.com"},
            "pending": {"pat@example.com"},
            "disabled": {"dee@example.com"},
        }
        for status, emails in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self.emails(self.officer, status=status)[0], emails)

    def test_officers_see_a_status_column(self):
        _, response = self.emails(self.officer, q="sam")
        self.assertContains(response, 'id="status-filter"')
        self.assertContains(response, "<th scope=\"col\">Status</th>", html=False)
        self.assertContains(response, "<td>Suspended</td>", html=False)

    def test_members_cannot_see_or_filter_by_status(self):
        everyone, response = self.emails(self.mia)
        self.assertNotContains(response, 'id="status-filter"')
        self.assertNotContains(response, "Suspended")
        self.assertEqual(self.emails(self.mia, status="suspended")[0], everyone)

    def test_csv_export_uses_the_same_filters(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("membership:export_roster_csv"), {"committee": str(self.outreach.pk), "status": "suspended"})
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual([(row["email"], row["status"]) for row in rows], [("sam@example.com", "suspended")])

    def test_filters_survive_pagination_links(self):
        _, response = self.emails(self.officer, committee=str(self.events.pk), status="active")
        self.assertIn(f"committee={self.events.pk}", response.context["query_string"])
        self.assertIn("status=active", response.context["query_string"])
