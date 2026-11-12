"""Django tests for the chart data embedded in the Reports page (SCRUM-37)."""

import json
import re
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from events.models import Attendance, Event, RSVP, RSVPResponse
from tasks.models import Task, TaskStatus

REPORT_URL = reverse("reports:report")


def _today():
    return timezone.localdate()


def _make_event(officer, days_offset=0, cancelled=False, title="Test Event"):
    """Create an event whose start date is `days_offset` days from today (can be negative)."""
    local_tz = timezone.get_current_timezone()
    dt = timezone.make_aware(
        timezone.datetime.combine(
            _today() + timedelta(days=days_offset),
            timezone.datetime.min.time(),
        ),
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


def _make_task(created_by, assignee=None, committee=None, status=TaskStatus.TODO, due_date=None):
    return Task.objects.create(
        title="Task",
        created_by=created_by,
        assignee=assignee,
        committee=committee,
        status=status,
        due_date=due_date,
    )


def _get_chart_data(response):
    """Extract the embedded chart JSON from the page content."""
    content = response.content.decode()
    # json_script produces: <script id="chart-data" type="application/json">...</script>
    match = re.search(
        r'<script[^>]+id="chart-data"[^>]*>(.*?)</script>',
        content,
        re.DOTALL,
    )
    if not match:
        return None
    return json.loads(match.group(1))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChartDataEmbeddedTests(TestCase):
    """Chart data embedded in the page matches known report numbers."""

    def setUp(self):
        self.officer = make_user("chart-officer@example.com", Role.OFFICER)
        self.member = make_user("chart-member@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Finance", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        # Attendance counts from membership start (#25), so join before the past test events.
        for user in (self.officer, self.member):
            type(user).objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=60))
        self.client.force_login(self.officer)

    def _report(self, start_offset=-5, end_offset=0):
        today = _today()
        return self.client.get(REPORT_URL, {
            "start_date": (today + timedelta(days=start_offset)).isoformat(),
            "end_date": (today + timedelta(days=end_offset)).isoformat(),
        })

    def test_chart_data_script_tag_present(self):
        response = self._report()
        self.assertContains(response, 'id="chart-data"')

    def test_chart_data_per_event_matches_report(self):
        event = _make_event(self.officer, days_offset=-1, title="Annual Gala")
        _rsvp_going(event, self.member)
        _attend(event, self.member, self.officer)

        response = self._report()
        data = _get_chart_data(response)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["per_event"]), 1)
        event_data = data["per_event"][0]
        self.assertEqual(event_data["title"], "Annual Gala")
        self.assertEqual(event_data["rsvps_going"], 1)
        self.assertEqual(event_data["attended"], 1)

    def test_chart_data_per_committee_attendance_pct(self):
        event = _make_event(self.officer, days_offset=-1, title="Committee Meeting")
        _attend(event, self.member, self.officer)

        response = self._report()
        data = _get_chart_data(response)
        self.assertIsNotNone(data)

        committee_data = next(
            (c for c in data["per_committee"] if c["name"] == "Finance"), None
        )
        self.assertIsNotNone(committee_data)
        # 1 member, 1 event, 1 attendance → 100%
        self.assertEqual(committee_data["attendance_pct"], 100.0)
        self.assertTrue(committee_data["has_events"])

    def test_chart_data_committee_no_events_has_events_false(self):
        # No events in range → attendance_pct is None → has_events = False
        response = self._report()
        data = _get_chart_data(response)
        self.assertIsNotNone(data)

        committee_data = next(
            (c for c in data["per_committee"] if c["name"] == "Finance"), None
        )
        self.assertIsNotNone(committee_data)
        self.assertFalse(committee_data["has_events"])

    def test_chart_data_per_committee_task_counts(self):
        today = _today()
        _make_task(self.officer, committee=self.committee, status=TaskStatus.DONE)
        _make_task(
            self.officer,
            committee=self.committee,
            status=TaskStatus.TODO,
            due_date=today - timedelta(days=1),
        )
        _make_task(
            self.officer,
            committee=self.committee,
            status=TaskStatus.TODO,
            due_date=today + timedelta(days=5),
        )

        response = self._report()
        data = _get_chart_data(response)
        committee_data = next(
            (c for c in data["per_committee"] if c["name"] == "Finance"), None
        )
        self.assertEqual(committee_data["tasks_total"], 3)
        self.assertEqual(committee_data["tasks_completed"], 1)
        self.assertEqual(committee_data["tasks_overdue"], 1)

    def test_empty_range_produces_null_chart_data(self):
        """An empty date range (no events, no committees) produces null chart data."""
        # Remove the committee so there are truly no data sources.
        Committee.objects.all().delete()
        # Empty range far in the future (no events).
        today = _today()
        response = self.client.get(REPORT_URL, {
            "start_date": (today + timedelta(days=100)).isoformat(),
            "end_date": (today + timedelta(days=105)).isoformat(),
        })
        data = _get_chart_data(response)
        self.assertIsNone(data)

    def test_chartjs_script_tag_on_page(self):
        response = self._report()
        self.assertContains(response, "chart.umd.min.js")

    def test_charts_js_script_tag_on_page(self):
        response = self._report()
        self.assertContains(response, "charts.js")

    def test_member_gets_403(self):
        self.client.force_login(self.member)
        response = self.client.get(REPORT_URL)
        self.assertEqual(response.status_code, 403)
