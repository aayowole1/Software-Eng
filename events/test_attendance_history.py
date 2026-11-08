"""
Tests for US-13: Members can view their own attendance history.

Covers:
- Only own records shown (not other members').
- Cancelled and future events excluded.
- Events before joining excluded.
- Attendance rate calculation including zero events.
- Dashboard summary.
- Access for applicants and signed-out users.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .models import Attendance, Event

# How far back members are considered to have joined in most tests.
_JOINED_DAYS_AGO = 30


def days(n):
    return timezone.now() + timedelta(days=n)


def _backdate_joined(user, days_ago=_JOINED_DAYS_AGO):
    """Move a user's date_joined into the past so test events are eligible."""
    user.date_joined = timezone.now() - timedelta(days=days_ago)
    user.save(update_fields=["date_joined"])


class AttendanceHistoryProfileTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.other = make_user("other@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")
        # Push date_joined back so past events (days(-1) etc.) are included.
        _backdate_joined(self.member)
        _backdate_joined(self.other)

    def make_past_event(self, title="Past event", delta_days=-1, **kwargs):
        return Event.objects.create(
            title=title,
            location="Room 1",
            starts_at=days(delta_days),
            created_by=self.officer,
            **kwargs,
        )

    def attend(self, user, event):
        return Attendance.objects.create(event=event, user=user, marked_by=self.officer)

    # --- Access control ---------------------------------------------------

    def test_signed_out_redirects_to_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(response, f"/accounts/login/?next=/accounts/me/")

    def test_applicant_sees_no_attendance_section(self):
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "My attendance")
        self.assertNotIn("attendance_history", response.context)

    # --- Own records only -------------------------------------------------

    def test_member_sees_own_attendance_only(self):
        # Both member and other attend the same event.  The view must show one
        # row for the event (not two) with the logged-in member's own status.
        event = self.make_past_event("Team social")
        self.attend(self.member, event)
        self.attend(self.other, event)

        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Team social")
        # Exactly one "Attended" badge — not two (one per member who attended)
        self.assertEqual(response.content.decode().count(">Attended<"), 1)
        # Rate shown as 1/1 for the member's own view
        self.assertContains(response, "1 of 1")

    def test_attended_badge_shown_for_attended_event(self):
        event = self.make_past_event("Attended event")
        self.attend(self.member, event)
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Attended")

    def test_not_recorded_shown_for_missed_event(self):
        self.make_past_event("Missed event")
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Not recorded")

    # --- Exclusions -------------------------------------------------------

    def test_cancelled_events_excluded(self):
        self.make_past_event("Cancelled meetup", cancelled=True)
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(response, "Cancelled meetup")

    def test_future_events_excluded(self):
        Event.objects.create(
            title="Future event",
            location="Room 1",
            starts_at=days(7),
            created_by=self.officer,
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(response, "Future event")

    def test_events_before_joining_excluded(self):
        # Explicitly set date_joined to now so any event before that is excluded.
        self.member.date_joined = timezone.now()
        self.member.save(update_fields=["date_joined"])
        # Event starts 1 second before date_joined — must not appear.
        Event.objects.create(
            title="Pre-join event",
            location="Room 1",
            starts_at=timezone.now() - timedelta(seconds=1),
            created_by=self.officer,
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(response, "Pre-join event")

    # --- Rate calculation -------------------------------------------------

    def test_no_past_events_shows_no_past_events_message(self):
        # Member has no eligible events yet (date_joined = now, no past events created).
        self.member.date_joined = timezone.now()
        self.member.save(update_fields=["date_joined"])
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "No past events yet")
        # The rate summary line must not appear.
        self.assertNotContains(response, "events (")

    def test_rate_calculated_correctly(self):
        # 2 events, member attended 1 → 50 %
        event1 = self.make_past_event("Event A")
        self.make_past_event("Event B")
        self.attend(self.member, event1)
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "1 of 2")
        self.assertContains(response, "50%")

    def test_full_attendance_rate(self):
        event1 = self.make_past_event("Event A")
        event2 = self.make_past_event("Event B")
        self.attend(self.member, event1)
        self.attend(self.member, event2)
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "100%")

    # --- Newest first ordering --------------------------------------------

    def test_events_ordered_newest_first(self):
        self.make_past_event("Older event", delta_days=-5)
        self.make_past_event("Newer event", delta_days=-1)
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        content = response.content.decode()
        self.assertIn("Newer event", content)
        self.assertIn("Older event", content)
        self.assertLess(content.index("Newer event"), content.index("Older event"))


class AttendanceDashboardSummaryTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")
        # Push date_joined back so past events are eligible.
        _backdate_joined(self.member)

    def make_past_event(self, title="Past event", **kwargs):
        return Event.objects.create(
            title=title,
            location="Room 1",
            starts_at=timezone.now() - timedelta(days=1),
            created_by=self.officer,
            **kwargs,
        )

    def attend(self, user, event):
        return Attendance.objects.create(event=event, user=user, marked_by=self.officer)

    def test_dashboard_shows_no_past_events_when_none(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "My attendance")
        self.assertContains(response, "No past events yet")

    def test_dashboard_shows_attendance_summary(self):
        event1 = self.make_past_event("Event A")
        self.make_past_event("Event B")
        self.attend(self.member, event1)
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Attended 1 of 2 events (50%)")

    def test_dashboard_summary_links_to_profile_attendance_section(self):
        self.make_past_event("Event A")
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, 'href="/accounts/me/#attendance"')

    def test_dashboard_no_attendance_section_for_applicant(self):
        self.make_past_event("Event A")
        self.client.force_login(self.applicant)
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "My attendance")

    def test_dashboard_no_attendance_section_for_anonymous(self):
        self.make_past_event("Event A")
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "My attendance")

    def test_cancelled_events_excluded_from_dashboard_summary(self):
        self.make_past_event("Cancelled event", cancelled=True)
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        # No eligible events → "No past events yet"
        self.assertContains(response, "No past events yet")
        self.assertNotContains(response, "Cancelled event")


class AttendanceCountsFromApprovalTests(TestCase):
    """Review fix: attendance counts from membership approval, not account sign-up."""

    def setUp(self):
        from membership.models import ApplicationStatus, MembershipApplication

        self.ApplicationStatus = ApplicationStatus
        self.MembershipApplication = MembershipApplication
        self.officer = make_user("approval-officer@example.com", Role.OFFICER)
        self.member = make_user("approval-member@example.com", Role.MEMBER)
        _backdate_joined(self.member, days_ago=30)  # signed up 30 days ago

    def approve(self, days_ago, user=None):
        return self.MembershipApplication.objects.create(
            user=user or self.member,
            statement="I'd like to join.",
            status=self.ApplicationStatus.APPROVED,
            reviewed_by=self.officer,
            reviewed_at=timezone.now() - timedelta(days=days_ago),
        )

    def reject(self, days_ago):
        return self.MembershipApplication.objects.create(
            user=self.member,
            statement="Please reconsider.",
            status=self.ApplicationStatus.REJECTED,
            reviewed_by=self.officer,
            reviewed_at=timezone.now() - timedelta(days=days_ago),
            review_note="Not yet.",
        )

    def event(self, title, delta_days):
        return Event.objects.create(
            title=title, location="Room 1", starts_at=days(delta_days), created_by=self.officer,
        )

    def summary(self):
        return Event.objects.attendance_summary_for(self.member)

    def test_events_while_pending_are_not_counted(self):
        """Chau's case: events between sign-up and approval don't lower the rate."""
        self.approve(days_ago=10)
        self.event("While pending", -20)
        attended = self.event("After approval", -5)
        Attendance.objects.create(event=attended, user=self.member, marked_by=self.officer)

        summary = self.summary()

        self.assertEqual([row["event"].title for row in summary["history"]], ["After approval"])
        self.assertEqual((summary["attended"], summary["total"], summary["rate"]), (1, 1, 100))

    def test_profile_and_dashboard_use_the_approval_date(self):
        self.approve(days_ago=10)
        self.event("While pending", -20)
        attended = self.event("After approval", -5)
        Attendance.objects.create(event=attended, user=self.member, marked_by=self.officer)
        self.client.force_login(self.member)

        profile = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(profile, "While pending")
        self.assertContains(profile, "Attended 1 of 1 event (100%)")
        approved_on = timezone.localtime(timezone.now() - timedelta(days=10)).strftime("%b %-d, %Y")
        self.assertContains(profile, f"Counting events since your membership started on {approved_on}.")

        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertEqual(dashboard.context["attendance_summary"]["total"], 1)
        self.assertEqual(dashboard.context["attendance_summary"]["rate"], 100)

    def test_counts_from_the_most_recent_approval(self):
        self.approve(days_ago=25)
        self.reject(days_ago=15)
        self.approve(days_ago=5)
        self.event("Earlier membership", -20)
        self.event("Current membership", -2)

        titles = [row["event"].title for row in self.summary()["history"]]

        self.assertEqual(titles, ["Current membership"])

    def test_rejected_or_pending_applications_do_not_set_the_start(self):
        self.reject(days_ago=10)
        self.MembershipApplication.objects.create(
            user=self.member, statement="Trying again.", status=self.ApplicationStatus.PENDING,
        )
        self.event("After sign-up", -20)

        # No approval on record, so the sign-up date is used.
        self.assertEqual(self.summary()["total"], 1)

    def test_accounts_never_approved_through_an_application_use_sign_up_date(self):
        self.event("After sign-up", -20)
        self.event("Before sign-up", -40)

        summary = self.summary()

        self.assertEqual([row["event"].title for row in summary["history"]], ["After sign-up"])
        self.assertEqual(summary["since"], self.member.date_joined)

    def test_other_members_approvals_do_not_affect_this_member(self):
        other = make_user("approval-other@example.com", Role.MEMBER)
        self.approve(days_ago=1, user=other)
        self.event("After sign-up", -20)

        self.assertEqual(self.summary()["total"], 1)
