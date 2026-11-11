"""Committee task management never promotes a Chair to organization officer."""

from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile, Role, get_role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember, CommitteeRole
from meetings.models import DraftStatus, MeetingDraft
from tasks.forms import TaskForm
from tasks.models import Task, TaskPriority, TaskStatus, can_manage_tasks
from tasks.services import TaskConflict, create_task, import_action_items, update_task


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChairTaskPermissionsTests(TestCase):
    def setUp(self):
        self.officer = make_user("chair-officer@example.com", Role.OFFICER)
        self.admin = make_user("chair-admin@example.com", Role.ADMIN)
        self.chair = make_user("chair@example.com", Role.MEMBER)
        self.member = make_user("chair-member@example.com", Role.MEMBER)
        self.outsider = make_user("chair-outsider@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Outreach", created_by=self.officer)
        self.other = Committee.objects.create(name="Finance", created_by=self.officer)
        self.chair_membership = CommitteeMember.objects.create(
            committee=self.committee, user=self.chair, role=CommitteeRole.CHAIR,
        )
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        # A Chair may also be an ordinary member elsewhere; visibility is not management.
        CommitteeMember.objects.create(committee=self.other, user=self.chair)
        CommitteeMember.objects.create(committee=self.other, user=self.outsider)

    def task(self, **overrides):
        fields = {"title": "Prepare agenda", "committee": self.committee, "assignee": self.member}
        fields.update(overrides)
        return create_task(self.officer, **fields)

    def payload(self, task=None, **overrides):
        fields = {
            "title": "Prepare agenda", "description": "Committee work",
            "committee": str(self.committee.pk), "assignee": str(self.member.pk),
            "due_date": "", "priority": TaskPriority.MEDIUM, "status": TaskStatus.TODO,
        }
        if task:
            fields["version"] = str(task.version)
        fields.update(overrides)
        return fields

    def test_chair_creates_and_delegates_own_committee_task_with_history(self):
        self.client.force_login(self.chair)
        response = self.client.post(reverse("tasks:create"), self.payload())
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get()
        self.assertEqual(task.committee_id, self.committee.pk)
        self.assertEqual(task.assignee_id, self.member.pk)
        self.assertEqual(task.created_by_id, self.chair.pk)
        self.assertEqual(task.history[0]["actor_id"], str(self.chair.pk))
        self.assertEqual(get_role(self.chair), Role.MEMBER)
        self.assertFalse(can_manage_tasks(self.chair))

    def test_chair_edit_reassign_status_and_history_are_scoped(self):
        task = self.task()
        self.client.force_login(self.chair)
        self.assertContains(self.client.get(reverse("tasks:detail", args=[task.pk])), "Edit task")
        response = self.client.post(
            reverse("tasks:edit", args=[task.pk]),
            self.payload(task, title="Reviewed agenda", assignee=str(self.chair.pk)),
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.title, "Reviewed agenda")
        self.assertEqual(task.assignee_id, self.chair.pk)
        self.assertEqual(task.history[-1]["actor_id"], str(self.chair.pk))
        self.assertEqual(self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": TaskStatus.IN_PROGRESS, "version": task.version,
        }).status_code, 302)

    def test_chair_form_and_assignee_endpoint_only_offer_managed_committee(self):
        self.client.force_login(self.chair)
        response = self.client.get(reverse("tasks:create"), {"committee": str(self.committee.pk)})
        form = response.context["form"]
        self.assertEqual(list(form.fields["committee"].queryset), [self.committee])
        self.assertTrue(form.fields["committee"].required)
        self.assertEqual(set(form.fields["assignee"].queryset), {self.chair, self.member})
        endpoint = reverse("tasks:assignees")
        response = self.client.get(endpoint, {"committee": str(self.committee.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.json()["assignees"]}, {
            str(self.chair.pk), str(self.member.pk),
        })
        self.assertEqual(self.client.get(endpoint, {"committee": str(self.other.pk)}).status_code, 404)
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.assertEqual(self.client.get(reverse("tasks:create"), {"committee": str(self.other.pk)}).status_code, 404)

    def test_chair_cannot_create_organization_or_other_committee_task(self):
        self.client.force_login(self.chair)
        for committee in ("", str(self.other.pk)):
            response = self.client.post(reverse("tasks:create"), self.payload(committee=committee, assignee=""))
            self.assertTrue(response.context["form"].errors)
        for committee in (None, self.other):
            with self.assertRaises(PermissionDenied):
                create_task(self.chair, title="Forbidden", committee=committee)
        self.assertFalse(Task.objects.exists())

    def test_chair_cannot_assign_outside_current_committee_roster(self):
        self.client.force_login(self.chair)
        response = self.client.post(reverse("tasks:create"), self.payload(assignee=str(self.outsider.pk)))
        self.assertIn("assignee", response.context["form"].errors)
        self.assertFalse(Task.objects.exists())

    def test_other_committee_membership_does_not_allow_management(self):
        task = self.task(committee=self.other, assignee=self.outsider)
        self.client.force_login(self.chair)
        self.assertNotContains(self.client.get(reverse("tasks:detail", args=[task.pk])), "Edit task")
        self.assertEqual(self.client.get(reverse("tasks:edit", args=[task.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": TaskStatus.DONE, "version": task.version,
        }).status_code, 403)
        with self.assertRaises(PermissionDenied):
            update_task(self.chair, task, {"title": "Cross-committee overwrite"}, task.version)
        task.refresh_from_db()
        self.assertEqual(task.title, "Prepare agenda")

    def test_move_requires_authority_over_source_and_destination(self):
        own = self.task(assignee=None)
        other = self.task(committee=self.other, assignee=None)
        for task, destination in ((own, self.other), (own, None), (other, self.committee)):
            with self.assertRaises(PermissionDenied):
                update_task(self.chair, task, {"committee": destination}, task.version)
            task.refresh_from_db()
            self.assertEqual(task.version, 0)
        CommitteeMember.objects.filter(user=self.chair, committee=self.other).update(role=CommitteeRole.CHAIR)
        updated = update_task(self.chair, own, {"committee": self.other}, own.version)
        self.assertEqual(updated.committee_id, self.other.pk)

    def test_form_cannot_move_task_from_unmanaged_source(self):
        task = self.task(committee=self.other, assignee=None)
        form = TaskForm(self.chair, self.payload(task, assignee=""), instance=task)
        self.assertFalse(form.is_valid())
        self.assertIn("You can no longer manage this task.", form.non_field_errors())

    def test_removal_or_demotion_after_get_blocks_post_and_stale_actor_service(self):
        task = self.task()
        self.client.force_login(self.chair)
        self.assertEqual(self.client.get(reverse("tasks:edit", args=[task.pk])).status_code, 200)
        self.chair_membership.role = CommitteeRole.MEMBER
        self.chair_membership.save(update_fields=["role"])
        self.assertEqual(self.client.post(reverse("tasks:edit", args=[task.pk]), self.payload(task)).status_code, 403)
        with self.assertRaises(PermissionDenied):
            create_task(self.chair, title="Stale role", committee=self.committee)
        self.chair_membership.delete()
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[task.pk])).status_code, 404)

    def test_suspension_and_inactive_account_block_stale_actor_writes(self):
        task = self.task()
        for field in ("is_suspended", "suspension_update_pending"):
            Profile.objects.filter(user=self.chair).update(**{field: True})
            with self.assertRaises(PermissionDenied):
                update_task(self.chair, task, {"title": "Stale account"}, task.version)
            Profile.objects.filter(user=self.chair).update(**{field: False})
        type(self.chair).objects.filter(pk=self.chair.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            create_task(self.chair, title="Inactive actor", committee=self.committee)

    def test_validation_time_membership_revocation_prevents_task_insert(self):
        original = Task.full_clean

        def revoke_after_validation(task, *args, **kwargs):
            result = original(task, *args, **kwargs)
            self.chair_membership.delete()
            return result

        with patch.object(Task, "full_clean", revoke_after_validation):
            with self.assertRaises(PermissionDenied):
                create_task(self.chair, title="Must not be created", committee=self.committee)
        self.assertFalse(Task.objects.exists())

    def test_validation_time_membership_revocation_prevents_task_update(self):
        task = self.task()
        original = Task.full_clean

        def revoke_after_validation(candidate, *args, **kwargs):
            result = original(candidate, *args, **kwargs)
            self.chair_membership.delete()
            return result

        with patch.object(Task, "full_clean", revoke_after_validation):
            with self.assertRaises(PermissionDenied):
                update_task(self.chair, task, {"title": "Must not replace"}, task.version)
        task.refresh_from_db()
        self.assertEqual(task.title, "Prepare agenda")
        self.assertEqual(task.version, 0)

    def test_stale_chair_edit_cannot_overwrite_newer_task(self):
        task = self.task()
        old_version = task.version
        update_task(self.officer, task, {"title": "Newer officer edit"}, old_version)
        with self.assertRaises(TaskConflict):
            update_task(self.chair, task, {"title": "Stale Chair edit"}, old_version)
        task.refresh_from_db()
        self.assertEqual(task.title, "Newer officer edit")

    def test_chair_task_links_do_not_expose_committee_management(self):
        self.client.force_login(self.chair)
        self.assertContains(self.client.get(reverse("tasks:list")), "New task")
        response = self.client.get(reverse("committees:detail", args=[self.committee.pk]))
        self.assertContains(response, "Create a task")
        self.assertNotContains(response, "Edit committee")
        self.assertEqual(self.client.get(reverse("committees:edit", args=[self.committee.pk])).status_code, 403)

    def test_chair_cannot_import_meeting_actions_or_open_meeting_review(self):
        draft = MeetingDraft.objects.create(
            title="Officer review", notes="Synthetic notes", status=DraftStatus.APPROVED,
            created_by=self.officer,
        )
        self.client.force_login(self.chair)
        for url in (reverse("tasks:import_draft", args=[draft.pk]), reverse("meetings:detail", args=[draft.pk])):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("tasks:import_draft", args=[draft.pk]), {}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            import_action_items(self.chair, draft, committee=self.committee)
        self.assertFalse(Task.objects.exists())

    def test_chair_mutations_still_require_csrf(self):
        task = self.task()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.chair)
        self.assertEqual(strict.post(reverse("tasks:create"), self.payload()).status_code, 403)
        self.assertEqual(strict.post(reverse("tasks:edit", args=[task.pk]), self.payload(task)).status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.version, 0)

    def test_members_keep_claim_and_own_progress_without_metadata_authority(self):
        task = self.task(assignee=None)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse("tasks:claim", args=[task.pk]), {"version": task.version}).status_code, 302)
        task.refresh_from_db()
        self.assertEqual(self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": TaskStatus.IN_PROGRESS, "version": task.version,
        }).status_code, 302)
        self.assertEqual(self.client.get(reverse("tasks:edit", args=[task.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("tasks:create"), self.payload()).status_code, 403)

    def test_officers_and_admins_keep_global_task_management(self):
        for actor in (self.officer, self.admin):
            task = create_task(actor, title="Organization task", assignee=self.outsider)
            updated = update_task(actor, task, {
                "committee": self.other, "title": "Finance task",
            }, task.version)
            self.assertEqual(updated.committee_id, self.other.pk)
