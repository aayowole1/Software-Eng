"""Tests for the participation and engagement reports (SCRUM-64, SCRUM-38)."""

import csv
import io
from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from events.models import Attendance, Event, RSVP, RSVPResponse
from tasks.models import Task, TaskStatus


REPORT_URL = reverse("reports:report")
CSV_EVENTS_URL = reverse("reports:csv_events")
CSV_MEMBERS_URL = reverse("reports:csv_members")
CSV_COMMITTEES_URL = reverse("reports:csv_committees")


def _today():
    return timezone.localdate()


def _make_event(officer, days_offset=0, cancelled=False, title="Test Event", hour=0, minute=0):
    """Create an event whose start date is `days_offset` days from today (can be negative)."""
    local_tz = timezone.get_current_timezone()
    dt = timezone.make_aware(
        timezone.datetime.combine(
            _today() + timedelta(days=days_offset),
            timezone.datetime.min.time(),
        ).replace(hour=hour, minute=minute),
        local_tz,
    )
    return Event.objects.create(
        title=title,
        location="Room 101",
        starts_at=dt,
        created_by=officer,
        cancelled=cancelled,
    )


def _attend(event, user, officer):
    return Attendance.objects.create(event=event, user=user, marked_by=officer)


def _rsvp_going(event, user):
    return RSVP.objects.create(event=event, user=user, response=RSVPResponse.GOING)


def _make_task(created_by, assignee=None, committee=None, status=TaskStatus.TODO, due_date=None, days_ago=0):
    """Create a task whose created_at is approximately `days_ago` days ago."""
    task = Task.objects.create(
        title="Task",
        created_by=created_by,
        assignee=assignee,
        committee=committee,
        status=status,
        due_date=due_date,
    )
    if days_ago:
        # Shift the created_at timestamp back for range tests.
        Task.objects.filter(pk=task.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        task.refresh_from_db()
    return task


def _parse_csv(response):
    """Return (headers, rows) from a CSV response."""
    content = response.content
    # Strip UTF-8 BOM if present.
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return reader.fieldnames or [], rows


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReportAccessTests(TestCase):
    """AC-1: Access control by role."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")

    def _get(self, url, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(url)

    def test_officer_can_access_report(self):
        response = self._get(REPORT_URL, self.officer)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_report(self):
        response = self._get(REPORT_URL, self.admin)
        self.assertEqual(response.status_code, 200)

    def test_member_gets_403(self):
        response = self._get(REPORT_URL, self.member)
        self.assertEqual(response.status_code, 403)

    def test_applicant_gets_403(self):
        response = self._get(REPORT_URL, self.applicant)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = self._get(REPORT_URL)
        self.assertRedirects(response, f"/accounts/login/?next={REPORT_URL}", fetch_redirect_response=False)

    def test_pending_applicant_cannot_access_report(self):
        """Users with applicant role (pending membership) cannot access the report."""
        response = self._get(REPORT_URL, self.applicant)
        self.assertEqual(response.status_code, 403)

    # --- CSV downloads: access ---

    def test_officer_can_access_csv_events(self):
        response = self._get(CSV_EVENTS_URL, self.officer)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_officer_can_access_csv_members(self):
        response = self._get(CSV_MEMBERS_URL, self.officer)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_officer_can_access_csv_committees(self):
        response = self._get(CSV_COMMITTEES_URL, self.officer)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_admin_can_access_csv_events(self):
        response = self._get(CSV_EVENTS_URL, self.admin)
        self.assertEqual(response.status_code, 200)

    def test_member_csv_events_gets_403(self):
        response = self._get(CSV_EVENTS_URL, self.member)
        self.assertEqual(response.status_code, 403)

    def test_member_csv_members_gets_403(self):
        response = self._get(CSV_MEMBERS_URL, self.member)
        self.assertEqual(response.status_code, 403)

    def test_member_csv_committees_gets_403(self):
        response = self._get(CSV_COMMITTEES_URL, self.member)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_csv_events_redirected_to_login(self):
        response = self._get(CSV_EVENTS_URL)
        self.assertRedirects(response, f"/accounts/login/?next={CSV_EVENTS_URL}", fetch_redirect_response=False)

    def test_anonymous_csv_members_redirected_to_login(self):
        response = self._get(CSV_MEMBERS_URL)
        self.assertRedirects(response, f"/accounts/login/?next={CSV_MEMBERS_URL}", fetch_redirect_response=False)

    def test_anonymous_csv_committees_redirected_to_login(self):
        response = self._get(CSV_COMMITTEES_URL)
        self.assertRedirects(response, f"/accounts/login/?next={CSV_COMMITTEES_URL}", fetch_redirect_response=False)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DateRangeValidationTests(TestCase):
    """AC-2: Date range validation."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)

    def test_default_date_range_is_last_30_days(self):
        response = self.client.get(REPORT_URL)
        self.assertEqual(response.status_code, 200)
        # Form should be pre-populated.
        form = response.context["form"]
        today = _today()
        self.assertEqual(form.initial["end_date"], today)
        self.assertEqual(form.initial["start_date"], today - timedelta(days=30))

    def test_end_before_start_shows_error(self):
        response = self.client.get(REPORT_URL, {
            "start_date": "2024-06-10",
            "end_date": "2024-06-01",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "end_date", "End date cannot be before start date.")

    def test_same_start_and_end_date_is_valid(self):
        today = _today()
        response = self.client.get(REPORT_URL, {
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].errors)

    def test_valid_range_produces_data(self):
        today = _today()
        response = self.client.get(REPORT_URL, {
            "start_date": (today - timedelta(days=7)).isoformat(),
            "end_date": today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["data"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EventFilteringTests(TestCase):
    """AC-3: Cancelled events and events outside the range are excluded."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def _report(self, start_offset=-5, end_offset=0):
        today = _today()
        return self.client.get(REPORT_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        }).context["data"]

    def test_cancelled_event_excluded_from_count(self):
        _make_event(self.officer, days_offset=-1, cancelled=True, title="Cancelled Event")
        data = self._report(start_offset=-5, end_offset=0)
        self.assertEqual(data["events_held"], 0)
        titles = [item["event"].title for item in data["per_event"]]
        self.assertNotIn("Cancelled Event", titles)

    def test_event_outside_range_excluded(self):
        _make_event(self.officer, days_offset=-10, title="Old Event")
        data = self._report(start_offset=-5, end_offset=0)
        self.assertEqual(data["events_held"], 0)

    def test_event_inside_range_included(self):
        _make_event(self.officer, days_offset=-2, title="Recent Event")
        data = self._report(start_offset=-5, end_offset=0)
        self.assertEqual(data["events_held"], 1)
        self.assertEqual(data["per_event"][0]["event"].title, "Recent Event")

    def test_events_on_boundary_dates_included(self):
        today = _today()
        # Event on start_date boundary.
        _make_event(self.officer, days_offset=-5, title="Start Boundary")
        # Event on end_date boundary (today).
        _make_event(self.officer, days_offset=0, title="End Boundary")
        data = self._report(start_offset=-5, end_offset=0)
        self.assertEqual(data["events_held"], 2)

    def test_mixed_cancelled_and_active(self):
        _make_event(self.officer, days_offset=-1, cancelled=False, title="Active")
        _make_event(self.officer, days_offset=-2, cancelled=True, title="Cancelled")
        data = self._report(start_offset=-5, end_offset=0)
        self.assertEqual(data["events_held"], 1)
        titles = [item["event"].title for item in data["per_event"]]
        self.assertIn("Active", titles)
        self.assertNotIn("Cancelled", titles)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PerEventCountsTests(TestCase):
    """AC-3: Per-event RSVP and attendance counts."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member1 = make_user("m1@example.com", Role.MEMBER)
        self.member2 = make_user("m2@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def test_per_event_rsvp_and_attendance_counts(self):
        event = _make_event(self.officer, days_offset=-1, title="Test")
        _rsvp_going(event, self.member1)
        _rsvp_going(event, self.member2)
        _attend(event, self.member1, self.officer)

        today = _today()
        data = self.client.get(REPORT_URL, {
            "start_date": (today - timedelta(days=5)).isoformat(),
            "end_date": today.isoformat(),
        }).context["data"]

        self.assertEqual(len(data["per_event"]), 1)
        item = data["per_event"][0]
        self.assertEqual(item["rsvps_going"], 2)
        self.assertEqual(item["attended"], 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PerMemberCountsTests(TestCase):
    """AC-3 & AC-4: Per-member attendance and task counts."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def _report(self, start_offset=-5, end_offset=0):
        today = _today()
        return self.client.get(REPORT_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        }).context["data"]

    def _member_row(self, data):
        for row in data["per_member"]:
            if row["user"].pk == self.member.pk:
                return row
        self.fail("Member not found in per_member data")

    def test_member_attendance_counts(self):
        event1 = _make_event(self.officer, days_offset=-1, title="E1")
        event2 = _make_event(self.officer, days_offset=-2, title="E2")
        _attend(event1, self.member, self.officer)
        # member2 didn't attend event2.
        data = self._report()
        row = self._member_row(data)
        self.assertEqual(row["attended"], 1)
        self.assertEqual(row["events_held"], 2)
        self.assertAlmostEqual(row["attendance_pct"], 50.0)

    def test_member_attendance_pct_none_when_no_events(self):
        data = self._report()
        row = self._member_row(data)
        self.assertIsNone(row["attendance_pct"])

    def test_member_task_counts(self):
        today = _today()
        # Completed task.
        _make_task(self.officer, assignee=self.member, status=TaskStatus.DONE)
        # Overdue task (due yesterday, not done).
        _make_task(self.officer, assignee=self.member, status=TaskStatus.TODO, due_date=today - timedelta(days=1))
        # TODO task with future due date.
        _make_task(self.officer, assignee=self.member, status=TaskStatus.TODO, due_date=today + timedelta(days=5))

        data = self._report()
        row = self._member_row(data)
        self.assertEqual(row["tasks_assigned"], 3)
        self.assertEqual(row["tasks_completed"], 1)
        self.assertEqual(row["tasks_overdue"], 1)

    def test_tasks_outside_range_excluded(self):
        # Task created 60 days ago — outside the default 30-day range.
        _make_task(self.officer, assignee=self.member, status=TaskStatus.TODO, days_ago=60)
        data = self._report(start_offset=-30, end_offset=0)
        row = self._member_row(data)
        self.assertEqual(row["tasks_assigned"], 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PerCommitteeCountsTests(TestCase):
    """AC-3 & AC-4: Per-committee attendance and task counts."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member1 = make_user("m1@example.com", Role.MEMBER)
        self.member2 = make_user("m2@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Events", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member1)
        CommitteeMember.objects.create(committee=self.committee, user=self.member2)
        self.client.force_login(self.officer)

    def _report(self, start_offset=-5, end_offset=0):
        today = _today()
        return self.client.get(REPORT_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        }).context["data"]

    def _committee_row(self, data):
        for row in data["per_committee"]:
            if row["committee"].pk == self.committee.pk:
                return row
        self.fail("Committee not found in per_committee data")

    def test_committee_member_count(self):
        data = self._report()
        row = self._committee_row(data)
        self.assertEqual(row["num_members"], 2)

    def test_committee_attendance_pct(self):
        event = _make_event(self.officer, days_offset=-1, title="E")
        # Only member1 attended out of 2 members, 1 event.
        _attend(event, self.member1, self.officer)
        data = self._report()
        row = self._committee_row(data)
        # 1 attendance / (2 members × 1 event) = 50%.
        self.assertAlmostEqual(row["attendance_pct"], 50.0)

    def test_committee_attendance_pct_none_when_no_events(self):
        data = self._report()
        row = self._committee_row(data)
        self.assertIsNone(row["attendance_pct"])

    def test_committee_task_counts(self):
        today = _today()
        _make_task(self.officer, committee=self.committee, status=TaskStatus.DONE)
        _make_task(self.officer, committee=self.committee, status=TaskStatus.TODO,
                   due_date=today - timedelta(days=1))
        _make_task(self.officer, committee=self.committee, status=TaskStatus.TODO,
                   due_date=today + timedelta(days=3))
        data = self._report()
        row = self._committee_row(data)
        self.assertEqual(row["tasks_total"], 3)
        self.assertEqual(row["tasks_completed"], 1)
        self.assertEqual(row["tasks_overdue"], 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EventsCsvTests(TestCase):
    """Events CSV: columns, rows, date/time formatting, formula escaping."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("m@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def _csv(self, start_offset=-5, end_offset=0, **extra_params):
        today = _today()
        params = {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        }
        params.update(extra_params)
        response = self.client.get(CSV_EVENTS_URL, params)
        self.assertEqual(response.status_code, 200)
        _, rows = _parse_csv(response)
        return rows

    def test_events_csv_columns(self):
        """Events CSV has the correct six columns."""
        response = self.client.get(CSV_EVENTS_URL)
        headers, _ = _parse_csv(response)
        self.assertEqual(headers, ["Event", "Date", "Start time", "Location", "RSVPs going", "Attended"])

    def test_events_csv_one_row_per_event(self):
        _make_event(self.officer, days_offset=-2, title="Alpha")
        _make_event(self.officer, days_offset=-1, title="Beta")
        rows = self._csv()
        titles = [r["Event"] for r in rows]
        self.assertIn("Alpha", titles)
        self.assertIn("Beta", titles)
        self.assertEqual(len(rows), 2)

    def test_events_csv_oldest_first(self):
        _make_event(self.officer, days_offset=-1, title="Newer")
        _make_event(self.officer, days_offset=-2, title="Older")
        rows = self._csv()
        self.assertEqual(rows[0]["Event"], "Older")
        self.assertEqual(rows[1]["Event"], "Newer")

    def test_events_csv_date_format(self):
        """Date column is YYYY-MM-DD in the organization's time zone."""
        today = _today()
        event = _make_event(self.officer, days_offset=-1, title="Dated")
        rows = self._csv()
        expected_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        event_row = next(r for r in rows if r["Event"] == "Dated")
        self.assertEqual(event_row["Date"], expected_date)

    def test_events_csv_time_format(self):
        """Start time column is HH:MM."""
        _make_event(self.officer, days_offset=-1, title="Timed", hour=14, minute=30)
        rows = self._csv()
        event_row = next(r for r in rows if r["Event"] == "Timed")
        self.assertEqual(event_row["Start time"], "14:30")

    def test_events_csv_late_evening_event(self):
        """A late-evening event (23:59) records its time correctly."""
        _make_event(self.officer, days_offset=-1, title="Night Owl", hour=23, minute=59)
        rows = self._csv()
        event_row = next(r for r in rows if r["Event"] == "Night Owl")
        self.assertEqual(event_row["Start time"], "23:59")

    def test_events_csv_location(self):
        event = _make_event(self.officer, days_offset=-1, title="Loc Test")
        rows = self._csv()
        event_row = next(r for r in rows if r["Event"] == "Loc Test")
        self.assertEqual(event_row["Location"], "Room 101")

    def test_events_csv_rsvps_and_attended(self):
        event = _make_event(self.officer, days_offset=-1, title="RSVP Test")
        _rsvp_going(event, self.member)
        _attend(event, self.member, self.officer)
        rows = self._csv()
        event_row = rows[0]
        self.assertEqual(event_row["RSVPs going"], "1")
        self.assertEqual(event_row["Attended"], "1")

    def test_events_csv_numeric_no_na(self):
        """Numeric columns contain only numbers, never 'N/A'."""
        _make_event(self.officer, days_offset=-1, title="Zero RSVPs")
        rows = self._csv()
        for row in rows:
            self.assertNotIn("N/A", row["RSVPs going"])
            self.assertNotIn("N/A", row["Attended"])

    def test_events_csv_formula_escaping_equals(self):
        _make_event(self.officer, days_offset=-1, title="=DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("="), f"Unescaped '=' in: {value!r}")

    def test_events_csv_formula_escaping_plus(self):
        _make_event(self.officer, days_offset=-1, title="+DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("+"), f"Unescaped '+' in: {value!r}")

    def test_events_csv_formula_escaping_at(self):
        _make_event(self.officer, days_offset=-1, title="@DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("@"), f"Unescaped '@' in: {value!r}")

    def test_events_csv_formula_escaping_minus(self):
        _make_event(self.officer, days_offset=-1, title="-DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("-"), f"Unescaped '-' in: {value!r}")

    def test_events_csv_formula_escaping_tab(self):
        _make_event(self.officer, days_offset=-1, title="\tDANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("\t"), f"Unescaped tab in: {value!r}")

    def test_events_csv_formula_escaping_cr(self):
        _make_event(self.officer, days_offset=-1, title="\rDANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                self.assertFalse(value.startswith("\r"), f"Unescaped CR in: {value!r}")

    def test_events_csv_safe_values_not_escaped(self):
        _make_event(self.officer, days_offset=-1, title="Normal Event")
        rows = self._csv()
        self.assertTrue(any(r["Event"] == "Normal Event" for r in rows))

    def test_events_csv_filename(self):
        """Content-Disposition filename matches orgflow-report-events-{start}_{end}.csv."""
        today = _today()
        start = (today - timedelta(days=5)).isoformat()
        end = today.isoformat()
        response = self.client.get(CSV_EVENTS_URL, {"start_date": start, "end_date": end})
        expected = f"orgflow-report-events-{start}_{end}.csv"
        self.assertIn(expected, response["Content-Disposition"])

    def test_events_csv_bom(self):
        """Response body starts with UTF-8 BOM (EF BB BF)."""
        response = self.client.get(CSV_EVENTS_URL)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"), "Missing UTF-8 BOM")

    def test_events_csv_empty_when_no_events(self):
        """Events CSV has only the header row when there are no events."""
        rows = self._csv()
        self.assertEqual(rows, [])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MembersCsvTests(TestCase):
    """Members CSV: columns, rows, attendance % formatting, formula escaping."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def _csv(self, start_offset=-5, end_offset=0):
        today = _today()
        response = self.client.get(CSV_MEMBERS_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        _, rows = _parse_csv(response)
        return rows

    def test_members_csv_columns(self):
        response = self.client.get(CSV_MEMBERS_URL)
        headers, _ = _parse_csv(response)
        self.assertEqual(headers, [
            "Member", "Email", "Role", "Attended", "Events held",
            "Attendance %", "Tasks assigned", "Tasks completed", "Tasks overdue",
        ])

    def test_members_csv_one_row_per_member(self):
        """One row per roster member (officer + member = 2 rows)."""
        rows = self._csv()
        self.assertEqual(len(rows), 2)

    def test_members_csv_contains_member_data(self):
        rows = self._csv()
        emails = [r["Email"] for r in rows]
        self.assertIn("member@example.com", emails)

    def test_members_csv_role_column(self):
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertEqual(member_row["Role"], "Member")
        officer_row = next(r for r in rows if r["Email"] == "officer@example.com")
        self.assertEqual(officer_row["Role"], "Officer")

    def test_members_csv_attendance_counts(self):
        event = _make_event(self.officer, days_offset=-1, title="E")
        _attend(event, self.member, self.officer)
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertEqual(member_row["Attended"], "1")
        self.assertEqual(member_row["Events held"], "1")

    def test_members_csv_attendance_pct_one_decimal(self):
        """Attendance % is a number with one decimal place, no % sign."""
        event1 = _make_event(self.officer, days_offset=-3, title="E1")
        event2 = _make_event(self.officer, days_offset=-2, title="E2")
        event3 = _make_event(self.officer, days_offset=-1, title="E3")
        _attend(event1, self.member, self.officer)
        # attended 1 of 3 = 33.3%
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertEqual(member_row["Attendance %"], "33.3")

    def test_members_csv_attendance_pct_blank_when_no_events(self):
        """Attendance % is blank (not 'N/A') when no events were held."""
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertEqual(member_row["Attendance %"], "")
        self.assertNotIn("N/A", member_row["Attendance %"])

    def test_members_csv_task_counts(self):
        today = _today()
        _make_task(self.officer, assignee=self.member, status=TaskStatus.DONE)
        _make_task(self.officer, assignee=self.member, status=TaskStatus.TODO,
                   due_date=today - timedelta(days=1))
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertEqual(member_row["Tasks assigned"], "2")
        self.assertEqual(member_row["Tasks completed"], "1")
        self.assertEqual(member_row["Tasks overdue"], "1")

    def test_members_csv_formula_escaping_in_name(self):
        """Names starting with formula triggers are escaped."""
        self.member.first_name = "=Evil"
        self.member.last_name = "User"
        self.member.save()
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertFalse(member_row["Member"].startswith("="), f"Unescaped '=' in name: {member_row['Member']!r}")

    def test_members_csv_formula_escaping_tab_in_name(self):
        """Names starting with tab are escaped."""
        self.member.first_name = "\tTabName"
        self.member.last_name = ""
        self.member.save()
        rows = self._csv()
        member_row = next(r for r in rows if r["Email"] == "member@example.com")
        self.assertFalse(member_row["Member"].startswith("\t"), f"Unescaped tab in name: {member_row['Member']!r}")

    def test_members_csv_filename(self):
        today = _today()
        start = (today - timedelta(days=5)).isoformat()
        end = today.isoformat()
        response = self.client.get(CSV_MEMBERS_URL, {"start_date": start, "end_date": end})
        expected = f"orgflow-report-members-{start}_{end}.csv"
        self.assertIn(expected, response["Content-Disposition"])

    def test_members_csv_bom(self):
        response = self.client.get(CSV_MEMBERS_URL)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"), "Missing UTF-8 BOM")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CommitteesCsvTests(TestCase):
    """Committees CSV: columns, rows, attendance % formatting, formula escaping."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Finance", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        self.client.force_login(self.officer)

    def _csv(self, start_offset=-5, end_offset=0):
        today = _today()
        response = self.client.get(CSV_COMMITTEES_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        _, rows = _parse_csv(response)
        return rows

    def test_committees_csv_columns(self):
        response = self.client.get(CSV_COMMITTEES_URL)
        headers, _ = _parse_csv(response)
        self.assertEqual(headers, [
            "Committee", "Members", "Attendance %",
            "Tasks total", "Tasks completed", "Tasks overdue",
        ])

    def test_committees_csv_one_row_per_committee(self):
        Committee.objects.create(name="Outreach", created_by=self.officer)
        rows = self._csv()
        self.assertEqual(len(rows), 2)

    def test_committees_csv_member_count(self):
        rows = self._csv()
        committee_row = next(r for r in rows if r["Committee"] == "Finance")
        self.assertEqual(committee_row["Members"], "1")

    def test_committees_csv_attendance_pct_one_decimal(self):
        """Attendance % has one decimal place and no % sign."""
        event1 = _make_event(self.officer, days_offset=-2, title="E1")
        event2 = _make_event(self.officer, days_offset=-1, title="E2")
        # member attended 1 of 2 events → 50%
        _attend(event1, self.member, self.officer)
        rows = self._csv()
        committee_row = next(r for r in rows if r["Committee"] == "Finance")
        self.assertEqual(committee_row["Attendance %"], "50.0")

    def test_committees_csv_attendance_pct_blank_when_no_events(self):
        """Attendance % is blank (not 'N/A') when no events were held."""
        rows = self._csv()
        committee_row = next(r for r in rows if r["Committee"] == "Finance")
        self.assertEqual(committee_row["Attendance %"], "")
        self.assertNotIn("N/A", committee_row["Attendance %"])

    def test_committees_csv_task_counts(self):
        today = _today()
        _make_task(self.officer, committee=self.committee, status=TaskStatus.DONE)
        _make_task(self.officer, committee=self.committee, status=TaskStatus.TODO,
                   due_date=today - timedelta(days=1))
        _make_task(self.officer, committee=self.committee, status=TaskStatus.TODO,
                   due_date=today + timedelta(days=5))
        rows = self._csv()
        committee_row = next(r for r in rows if r["Committee"] == "Finance")
        self.assertEqual(committee_row["Tasks total"], "3")
        self.assertEqual(committee_row["Tasks completed"], "1")
        self.assertEqual(committee_row["Tasks overdue"], "1")

    def test_committees_csv_formula_escaping_in_name(self):
        Committee.objects.create(name="=Evil Committee", created_by=self.officer)
        rows = self._csv()
        evil_row = next(r for r in rows if "Evil" in r["Committee"])
        self.assertFalse(evil_row["Committee"].startswith("="),
                         f"Unescaped '=' in committee name: {evil_row['Committee']!r}")

    def test_committees_csv_formula_escaping_tab_in_name(self):
        Committee.objects.create(name="\tTabCommittee", created_by=self.officer)
        rows = self._csv()
        tab_row = next(r for r in rows if "Tab" in r["Committee"])
        self.assertFalse(tab_row["Committee"].startswith("\t"),
                         f"Unescaped tab in committee name: {tab_row['Committee']!r}")

    def test_committees_csv_filename(self):
        today = _today()
        start = (today - timedelta(days=5)).isoformat()
        end = today.isoformat()
        response = self.client.get(CSV_COMMITTEES_URL, {"start_date": start, "end_date": end})
        expected = f"orgflow-report-committees-{start}_{end}.csv"
        self.assertIn(expected, response["Content-Disposition"])

    def test_committees_csv_bom(self):
        response = self.client.get(CSV_COMMITTEES_URL)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"), "Missing UTF-8 BOM")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SidebarNavigationTests(TestCase):
    """AC-6: Reports link appears in sidebar for Officers and Admins only."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")

    def _dashboard(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("core:dashboard"))

    def test_officer_sees_reports_link(self):
        response = self._dashboard(self.officer)
        self.assertContains(response, reverse("reports:report"))

    def test_admin_sees_reports_link(self):
        response = self._dashboard(self.admin)
        self.assertContains(response, reverse("reports:report"))

    def test_member_does_not_see_reports_link(self):
        response = self._dashboard(self.member)
        self.assertNotContains(response, reverse("reports:report"))

    def test_applicant_does_not_see_reports_link(self):
        response = self._dashboard(self.applicant)
        self.assertNotContains(response, reverse("reports:report"))

    def test_anonymous_does_not_see_reports_link(self):
        response = self._dashboard()
        self.assertNotContains(response, reverse("reports:report"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DefinitionsOnPageTests(TestCase):
    """AC-7: Definitions appear on the report page."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)

    def test_attendance_pct_definition_present(self):
        response = self.client.get(REPORT_URL)
        self.assertContains(response, "attendance %")

    def test_overdue_definition_present(self):
        response = self.client.get(REPORT_URL)
        self.assertContains(response, "Overdue")

    def test_download_csv_heading_present(self):
        """The 'Download CSV' heading and all three download links appear on the report page."""
        response = self.client.get(REPORT_URL)
        self.assertContains(response, "Download CSV")
        self.assertContains(response, reverse("reports:csv_events"))
        self.assertContains(response, reverse("reports:csv_members"))
        self.assertContains(response, reverse("reports:csv_committees"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewDateBoundaryTests(TestCase):
    """Review fixes: upcoming events are not 'held', and the whole end day is included."""

    def setUp(self):
        self.officer = make_user("boundary-officer@example.com", Role.OFFICER)
        self.member = make_user("boundary-member@example.com", Role.MEMBER)
        self.client.force_login(self.officer)
        self.tz = timezone.get_current_timezone()

    def _local(self, day, hour=0, minute=0, second=0, microsecond=0):
        return timezone.make_aware(
            timezone.datetime.combine(day, timezone.datetime.min.time()).replace(
                hour=hour, minute=minute, second=second, microsecond=microsecond
            ),
            self.tz,
        )

    def _params(self, start_offset, end_offset):
        today = _today()
        return {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        }

    def _report(self, start_offset, end_offset):
        return self.client.get(REPORT_URL, self._params(start_offset, end_offset)).context["data"]

    def _events_csv_rows(self, start_offset, end_offset):
        """Return raw csv rows (list of lists) from the events CSV."""
        response = self.client.get(CSV_EVENTS_URL, self._params(start_offset, end_offset))
        return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))

    def _member_row(self, data):
        return next(r for r in data["per_member"] if r["user"] == self.member)

    # --- Upcoming events are not counted as held ----------------------------

    def test_upcoming_event_in_range_is_not_counted_as_held(self):
        past = _make_event(self.officer, days_offset=-1, title="Held")
        _make_event(self.officer, days_offset=2, title="Upcoming")
        _attend(past, self.member, self.officer)

        data = self._report(start_offset=-5, end_offset=5)

        self.assertEqual(data["events_held"], 1)
        self.assertEqual([i["event"].title for i in data["per_event"]], ["Held"])
        row = self._member_row(data)
        self.assertEqual(row["events_held"], 1)
        self.assertEqual(row["attendance_pct"], 100.0)

    def test_upcoming_event_excluded_from_events_csv(self):
        _make_event(self.officer, days_offset=-1, title="Held")
        _make_event(self.officer, days_offset=2, title="Upcoming")

        rows = self._events_csv_rows(start_offset=-5, end_offset=5)

        # Only one data row (header + 1 event).
        self.assertEqual(len(rows), 2)
        self.assertFalse(any("Upcoming" in r for r in rows))

    def test_committee_attendance_ignores_upcoming_events(self):
        committee = Committee.objects.create(name="Outreach")
        CommitteeMember.objects.create(committee=committee, user=self.member)
        past = _make_event(self.officer, days_offset=-1, title="Held")
        _make_event(self.officer, days_offset=3, title="Upcoming")
        _attend(past, self.member, self.officer)

        data = self._report(start_offset=-5, end_offset=5)

        row = next(r for r in data["per_committee"] if r["committee"] == committee)
        self.assertEqual(row["attendance_pct"], 100.0)

    # --- Records late on the end date are included --------------------------

    def test_event_in_last_second_of_end_date_is_included(self):
        yesterday = _today() - timedelta(days=1)
        Event.objects.create(
            title="Late Night", location="Hall", created_by=self.officer,
            starts_at=self._local(yesterday, 23, 59, 59, 500000),
        )
        Event.objects.create(
            title="Next Day", location="Hall", created_by=self.officer,
            starts_at=self._local(_today()),
        )

        data = self._report(start_offset=-1, end_offset=-1)

        self.assertEqual([i["event"].title for i in data["per_event"]], ["Late Night"])
        rows = self._events_csv_rows(start_offset=-1, end_offset=-1)
        # Header + 1 data row.
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("Late Night" in r for r in rows))

    def test_task_created_in_last_second_of_end_date_is_counted(self):
        yesterday = _today() - timedelta(days=1)
        task = _make_task(self.officer, assignee=self.member)
        Task.objects.filter(pk=task.pk).update(created_at=self._local(yesterday, 23, 59, 59, 500000))

        data = self._report(start_offset=-1, end_offset=-1)

        self.assertEqual(self._member_row(data)["tasks_assigned"], 1)

        response = self.client.get(CSV_MEMBERS_URL, self._params(start_offset=-1, end_offset=-1))
        _, rows = _parse_csv(response)
        member_name = self.member.get_full_name() or self.member.username
        member_row = next(r for r in rows if r["Member"] == member_name)
        self.assertEqual(member_row["Tasks assigned"], "1")

    def test_definitions_explain_upcoming_events_and_whole_days(self):
        response = self.client.get(REPORT_URL)
        self.assertContains(response, "Cancelled and upcoming events are not counted.")
        self.assertContains(response, "include the whole start and end day")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CsvInvalidRangeTests(TestCase):
    """CSV downloads return 400 for invalid date ranges."""

    def setUp(self):
        self.officer = make_user("csv-range-officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)

    def _check_400(self, url, params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("attachment", response.get("Content-Disposition", ""))
        return response

    def test_events_end_before_start_returns_400(self):
        today = _today()
        response = self._check_400(CSV_EVENTS_URL, {
            "start_date": today.isoformat(),
            "end_date": (today - timedelta(days=3)).isoformat(),
        })
        self.assertIn("End date cannot be before start date.", response.content.decode())

    def test_members_end_before_start_returns_400(self):
        today = _today()
        self._check_400(CSV_MEMBERS_URL, {
            "start_date": today.isoformat(),
            "end_date": (today - timedelta(days=3)).isoformat(),
        })

    def test_committees_end_before_start_returns_400(self):
        today = _today()
        self._check_400(CSV_COMMITTEES_URL, {
            "start_date": today.isoformat(),
            "end_date": (today - timedelta(days=3)).isoformat(),
        })

    def test_unreadable_date_returns_400(self):
        self._check_400(CSV_EVENTS_URL, {
            "start_date": "not-a-date",
            "end_date": _today().isoformat(),
        })

    def test_missing_one_date_returns_400(self):
        self._check_400(CSV_EVENTS_URL, {"start_date": _today().isoformat()})

    def test_no_dates_downloads_default_last_30_days_events(self):
        response = self.client.get(CSV_EVENTS_URL)
        today = _today()
        self.assertEqual(response.status_code, 200)
        expected = f"orgflow-report-events-{today - timedelta(days=30)}_{today}.csv"
        self.assertIn(expected, response["Content-Disposition"])

    def test_no_dates_downloads_default_last_30_days_members(self):
        response = self.client.get(CSV_MEMBERS_URL)
        today = _today()
        self.assertEqual(response.status_code, 200)
        expected = f"orgflow-report-members-{today - timedelta(days=30)}_{today}.csv"
        self.assertIn(expected, response["Content-Disposition"])

    def test_no_dates_downloads_default_last_30_days_committees(self):
        response = self.client.get(CSV_COMMITTEES_URL)
        today = _today()
        self.assertEqual(response.status_code, 200)
        expected = f"orgflow-report-committees-{today - timedelta(days=30)}_{today}.csv"
        self.assertIn(expected, response["Content-Disposition"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SuspendedOfficerAccessTests(TestCase):
    """A suspended officer can't open the report or download the CSV."""

    def setUp(self):
        self.officer = make_user("suspended-officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)
        Profile.objects.filter(user=self.officer).update(is_suspended=True)

    def test_suspended_officer_is_signed_out_of_report(self):
        response = self.client.get(REPORT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_suspended_officer_cannot_download_events_csv(self):
        response = self.client.get(CSV_EVENTS_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.assertNotIn("attachment", response.get("Content-Disposition", ""))

    def test_suspended_officer_cannot_download_members_csv(self):
        response = self.client.get(CSV_MEMBERS_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_suspended_officer_cannot_download_committees_csv(self):
        response = self.client.get(CSV_COMMITTEES_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
