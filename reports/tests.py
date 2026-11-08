"""Tests for the participation and engagement reports (SCRUM-64)."""

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
CSV_URL = reverse("reports:csv")


def _today():
    return timezone.localdate()


def _make_event(officer, days_offset=0, cancelled=False, title="Test Event"):
    """Create an event whose start date is `days_offset` days from today (can be negative)."""
    local_tz = timezone.get_current_timezone()
    dt = timezone.datetime.combine(
        _today() + timedelta(days=days_offset),
        timezone.datetime.min.time(),
        tzinfo=local_tz,
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

    def test_officer_can_access_csv_download(self):
        response = self._get(CSV_URL, self.officer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_member_csv_gets_403(self):
        response = self._get(CSV_URL, self.member)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_csv_redirected_to_login(self):
        response = self._get(CSV_URL)
        self.assertRedirects(response, f"/accounts/login/?next={CSV_URL}", fetch_redirect_response=False)


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
class CsvDownloadTests(TestCase):
    """AC-5: CSV content, structure, and formula escaping."""

    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("m@example.com", Role.MEMBER)
        self.client.force_login(self.officer)

    def _csv(self, start_offset=-5, end_offset=0):
        today = _today()
        response = self.client.get(CSV_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = b"".join(response.streaming_content if hasattr(response, "streaming_content") else [response.content]).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)

    def test_csv_has_section_column(self):
        rows = self._csv()
        for row in rows:
            self.assertIn("section", row)

    def test_csv_contains_event_data(self):
        event = _make_event(self.officer, days_offset=-1, title="CSV Event")
        _attend(event, self.member, self.officer)
        rows = self._csv()
        sections = {row["section"] for row in rows}
        self.assertIn("event", sections)

    def test_csv_contains_member_data(self):
        rows = self._csv()
        sections = {row["section"] for row in rows}
        self.assertIn("member", sections)

    def test_csv_contains_committee_data(self):
        Committee.objects.create(name="Finance", created_by=self.officer)
        rows = self._csv()
        sections = {row["section"] for row in rows}
        self.assertIn("committee", sections)

    def test_formula_escaping_equals(self):
        """Cell values starting with = are prefixed with ' to prevent injection."""
        # Create an event whose title starts with '='.
        _make_event(self.officer, days_offset=-1, title="=DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                if value and value.startswith("="):
                    self.fail(f"Unescaped formula trigger in CSV: {value!r}")

    def test_formula_escaping_plus(self):
        _make_event(self.officer, days_offset=-1, title="+DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                if value and value.startswith("+"):
                    self.fail(f"Unescaped formula trigger in CSV: {value!r}")

    def test_formula_escaping_at(self):
        _make_event(self.officer, days_offset=-1, title="@DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                if value and value.startswith("@"):
                    self.fail(f"Unescaped formula trigger in CSV: {value!r}")

    def test_formula_escaping_minus(self):
        _make_event(self.officer, days_offset=-1, title="-DANGEROUS()")
        rows = self._csv()
        for row in rows:
            for value in row.values():
                if value and value.startswith("-"):
                    self.fail(f"Unescaped formula trigger in CSV: {value!r}")

    def test_safe_values_not_escaped(self):
        """Normal values must not be prefixed with the escape character."""
        _make_event(self.officer, days_offset=-1, title="Normal Event")
        rows = self._csv()
        names = [row.get("name", "") for row in rows if row.get("name")]
        self.assertTrue(any("Normal Event" in n for n in names))

    def test_csv_member_has_attendance_metrics(self):
        event = _make_event(self.officer, days_offset=-1)
        _attend(event, self.member, self.officer)
        rows = self._csv()
        member_rows = [r for r in rows if r["section"] == "member"]
        metrics = {r["metric"] for r in member_rows}
        self.assertIn("attended", metrics)
        self.assertIn("attendance_pct", metrics)
        self.assertIn("tasks_assigned", metrics)

    def test_csv_committee_has_task_metrics(self):
        Committee.objects.create(name="Budget", created_by=self.officer)
        rows = self._csv()
        committee_rows = [r for r in rows if r["section"] == "committee"]
        metrics = {r["metric"] for r in committee_rows}
        self.assertIn("tasks_total", metrics)
        self.assertIn("tasks_completed", metrics)
        self.assertIn("tasks_overdue", metrics)


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

    def _csv_rows(self, start_offset, end_offset):
        response = self.client.get(CSV_URL, self._params(start_offset, end_offset))
        return list(csv.reader(io.StringIO(response.content.decode())))

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

    def test_upcoming_event_excluded_from_csv(self):
        _make_event(self.officer, days_offset=-1, title="Held")
        _make_event(self.officer, days_offset=2, title="Upcoming")

        rows = self._csv_rows(start_offset=-5, end_offset=5)

        self.assertIn(["events", "summary", "events_held", "1"], rows)
        self.assertFalse(any(r[1] == "Upcoming" for r in rows))

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
        rows = self._csv_rows(start_offset=-1, end_offset=-1)
        self.assertIn(["events", "summary", "events_held", "1"], rows)

    def test_task_created_in_last_second_of_end_date_is_counted(self):
        yesterday = _today() - timedelta(days=1)
        task = _make_task(self.officer, assignee=self.member)
        Task.objects.filter(pk=task.pk).update(created_at=self._local(yesterday, 23, 59, 59, 500000))

        data = self._report(start_offset=-1, end_offset=-1)

        self.assertEqual(self._member_row(data)["tasks_assigned"], 1)
        rows = self._csv_rows(start_offset=-1, end_offset=-1)
        member_name = self.member.get_full_name() or self.member.username
        self.assertIn(["member", member_name, "tasks_assigned", "1"], rows)

    def test_definitions_explain_upcoming_events_and_whole_days(self):
        response = self.client.get(REPORT_URL)
        self.assertContains(response, "Cancelled and upcoming events are not counted.")
        self.assertContains(response, "include the whole start and end day")
