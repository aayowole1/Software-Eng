"""Tests for SCRUM-93: Admin CSV export of the roster (FR-2.4)."""

import csv
import datetime
from io import StringIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember


class RosterExportAccessTests(TestCase):
    """AC-6: Access control for the CSV export endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.officer = make_user("officer@example.com", Role.OFFICER)
        cls.member = make_user("member@example.com", Role.MEMBER)
        cls.applicant = make_user("applicant@example.com")
        cls.url = reverse("membership:export_roster_csv")

    def test_admin_can_download_csv(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_officer_gets_403(self):
        self.client.force_login(self.officer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_member_gets_403(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_applicant_gets_403(self):
        self.client.force_login(self.applicant)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_signed_out_user_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_suspended_admin_is_blocked(self):
        """A suspended account must not be able to export the roster (AC-6).

        EmailOrUsernameBackend.user_can_authenticate returns False for
        suspended users, so the AuthenticationMiddleware treats them as
        anonymous and login_required (inside role_required) redirects to login.
        """
        suspended_admin = make_user("suspended-admin@example.com", Role.ADMIN)
        Profile.objects.filter(user=suspended_admin).update(is_suspended=True)
        self.client.force_login(suspended_admin)
        response = self.client.get(self.url)
        # The backend rejects the suspended session → treated as anonymous → login redirect.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class RosterExportColumnsTests(TestCase):
    """AC-3: CSV columns contain the right data."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.member = make_user("alice@example.com", Role.MEMBER)
        cls.committee = Committee.objects.create(name="Finance", created_by=cls.admin)
        CommitteeMember.objects.create(committee=cls.committee, user=cls.member)
        cls.url = reverse("membership:export_roster_csv")

    def _get_rows(self, **params):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, params)
        content = b"".join(response.streaming_content if hasattr(response, "streaming_content") else [response.content])
        return list(csv.reader(StringIO(content.decode())))

    def test_header_row_has_correct_columns(self):
        rows = self._get_rows()
        self.assertEqual(rows[0], ["username", "email", "role", "committees", "date_joined", "status"])

    def test_data_row_has_username_and_email(self):
        rows = self._get_rows()
        usernames = [row[0] for row in rows[1:]]
        self.assertIn("alice@example.com", usernames)
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertEqual(alice_row[1], "alice@example.com")

    def test_role_column_uses_display_name(self):
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertEqual(alice_row[2], "Member")

    def test_committees_column_lists_committee_name(self):
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertIn("Finance", alice_row[3])

    def test_multiple_committees_separated_by_semicolons(self):
        second = Committee.objects.create(name="Events", created_by=self.admin)
        CommitteeMember.objects.create(committee=second, user=self.member)
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertIn(";", alice_row[3])
        # Clean up so other tests are not affected
        second.delete()

    def test_date_joined_matches_profile_created_at(self):
        profile = Profile.objects.get(user=self.member)
        expected = timezone.localtime(profile.created_at).strftime("%Y-%m-%d")
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertEqual(alice_row[4], expected)

    def test_status_active_for_non_suspended_member(self):
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertEqual(alice_row[5], "active")

    def test_status_suspended_for_suspended_member(self):
        Profile.objects.filter(user=self.member).update(is_suspended=True)
        rows = self._get_rows()
        alice_row = next(r for r in rows[1:] if r[0] == "alice@example.com")
        self.assertEqual(alice_row[5], "suspended")
        # Restore
        Profile.objects.filter(user=self.member).update(is_suspended=False)


class RosterExportFiltersTests(TestCase):
    """AC-2: Filters (search, role) are applied to the export."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.member1 = make_user("alpha@example.com", Role.MEMBER)
        cls.member2 = make_user("beta@example.com", Role.OFFICER)
        cls.url = reverse("membership:export_roster_csv")

    def _get_rows(self, **params):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, params)
        content = b"".join(response.streaming_content if hasattr(response, "streaming_content") else [response.content])
        return list(csv.reader(StringIO(content.decode())))

    def test_search_filter_limits_results(self):
        rows = self._get_rows(q="alpha")
        usernames = [r[0] for r in rows[1:]]
        self.assertIn("alpha@example.com", usernames)
        self.assertNotIn("beta@example.com", usernames)

    def test_role_filter_limits_results(self):
        rows = self._get_rows(role="officer")
        usernames = [r[0] for r in rows[1:]]
        self.assertIn("beta@example.com", usernames)
        self.assertNotIn("alpha@example.com", usernames)

    def test_no_filter_returns_all_roster_members(self):
        rows = self._get_rows()
        # Header + at least both members + admin
        self.assertGreaterEqual(len(rows), 4)

    def test_export_includes_all_members_not_just_one_page(self):
        """The CSV must not be limited to 25 rows even when the roster is paginated."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        extras = User.objects.bulk_create([
            User(username=f"paginated-{i:03}@example.com", email=f"paginated-{i:03}@example.com", is_active=True)
            for i in range(30)
        ])
        Profile.objects.bulk_create([Profile(user=u, role=Role.MEMBER) for u in extras])
        rows = self._get_rows()
        # 30 extra + existing members, all in one file (not capped at 25)
        self.assertGreater(len(rows) - 1, 25)
        # Clean up
        User.objects.filter(username__startswith="paginated-").delete()


class RosterExportFormulaEscapeTests(TestCase):
    """AC-4: Cells starting with formula-trigger characters are escaped."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.url = reverse("membership:export_roster_csv")
        # Create users whose names start with formula-trigger characters.
        # Note: accounts/signals.py fires create_profile on post_save, so a
        # Profile (role=APPLICANT) is auto-created for each new user. We
        # update it to MEMBER rather than creating a second one.
        for prefix, suffix in [("=cmd", "eq"), ("+cmd", "plus"), ("-cmd", "minus"), ("@cmd", "at")]:
            u = User.objects.create_user(
                username=f"{prefix}-user-{suffix}",
                email=f"{prefix}-user-{suffix}@example.com",
                is_active=True,
            )
            Profile.objects.filter(user=u).update(role=Role.MEMBER)

    def _get_rows(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        content = b"".join(response.streaming_content if hasattr(response, "streaming_content") else [response.content])
        return list(csv.reader(StringIO(content.decode())))

    def test_every_cell_starting_with_a_trigger_is_escaped(self):
        rows = self._get_rows()
        for row in rows[1:]:
            for cell in row:
                self.assertFalse(
                    cell[:1] in {"=", "+", "-", "@", "\t", "\r"},
                    f"Unescaped formula-trigger character in cell: {cell!r}",
                )
        usernames = {row[0] for row in rows[1:]}
        self.assertIn("'=cmd-user-eq", usernames)
        self.assertIn("'=cmd-user-eq@example.com", {row[1] for row in rows[1:]})

    def test_formula_trigger_characters_are_escaped(self):
        rows = self._get_rows()
        trigger_chars = set("=+-@")
        for row in rows[1:]:
            username = row[0]
            # Any cell that originally started with a trigger character must be
            # prefixed with a single quote to prevent spreadsheet formula injection.
            if len(username) > 1 and username[0] == "'" and username[1] in trigger_chars:
                # This is an escaped cell – that's what we want.
                continue
            # For unescaped cells, the first character must NOT be a trigger.
            self.assertNotIn(
                username[0] if username else "",
                trigger_chars,
                f"Unescaped formula-trigger character in cell: {username!r}",
            )


class RosterExportFileNameTests(TestCase):
    """AC-5: The file is named orgflow-roster-YYYY-MM-DD.csv."""

    def test_content_disposition_uses_correct_filename_format(self):
        admin = make_user("admin@example.com", Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("membership:export_roster_csv"))
        disposition = response.get("Content-Disposition", "")
        today = timezone.localdate().strftime("%Y-%m-%d")
        self.assertIn(f"orgflow-roster-{today}.csv", disposition)

    # The fake clock is weeks ahead, so keep the test session from expiring.
    @override_settings(SESSION_COOKIE_AGE=60 * 60 * 24 * 365)
    def test_filename_uses_the_organization_date_late_in_the_evening(self):
        """10:30 PM Chicago time is already the next day in UTC; the file keeps the local date."""
        admin = make_user("late-admin@example.com", Role.ADMIN)
        self.client.force_login(admin)
        # 04:30 UTC on Dec 2 is 10:30 PM on Dec 1 in Chicago.
        utc_moment = datetime.datetime(2026, 12, 2, 4, 30, tzinfo=datetime.timezone.utc)
        with patch("django.utils.timezone.now", return_value=utc_moment):
            response = self.client.get(reverse("membership:export_roster_csv"))
        self.assertIn("orgflow-roster-2026-12-01.csv", response["Content-Disposition"])


class RosterExportButtonVisibilityTests(TestCase):
    """AC-1: Export CSV button on the roster page, visible to Admins only."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.officer = make_user("officer@example.com", Role.OFFICER)
        cls.member = make_user("member@example.com", Role.MEMBER)
        cls.url = reverse("membership:roster")

    def test_admin_sees_export_button(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "Export CSV")

    def test_officer_does_not_see_export_button(self):
        self.client.force_login(self.officer)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Export CSV")

    def test_member_does_not_see_export_button(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Export CSV")

    def test_export_link_keeps_filters_but_not_the_page_number(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"q": "example", "role": "member", "page": "2"})
        export_url = reverse("membership:export_roster_csv")
        self.assertContains(response, f'href="{export_url}?q=example&amp;role=member"')
        self.assertNotContains(response, f"{export_url}?q=example&amp;role=member&amp;page")


class RosterExportLocalDateTests(TestCase):
    """Dates in the CSV use the organization's time zone, like the roster page."""

    def test_late_evening_sign_up_keeps_the_local_date(self):
        admin = make_user("tz-admin@example.com", Role.ADMIN)
        member = make_user("tz-member@example.com", Role.MEMBER)
        # 11:30 PM Chicago on Nov 3 is 05:30 UTC on Nov 4.
        late = datetime.datetime(2026, 11, 4, 5, 30, tzinfo=datetime.timezone.utc)
        Profile.objects.filter(user=member).update(created_at=late)
        self.client.force_login(admin)

        rows = list(csv.reader(StringIO(
            self.client.get(reverse("membership:export_roster_csv")).content.decode()
        )))
        member_row = next(r for r in rows[1:] if r[1] == "tz-member@example.com")
        self.assertEqual(member_row[4], "2026-11-03")

        page = self.client.get(reverse("membership:roster"), {"q": "tz-member"})
        self.assertContains(page, "Nov 3, 2026")
