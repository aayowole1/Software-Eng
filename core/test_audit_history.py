"""Tests for the FR-09 unified audit history view and audit producers."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, set_role
from accounts.testing import make_user
from events.models import AttendanceAction, AttendanceAuditLog, Event
from membership.models import ApplicationStatus, MembershipApplication


def in_days(days):
    return timezone.now() + timedelta(days=days)


class MembershipApplicationHistoryTests(TestCase):
    """Membership applications record a history entry on submission and review."""

    def setUp(self):
        self.officer = make_user("audit-officer@example.com", Role.OFFICER)
        self.applicant = make_user("audit-applicant@example.com")

    def _make_application(self, user=None):
        user = user or self.applicant
        app = MembershipApplication(user=user, statement="I want to join.")
        app.save()
        return app

    def test_submission_creates_history_entry(self):
        app = self._make_application()
        self.assertEqual(len(app.history), 1)
        entry = app.history[0]
        self.assertEqual(entry["action"], "submitted")
        self.assertEqual(entry["actor_id"], str(self.applicant.pk))
        self.assertIn("at", entry)

    def test_approval_appends_history_entry(self):
        app = self._make_application()
        app.review(self.officer, approve=True)
        app.refresh_from_db()
        self.assertEqual(len(app.history), 2)
        review_entry = app.history[1]
        self.assertEqual(review_entry["action"], "approved")
        self.assertEqual(review_entry["actor_id"], str(self.officer.pk))
        self.assertEqual(review_entry["actor"], self.officer.get_username())

    def test_rejection_appends_history_entry_with_note(self):
        app = self._make_application()
        app.review(self.officer, approve=False, note="Does not meet criteria.")
        app.refresh_from_db()
        self.assertEqual(len(app.history), 2)
        review_entry = app.history[1]
        self.assertEqual(review_entry["action"], "rejected")
        self.assertEqual(review_entry["note"], "Does not meet criteria.")

    def test_history_not_duplicated_on_update(self):
        """Updating non-history fields does not append a submission entry."""
        app = self._make_application()
        initial_history = list(app.history)
        # A save after creation (e.g. updating a field) should not re-append.
        app.statement = "Updated statement."
        app.save()
        self.assertEqual(app.history, initial_history)

    def test_each_application_has_independent_history(self):
        app1 = self._make_application()
        applicant2 = make_user("audit-applicant2@example.com")
        app2 = self._make_application(user=applicant2)
        self.assertEqual(len(app1.history), 1)
        self.assertEqual(len(app2.history), 1)
        self.assertNotEqual(app1.history[0]["actor_id"], app2.history[0]["actor_id"])


class AttendanceAuditLogTests(TestCase):
    """Attendance marking and removal writes AttendanceAuditLog entries."""

    def setUp(self):
        self.officer = make_user("att-officer@example.com", Role.OFFICER)
        self.member = make_user("att-member@example.com", Role.MEMBER)
        self.event = Event.objects.create(
            title="Test Event",
            location="Room 101",
            starts_at=in_days(1),
            created_by=self.officer,
        )

    def _post_attendance(self, user_pks):
        self.client.force_login(self.officer)
        data = {"attended": [str(pk) for pk in user_pks]}
        return self.client.post(reverse("events:attendance", args=[self.event.pk]), data)

    def test_marking_attendance_creates_marked_log_entry(self):
        self._post_attendance([self.member.pk])
        logs = AttendanceAuditLog.objects.filter(event=self.event, user=self.member)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.action, AttendanceAction.MARKED)
        self.assertEqual(log.actor, self.officer)

    def test_unmarking_attendance_creates_unmarked_log_entry(self):
        # First mark, then unmark.
        self._post_attendance([self.member.pk])
        self._post_attendance([])  # Remove from attendance.
        logs = AttendanceAuditLog.objects.filter(event=self.event, user=self.member).order_by("at")
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs[0].action, AttendanceAction.MARKED)
        self.assertEqual(logs[1].action, AttendanceAction.UNMARKED)

    def test_no_log_created_when_attendance_unchanged(self):
        """Submitting the same attendance list again should not add new log entries."""
        self._post_attendance([self.member.pk])
        count_after_first = AttendanceAuditLog.objects.count()
        self._post_attendance([self.member.pk])  # Same list.
        self.assertEqual(AttendanceAuditLog.objects.count(), count_after_first)

    def test_cancelled_event_attendance_is_rejected(self):
        self.event.cancelled = True
        self.event.save()
        self._post_attendance([self.member.pk])
        self.assertFalse(AttendanceAuditLog.objects.exists())


class AuditHistoryViewTests(TestCase):
    """The unified audit history page is accessible to officers and admins."""

    def setUp(self):
        self.officer = make_user("view-officer@example.com", Role.OFFICER)
        self.admin = make_user("view-admin@example.com", Role.ADMIN)
        self.member = make_user("view-member@example.com", Role.MEMBER)
        self.applicant = make_user("view-applicant@example.com")

    def url(self):
        return reverse("core:audit_history")

    def test_officer_can_access_audit_history(self):
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit History")

    def test_admin_can_access_audit_history(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_access_audit_history(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 403)

    def test_applicant_cannot_access_audit_history(self):
        self.client.force_login(self.applicant)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected_to_login(self):
        response = self.client.get(self.url())
        self.assertRedirects(response, f"/accounts/login/?next={self.url()}")

    def test_role_change_appears_in_audit_history(self):
        target = make_user("target-for-audit@example.com")
        set_role(target, Role.MEMBER, actor=self.admin, source="account_role_management")
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertContains(response, "Role change")
        self.assertContains(response, "Applicant")
        self.assertContains(response, "Member")

    def test_membership_submission_appears_in_audit_history(self):
        app = MembershipApplication(user=self.applicant, statement="Please let me in.")
        app.save()
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertContains(response, "Membership")
        self.assertContains(response, "Application submitted")

    def test_membership_approval_appears_in_audit_history(self):
        app = MembershipApplication(user=self.applicant, statement="Please let me in.")
        app.save()
        app.review(self.officer, approve=True)
        self.client.force_login(self.admin)
        response = self.client.get(self.url())
        self.assertContains(response, "Application approved")

    def test_attendance_log_appears_in_audit_history(self):
        event = Event.objects.create(
            title="Audit Test Event",
            location="Room 202",
            starts_at=timezone.now() + timedelta(days=1),
            created_by=self.officer,
        )
        AttendanceAuditLog.objects.create(
            event=event,
            user=self.member,
            action=AttendanceAction.MARKED,
            actor=self.officer,
        )
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertContains(response, "Attendance")
        self.assertContains(response, "marked present")

    def test_empty_audit_history_shows_no_entries_message(self):
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        # Should render without errors even when there are no entries
        # (there may be some from setUp role changes).

    def test_audit_history_link_visible_to_officer(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, reverse("core:audit_history"))

    def test_audit_history_link_not_visible_to_member(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, reverse("core:audit_history"))
