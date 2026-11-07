"""Tests for the FR-09 unified audit history view and audit producers."""

from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, set_role
from accounts.testing import make_user
from events.models import (
    Attendance, AttendanceAction, AttendanceAuditLog, AttendanceAuditStatus, Event,
)
from membership.models import ApplicationStatus, MembershipApplication


def in_days(days):
    return timezone.now() + timedelta(days=days)


# ---------------------------------------------------------------------------
# Membership application history
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Attendance audit log — normal writes
# ---------------------------------------------------------------------------

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

    def test_marked_entry_has_stable_change_key(self):
        self._post_attendance([self.member.pk])
        log = AttendanceAuditLog.objects.get(event=self.event, user=self.member)
        attendance = Attendance.objects.get(event=self.event, user=self.member)
        self.assertEqual(log.change_key, f"mark:{attendance.pk}")

    def test_unmarking_attendance_creates_unmarked_log_entry(self):
        self._post_attendance([self.member.pk])
        self._post_attendance([])  # Remove from attendance.
        logs = AttendanceAuditLog.objects.filter(event=self.event, user=self.member).order_by("at")
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs[0].action, AttendanceAction.MARKED)
        self.assertEqual(logs[1].action, AttendanceAction.UNMARKED)

    def test_no_log_created_when_attendance_unchanged(self):
        """Submitting the same attendance list again does not add new log entries."""
        self._post_attendance([self.member.pk])
        count_after_first = AttendanceAuditLog.objects.count()
        self._post_attendance([self.member.pk])  # Same list.
        self.assertEqual(AttendanceAuditLog.objects.count(), count_after_first)

    def test_cancelled_event_attendance_is_rejected(self):
        self.event.cancelled = True
        self.event.save()
        self._post_attendance([self.member.pk])
        self.assertFalse(AttendanceAuditLog.objects.exists())


# ---------------------------------------------------------------------------
# Attendance audit log — partial-write resilience
# ---------------------------------------------------------------------------

def _fail_audit_get_or_create_once():
    """Return a side_effect that fails the first AttendanceAuditLog.get_or_create."""
    original = QuerySet.get_or_create
    calls = [0]

    def side_effect(qs, **kwargs):
        if qs.model is AttendanceAuditLog:
            calls[0] += 1
            if calls[0] == 1:
                raise DatabaseError("Injected audit write failure")
        return original(qs, **kwargs)

    return side_effect


def _fail_attendance_delete_once():
    """Return a side_effect that fails the first Attendance.delete call."""
    original = Attendance.delete
    calls = [0]

    def side_effect(self_record):
        calls[0] += 1
        if calls[0] == 1:
            raise DatabaseError("Injected delete failure")
        return original(self_record)

    return side_effect


class AttendanceAuditPartialWriteTests(TestCase):
    """DB failure/retry tests — exactly one audit entry despite partial writes."""

    def setUp(self):
        self.officer = make_user("pw-officer@example.com", Role.OFFICER)
        self.member = make_user("pw-member@example.com", Role.MEMBER)
        self.event = Event.objects.create(
            title="Partial Write Event",
            location="Lab",
            starts_at=in_days(1),
            created_by=self.officer,
        )

    def _post_attendance(self, user_pks):
        self.client.force_login(self.officer)
        data = {"attended": [str(pk) for pk in user_pks]}
        return self.client.post(reverse("events:attendance", args=[self.event.pk]), data)

    # --- Mark: failure before the first write (Attendance.get_or_create) ----

    def test_mark_normal_write_creates_one_attendance_and_one_audit_entry(self):
        """Baseline: marking writes exactly one attendance record and one audit entry."""
        self._post_attendance([self.member.pk])
        self.assertEqual(Attendance.objects.filter(event=self.event, user=self.member).count(), 1)
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.MARKED
            ).count(), 1,
        )

    # --- Mark: Attendance created, audit write fails → retry fixes it --------

    def test_mark_retry_after_audit_failure_creates_exactly_one_entry(self):
        """Attendance written; audit log write fails. Retry produces one audit entry."""
        with patch.object(
            QuerySet, "get_or_create", autospec=True, side_effect=_fail_audit_get_or_create_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([self.member.pk])

        # After the failure: attendance exists, audit does not.
        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertFalse(
            AttendanceAuditLog.objects.filter(event=self.event, user=self.member).exists()
        )

        # Retry: audit entry is created; still only one of each.
        self._post_attendance([self.member.pk])
        self.assertEqual(Attendance.objects.filter(event=self.event, user=self.member).count(), 1)
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.MARKED
            ).count(), 1,
        )

    # --- Unmark: audit written, delete fails → retry fixes it, no duplicates -

    def test_unmark_retry_after_delete_failure_produces_one_audit_entry(self):
        """Audit written but delete fails. Retry deletes without duplicating audit."""
        # Start with the member marked.
        self._post_attendance([self.member.pk])
        attendance_pk = Attendance.objects.get(event=self.event, user=self.member).pk

        with patch.object(
            Attendance, "delete", autospec=True, side_effect=_fail_attendance_delete_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])  # Attempt to unmark.

        # After the failure: attendance still exists, audit entry was written.
        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.UNMARKED
            ).count(), 1,
        )

        # Retry: attendance is deleted; audit is not duplicated.
        self._post_attendance([])
        self.assertFalse(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.UNMARKED
            ).count(), 1,
        )

    # --- Unmark: audit write fails → retry writes audit and deletes ----------

    def test_unmark_retry_after_audit_failure_creates_entry_and_deletes(self):
        """Audit write fails before delete. Retry writes audit and deletes attendance."""
        self._post_attendance([self.member.pk])

        with patch.object(
            QuerySet, "get_or_create", autospec=True, side_effect=_fail_audit_get_or_create_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])  # Attempt to unmark; audit fails.

        # After the failure: attendance still exists, no audit entry written.
        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertFalse(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.UNMARKED
            ).exists()
        )

        # Retry: audit entry created and attendance deleted.
        self._post_attendance([])
        self.assertFalse(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.UNMARKED
            ).count(), 1,
        )


def _fail_audit_status_update_once():
    """Return a side_effect that fails the first status-only AttendanceAuditLog save.

    get_or_create also calls save() to insert, so only saves that pass
    update_fields (the pending -> completed step) are failed.
    """
    original = AttendanceAuditLog.save
    calls = [0]

    def side_effect(self_log, *args, **kwargs):
        if kwargs.get("update_fields"):
            calls[0] += 1
            if calls[0] == 1:
                raise DatabaseError("Injected status update failure")
        return original(self_log, *args, **kwargs)

    return side_effect


class AttendanceAuditPendingAndActorTests(TestCase):
    """Pending removals stay separate from completed changes; repairs keep the original actor."""

    def setUp(self):
        self.officer = make_user("pa-officer@example.com", Role.OFFICER)
        self.other_officer = make_user("pa-other-officer@example.com", Role.OFFICER)
        self.admin = make_user("pa-admin@example.com", Role.ADMIN)
        self.member = make_user("pa-member@example.com", Role.MEMBER)
        self.event = Event.objects.create(
            title="Pending Audit Event",
            location="Hall",
            starts_at=in_days(1),
            created_by=self.officer,
        )

    def _post_attendance(self, user_pks, as_user=None):
        self.client.force_login(as_user or self.officer)
        data = {"attended": [str(pk) for pk in user_pks]}
        return self.client.post(reverse("events:attendance", args=[self.event.pk]), data)

    def _removals(self, **filters):
        return AttendanceAuditLog.objects.filter(
            event=self.event, user=self.member, action=AttendanceAction.UNMARKED, **filters
        )

    def _audit_page(self):
        self.client.force_login(self.admin)
        return self.client.get(reverse("core:audit_history"))

    # --- Failed delete: the removal stays pending, not completed -------------

    def test_failed_delete_leaves_pending_removal_hidden_from_history(self):
        self._post_attendance([self.member.pk])
        with patch.object(
            Attendance, "delete", autospec=True, side_effect=_fail_attendance_delete_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])

        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(self._removals(status=AttendanceAuditStatus.PENDING).count(), 1)
        self.assertFalse(self._removals(status=AttendanceAuditStatus.COMPLETED).exists())
        self.assertNotContains(self._audit_page(), "marked absent")

    def test_failed_delete_then_member_kept_records_no_removal(self):
        """Chau's case: the next save keeps the member present, so no removal is recorded."""
        self._post_attendance([self.member.pk])
        with patch.object(
            Attendance, "delete", autospec=True, side_effect=_fail_attendance_delete_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])

        self._post_attendance([self.member.pk])  # Next save keeps the member present.

        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertFalse(self._removals().exists())
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.MARKED
            ).count(), 1,
        )
        self.assertNotContains(self._audit_page(), "marked absent")

    def test_failed_delete_then_retried_removal_is_completed_once(self):
        self._post_attendance([self.member.pk])
        with patch.object(
            Attendance, "delete", autospec=True, side_effect=_fail_attendance_delete_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])

        self._post_attendance([])  # Retry the removal.

        self.assertFalse(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(self._removals().count(), 1)
        self.assertEqual(self._removals().get().status, AttendanceAuditStatus.COMPLETED)
        self.assertContains(self._audit_page(), "marked absent")

    def test_kept_member_can_be_removed_later_with_one_completed_entry(self):
        self._post_attendance([self.member.pk])
        with patch.object(
            Attendance, "delete", autospec=True, side_effect=_fail_attendance_delete_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])
        self._post_attendance([self.member.pk])  # Pending removal discarded.

        self._post_attendance([])  # A later, successful removal.

        self.assertFalse(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(self._removals().count(), 1)
        self.assertEqual(self._removals().get().status, AttendanceAuditStatus.COMPLETED)

    # --- Delete succeeded but completing the entry failed --------------------

    def test_status_update_failure_after_delete_is_completed_on_next_save(self):
        self._post_attendance([self.member.pk])
        with patch.object(
            AttendanceAuditLog, "save", autospec=True, side_effect=_fail_audit_status_update_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])

        # The member was removed, but the entry is still pending.
        self.assertFalse(Attendance.objects.filter(event=self.event, user=self.member).exists())
        self.assertEqual(self._removals(status=AttendanceAuditStatus.PENDING).count(), 1)

        self._post_attendance([])  # Any later save resolves it.

        self.assertEqual(self._removals().count(), 1)
        self.assertEqual(self._removals().get().status, AttendanceAuditStatus.COMPLETED)

    def test_status_update_failure_then_member_marked_again_keeps_both_changes(self):
        self._post_attendance([self.member.pk])
        with patch.object(
            AttendanceAuditLog, "save", autospec=True, side_effect=_fail_audit_status_update_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([])

        self._post_attendance([self.member.pk])  # Member marked present again.

        # The earlier removal did happen, so it is completed, then a new mark follows.
        self.assertEqual(self._removals().get().status, AttendanceAuditStatus.COMPLETED)
        self.assertEqual(
            AttendanceAuditLog.objects.filter(
                event=self.event, user=self.member, action=AttendanceAction.MARKED
            ).count(), 2,
        )
        self.assertTrue(Attendance.objects.filter(event=self.event, user=self.member).exists())

    # --- Repaired mark entries keep the original actor and time --------------

    def test_repaired_mark_entry_credits_original_officer(self):
        """Chau's case: another officer's retry repairs the entry for the original marker."""
        with patch.object(
            QuerySet, "get_or_create", autospec=True, side_effect=_fail_audit_get_or_create_once()
        ):
            with self.assertRaises(DatabaseError):
                self._post_attendance([self.member.pk], as_user=self.officer)

        self._post_attendance([self.member.pk], as_user=self.other_officer)

        attendance = Attendance.objects.get(event=self.event, user=self.member)
        log = AttendanceAuditLog.objects.get(
            event=self.event, user=self.member, action=AttendanceAction.MARKED
        )
        self.assertEqual(attendance.marked_by, self.officer)
        self.assertEqual(log.actor, self.officer)
        self.assertEqual(log.at, attendance.marked_at)
        self.assertEqual(log.status, AttendanceAuditStatus.COMPLETED)

    def test_attendance_without_audit_entry_is_backfilled_with_original_marker(self):
        """Attendance saved before audit history existed is credited to whoever marked it."""
        attendance = Attendance.objects.create(
            event=self.event, user=self.member, marked_by=self.officer
        )
        self._post_attendance([self.member.pk], as_user=self.other_officer)

        attendance.refresh_from_db()  # MongoDB stores times to the millisecond.
        log = AttendanceAuditLog.objects.get(change_key=f"mark:{attendance.pk}")
        self.assertEqual(log.actor, self.officer)
        self.assertEqual(log.at, attendance.marked_at)

    def test_removal_credits_officer_who_removed(self):
        self._post_attendance([self.member.pk], as_user=self.officer)
        self._post_attendance([], as_user=self.other_officer)
        self.assertEqual(self._removals().get().actor, self.other_officer)


# ---------------------------------------------------------------------------
# Audit history view — access control and content
# ---------------------------------------------------------------------------

class AuditHistoryViewTests(TestCase):
    """The unified audit history page is accessible to admins only."""

    def setUp(self):
        self.officer = make_user("view-officer@example.com", Role.OFFICER)
        self.admin = make_user("view-admin@example.com", Role.ADMIN)
        self.member = make_user("view-member@example.com", Role.MEMBER)
        self.applicant = make_user("view-applicant@example.com")

    def url(self):
        return reverse("core:audit_history")

    def test_admin_can_access_audit_history(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit History")

    def test_officer_cannot_access_audit_history(self):
        self.client.force_login(self.officer)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 403)

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
        self.client.force_login(self.admin)
        response = self.client.get(self.url())
        self.assertContains(response, "Role change")
        self.assertContains(response, "Applicant")
        self.assertContains(response, "Member")

    def test_membership_submission_appears_in_audit_history(self):
        app = MembershipApplication(user=self.applicant, statement="Please let me in.")
        app.save()
        self.client.force_login(self.admin)
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
        self.client.force_login(self.admin)
        response = self.client.get(self.url())
        self.assertContains(response, "Attendance")
        self.assertContains(response, "marked present")

    def test_audit_history_link_visible_to_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, reverse("core:audit_history"))

    def test_audit_history_link_not_visible_to_officer(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, reverse("core:audit_history"))

    def test_audit_history_link_not_visible_to_member(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, reverse("core:audit_history"))
