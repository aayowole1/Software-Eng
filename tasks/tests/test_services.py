from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from meetings.models import ActionItem, DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication

from tasks.forms import TaskForm, TaskImportForm, TaskStatusForm
from tasks.models import (
    Task, TaskPriority, TaskStatus, can_claim_task, can_manage_tasks,
    can_update_task, eligible_assignees,
)
from tasks.services import (
    TaskConflict, claim_task, create_task, import_action_items, update_task,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskServiceTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.peer = make_user("peer@example.com", Role.MEMBER)
        self.outsider = make_user("outsider@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")
        self.committee = Committee.objects.create(name="Robotics", created_by=self.officer)
        for user in [self.member, self.peer]:
            CommitteeMember.objects.create(committee=self.committee, user=user)

    def task(self, **fields):
        return create_task(self.officer, title="Prepare the demonstration", **fields)

    def test_creation_persists_delegation_dates_priority_and_audit(self):
        due = timezone.localdate() + timedelta(days=2)
        task = self.task(
            committee=self.committee, assignee=self.member,
            due_date=due, priority=TaskPriority.HIGH,
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.assignee, self.member)
        self.assertEqual(task.due_date, due)
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.version, 0)
        self.assertEqual(task.history[0]["actor_id"], str(self.officer.pk))
        self.assertEqual(task.history[0]["changes"]["assignee"]["to"], str(self.member.pk))

    def test_manual_tasks_have_distinct_nonnullable_origin_keys(self):
        first, second = self.task(), self.task()
        self.assertNotEqual(first.origin_key, second.origin_key)
        self.assertTrue(first.origin_key.startswith("manual:"))

    def test_only_current_active_officers_manage_tasks(self):
        for user in [AnonymousUser(), self.applicant, self.member]:
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                create_task(user, title="Unauthorized")
        Profile.objects.filter(user=self.officer).update(is_suspended=True)
        # The caller's user/profile objects may have been loaded before suspension.
        self.assertFalse(can_manage_tasks(self.officer))
        with self.assertRaises(PermissionDenied):
            self.task()
        self.assertFalse(Task.objects.exists())

    def test_deactivated_stale_officer_instance_cannot_create(self):
        self.officer.__class__.objects.filter(pk=self.officer.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.task()

    def test_incomplete_membership_access_update_blocks_tasks_until_finalized(self):
        assigned = self.task(committee=self.committee, assignee=self.member)
        unassigned = self.task(committee=self.committee)
        application = MembershipApplication.objects.create(
            user=self.member, statement="Reviewed application",
            status=ApplicationStatus.APPROVED, reviewed_by=self.officer,
            reviewed_at=timezone.now(), access_update_pending=True,
        )
        # An interrupted approval may already have set Member and is_active.
        # Its durable unfinished marker still withholds effective task access.
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.profile.role, Role.MEMBER)
        self.assertFalse(Task.objects.visible_to(self.member).exists())
        self.assertFalse(can_update_task(self.member, assigned))
        self.assertFalse(can_claim_task(self.member, unassigned))
        self.assertFalse(eligible_assignees(self.committee).filter(pk=self.member.pk).exists())
        with self.assertRaises(PermissionDenied):
            claim_task(self.member, unassigned, 0)
        with self.assertRaises(ValidationError):
            self.task(committee=self.committee, assignee=self.member)

        MembershipApplication.objects.filter(pk=application.pk).update(access_update_pending=False)
        self.assertEqual(Task.objects.visible_to(self.member).count(), 2)
        self.assertTrue(can_update_task(self.member, assigned))
        self.assertTrue(eligible_assignees(self.committee).filter(pk=self.member.pk).exists())
        claimed = claim_task(self.member, unassigned, 0)
        self.assertEqual(claimed.assignee_id, self.member.pk)
        self.assertEqual(claimed.history[-1]["action"], "claimed")
        normal = self.task(committee=self.committee, assignee=self.member)
        self.assertEqual(normal.assignee_id, self.member.pk)

    def test_invalid_fields_do_not_create_a_task(self):
        for fields in [{"title": "   "}, {"priority": "urgent"}, {"status": "invented"}]:
            values = {"title": "Valid title", **fields}
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                create_task(self.officer, **values)
        with self.assertRaises(ValidationError):
            create_task(self.officer, title="Unknown field", version=9)
        self.assertFalse(Task.objects.exists())

    def test_assignment_rejects_applicants_and_noncommittee_members(self):
        for assignee in [self.applicant, self.outsider]:
            with self.subTest(assignee=assignee), self.assertRaises(ValidationError):
                self.task(committee=self.committee, assignee=assignee)
        self.assertFalse(Task.objects.exists())

    def test_assignment_rejects_inactive_and_suspended_members(self):
        self.member.__class__.objects.filter(pk=self.member.pk).update(is_active=False)
        Profile.objects.filter(user=self.peer).update(is_suspended=True)
        for assignee in [self.member, self.peer]:
            with self.subTest(assignee=assignee), self.assertRaises(ValidationError):
                self.task(assignee=assignee)

    def test_visibility_hides_other_general_and_other_committee_tasks(self):
        own = self.task(assignee=self.member)
        committee_task = self.task(committee=self.committee)
        hidden_general = self.task(assignee=self.outsider)
        other_committee = Committee.objects.create(name="Finance", created_by=self.officer)
        hidden_committee = self.task(committee=other_committee)
        visible = set(Task.objects.visible_to(self.member).values_list("pk", flat=True))
        self.assertEqual(visible, {own.pk, committee_task.pk})
        self.assertEqual(Task.objects.visible_to(self.officer).count(), 4)
        self.assertNotIn(hidden_general.pk, visible)
        self.assertNotIn(hidden_committee.pk, visible)
        self.assertFalse(Task.objects.visible_to(self.applicant).exists())
        self.assertFalse(Task.objects.visible_to(AnonymousUser()).exists())

    def test_departed_committee_member_loses_even_assigned_task_access(self):
        task = self.task(committee=self.committee, assignee=self.member)
        CommitteeMember.objects.filter(committee=self.committee, user=self.member).delete()
        self.assertFalse(Task.objects.visible_to(self.member).exists())
        self.assertFalse(can_update_task(self.member, task))
        with self.assertRaises(PermissionDenied):
            update_task(self.member, task, {"status": TaskStatus.IN_PROGRESS}, 0)

    def test_assignee_updates_only_progress_and_audit_is_persisted(self):
        task = self.task(assignee=self.member)
        updated = update_task(self.member, task, {"status": TaskStatus.IN_PROGRESS}, 0)
        self.assertEqual(updated.version, 1)
        self.assertEqual(updated.history[-1]["changes"]["status"], {"from": "todo", "to": "in_progress"})
        self.assertEqual(updated.history[-1]["actor_id"], str(self.member.pk))
        for changes in [{"assignee": self.peer}, {"title": "Changed"}, {"due_date": None}]:
            with self.subTest(changes=changes), self.assertRaises(PermissionDenied):
                update_task(self.member, updated, changes, 1)
        updated.refresh_from_db()
        self.assertEqual(updated.version, 1)
        self.assertEqual(len(updated.history), 2)

    def test_unassigned_and_other_assigned_tasks_cannot_be_updated_by_member(self):
        for fields in [{"committee": self.committee}, {"assignee": self.peer}]:
            task = self.task(**fields)
            with self.subTest(fields=fields), self.assertRaises(PermissionDenied):
                update_task(self.member, task, {"status": TaskStatus.DONE}, 0)

    def test_stale_update_cannot_overwrite_new_state_or_append_audit(self):
        task = self.task(assignee=self.member)
        stale = Task.objects.get(pk=task.pk)
        update_task(self.member, task, {"status": TaskStatus.IN_PROGRESS}, 0)
        with self.assertRaises(TaskConflict):
            update_task(self.officer, stale, {"title": "Stale overwrite"}, 0)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(task.title, "Prepare the demonstration")
        self.assertEqual(task.version, 1)
        self.assertEqual(len(task.history), 2)

    def test_update_reloads_state_instead_of_trusting_mutated_form_instance(self):
        task = self.task()
        task.title = "Already changed by form validation"
        updated = update_task(self.officer, task, {"title": "Already changed by form validation"}, 0)
        self.assertEqual(updated.history[-1]["changes"]["title"]["from"], "Prepare the demonstration")
        self.assertEqual(updated.version, 1)

    def test_noop_update_has_no_duplicate_history_or_version_increment(self):
        task = self.task()
        result = update_task(self.officer, task, {"status": TaskStatus.TODO}, 0)
        self.assertEqual(result.version, 0)
        self.assertEqual(len(result.history), 1)

    def test_conditional_write_failure_does_not_report_success(self):
        task = self.task()
        with patch("tasks.models.TaskQuerySet.update", return_value=0):
            with self.assertRaises(TaskConflict):
                update_task(self.officer, task, {"status": TaskStatus.DONE}, 0)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(len(task.history), 1)

    def test_invalid_or_missing_version_is_rejected(self):
        task = self.task()
        for version in [None, -1, True, "0"]:
            with self.subTest(version=version), self.assertRaises(ValidationError):
                update_task(self.officer, task, {"status": TaskStatus.DONE}, version)

    def test_committee_member_claim_is_atomic_and_audited(self):
        task = self.task(committee=self.committee)
        self.assertTrue(can_claim_task(self.member, task))
        claimed = claim_task(self.member, task, 0)
        self.assertEqual(claimed.assignee, self.member)
        self.assertEqual(claimed.version, 1)
        self.assertEqual(claimed.history[-1]["action"], "claimed")
        with self.assertRaises(TaskConflict):
            claim_task(self.peer, task, 0)
        task.refresh_from_db()
        self.assertEqual(task.assignee, self.member)
        self.assertEqual(len(task.history), 2)

    def test_claim_requires_current_committee_membership_and_unfinished_task(self):
        committee_task = self.task(committee=self.committee)
        with self.assertRaises(PermissionDenied):
            claim_task(self.outsider, committee_task, 0)
        for task in [self.task(), self.task(committee=self.committee, status=TaskStatus.DONE)]:
            with self.subTest(task=task.pk), self.assertRaises(PermissionDenied):
                claim_task(self.member, task, 0)

    def test_overdue_excludes_today_future_and_done_tasks(self):
        today = timezone.localdate()
        self.assertTrue(self.task(due_date=today - timedelta(days=1)).is_overdue)
        self.assertFalse(self.task(due_date=today).is_overdue)
        self.assertFalse(self.task(due_date=today + timedelta(days=1)).is_overdue)
        self.assertFalse(self.task(due_date=today - timedelta(days=1), status=TaskStatus.DONE).is_overdue)
        self.assertFalse(self.task().is_overdue)

    def test_committee_cannot_be_deleted_while_task_retains_history(self):
        task = self.task(committee=self.committee)
        with self.assertRaises(ProtectedError):
            self.committee.delete()
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def approved_draft(self):
        draft = MeetingDraft.objects.create(title="Weekly meeting", notes="Reviewed notes", created_by=self.officer)
        accepted = ActionItem.objects.create(draft=draft, description="Prepare the exhibition", accepted=True)
        ActionItem.objects.create(draft=draft, description="Not accepted", accepted=False, position=1)
        draft.review(self.officer, DraftStatus.APPROVED)
        return draft, accepted

    def test_import_requires_approval_and_officer_and_only_accepted_items(self):
        draft, accepted = self.approved_draft()
        with self.assertRaises(PermissionDenied):
            import_action_items(self.member, draft)
        pending = MeetingDraft.objects.create(title="Pending", notes="Do not create tasks")
        for status in [DraftStatus.PENDING_REVIEW, DraftStatus.REJECTED, DraftStatus.REVISION_REQUESTED]:
            pending.status = status
            pending.save()
            with self.subTest(status=status), self.assertRaises(ValidationError):
                import_action_items(self.officer, pending)
        result = import_action_items(self.officer, draft, committee=self.committee, assignee=self.member)
        self.assertEqual(len(result["created"]), 1)
        task = result["created"][0]
        self.assertEqual(task.source_action_item, accepted)
        self.assertEqual(task.origin_key, f"meeting:{accepted.pk}")
        self.assertEqual(task.history[0]["action"], "imported")
        self.assertEqual(task.assignee, self.member)

    def test_import_retries_do_not_duplicate_or_overwrite_tasks(self):
        draft, accepted = self.approved_draft()
        first = import_action_items(self.officer, draft)["created"][0]
        update_task(self.officer, first, {"status": TaskStatus.IN_PROGRESS, "title": "Officer edit"}, 0)
        second = import_action_items(self.officer, draft)
        self.assertEqual(second["created"], [])
        self.assertEqual([task.pk for task in second["existing"]], [first.pk])
        first.refresh_from_db()
        self.assertEqual(first.title, "Officer edit")
        self.assertEqual(first.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(len(first.history), 2)
        self.assertEqual(Task.objects.count(), 1)

    def test_import_preserves_full_description_while_limiting_title(self):
        draft, item = self.approved_draft()
        item.description = "A" * 450
        item.save()
        task = import_action_items(self.officer, draft)["created"][0]
        self.assertEqual(len(task.title), 200)
        self.assertEqual(task.description, "A" * 450)

    def test_import_resumes_after_partial_batch_and_source_deletion_preserves_task(self):
        draft, first_item = self.approved_draft()
        second_item = ActionItem.objects.create(draft=draft, description="Second accepted item", position=2)
        import tasks.services as services
        original_create = services._create

        def fail_second(actor, fields, **kwargs):
            if kwargs.get("source_action_item").pk == second_item.pk:
                raise RuntimeError("Simulated interrupted batch")
            return original_create(actor, fields, **kwargs)

        with patch("tasks.services._create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                import_action_items(self.officer, draft)
        self.assertEqual(Task.objects.count(), 1)
        resumed = import_action_items(self.officer, draft)
        self.assertEqual(len(resumed["created"]), 1)
        self.assertEqual(len(resumed["existing"]), 1)
        first_task = resumed["existing"][0]
        source_key = first_task.origin_key
        first_item.delete()
        first_task.refresh_from_db()
        self.assertIsNone(first_task.source_action_item_id)
        self.assertEqual(first_task.origin_key, source_key)
        self.assertEqual(len(first_task.history), 1)

    def test_invalid_import_assignment_creates_nothing(self):
        draft, _ = self.approved_draft()
        with self.assertRaises(ValidationError):
            import_action_items(self.officer, draft, committee=self.committee, assignee=self.outsider)
        self.assertFalse(Task.objects.exists())

    def test_forms_validate_choices_and_require_an_edit_version(self):
        data = {
            "title": "Demonstration", "description": "Preparation", "committee": str(self.committee.pk),
            "assignee": str(self.member.pk), "priority": TaskPriority.MEDIUM, "status": TaskStatus.TODO,
            "due_date": "2026-11-01",
        }
        form = TaskForm(self.officer, data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["assignee"], self.member)
        task = self.task()
        edit = TaskForm(self.officer, data, instance=task)
        self.assertFalse(edit.is_valid())
        self.assertIn("version", edit.errors)
        wrong_member = TaskForm(self.officer, {**data, "assignee": str(self.outsider.pk)})
        self.assertFalse(wrong_member.is_valid())
        self.assertIn("assignee", wrong_member.errors)
        self.assertFalse(TaskStatusForm({"status": "bad", "version": 0}).is_valid())
        self.assertTrue(TaskStatusForm({"status": TaskStatus.DONE, "version": 0}).is_valid())

    def test_import_form_disallows_suspended_assignee_and_member_actor(self):
        data = {"committee": str(self.committee.pk), "assignee": str(self.member.pk), "priority": "high"}
        self.assertTrue(TaskImportForm(self.officer, data).is_valid())
        self.assertFalse(TaskImportForm(self.member, data).is_valid())
        Profile.objects.filter(user=self.member).update(is_suspended=True)
        self.assertFalse(TaskImportForm(self.officer, data).is_valid())
