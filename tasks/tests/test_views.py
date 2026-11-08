"""HTTP acceptance checks for task permissions, forms and reviewed AI actions."""

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from meetings.models import ActionItem, DraftStatus, MeetingDraft

from tasks.models import Task, TaskPriority, TaskStatus
from tasks.services import create_task


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskViewTests(TestCase):
    def setUp(self):
        self.officer = make_user("task-officer@example.com", Role.OFFICER)
        self.member = make_user("task-member@example.com", Role.MEMBER)
        self.colleague = make_user("task-colleague@example.com", Role.MEMBER)
        self.outsider = make_user("task-outsider@example.com", Role.MEMBER)
        self.applicant = make_user("task-applicant@example.com")
        self.committee = Committee.objects.create(name="Events", created_by=self.officer)
        self.other_committee = Committee.objects.create(name="Finance", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        CommitteeMember.objects.create(committee=self.committee, user=self.colleague)
        CommitteeMember.objects.create(committee=self.other_committee, user=self.outsider)

    def task(self, title="Prepare agenda", **overrides):
        data = {"title": title, "committee": self.committee, "assignee": self.member}
        data.update(overrides)
        return create_task(self.officer, **data)

    def payload(self, task=None, **overrides):
        data = {
            "title": "Prepare agenda", "description": "Discuss next event",
            "committee": str(self.committee.pk), "assignee": str(self.member.pk),
            "due_date": "", "priority": TaskPriority.MEDIUM, "status": TaskStatus.TODO,
        }
        if task:
            data["version"] = str(task.version)
        data.update(overrides)
        return data

    def test_anonymous_redirect_and_applicant_denied(self):
        self.assertEqual(self.client.get(reverse("tasks:list")).status_code, 302)
        self.client.force_login(self.applicant)
        for name in ("list", "create"):
            self.assertEqual(self.client.get(reverse(f"tasks:{name}")).status_code, 403)
        self.assertEqual(Task.objects.count(), 0)

    def test_suspension_blocks_even_existing_session(self):
        self.client.force_login(self.member)
        profile = self.member.profile
        profile.is_suspended = True
        profile.save(update_fields=["is_suspended"])
        response = self.client.get(reverse("tasks:list"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('tasks:list')}", fetch_redirect_response=False)

    def test_officer_creates_delegated_task_and_member_cannot(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse("tasks:create"), self.payload()).status_code, 403)
        self.client.force_login(self.officer)
        response = self.client.post(reverse("tasks:create"), self.payload())
        task = Task.objects.get()
        self.assertRedirects(response, reverse("tasks:detail", args=[task.pk]))
        self.assertEqual(task.assignee_id, self.member.pk)
        self.assertEqual(task.created_by_id, self.officer.pk)

    def test_create_committee_link_and_invalid_initial(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("tasks:create"), {"committee": str(self.committee.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["committee"], self.committee)
        self.assertEqual(self.client.get(reverse("tasks:create"), {"committee": "bad-id"}).status_code, 404)

    def test_malformed_form_identifiers_are_errors_not_server_errors(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("tasks:create"), self.payload(committee="bad-id", assignee="bad-id"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Task.objects.exists())

    def test_member_counts_and_filters_never_include_other_committee(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        todo = self.task("Publicity poster", assignee=None, due_date=yesterday, priority=TaskPriority.HIGH)
        self.task("Agenda completed", status=TaskStatus.DONE, due_date=yesterday)
        self.task("Hidden budget", committee=self.other_committee, assignee=self.outsider, due_date=yesterday)
        self.client.force_login(self.member)
        response = self.client.get(reverse("tasks:list"))
        self.assertEqual(response.context["counts"], {"total": 2, "completed": 1, "overdue": 1})
        self.assertNotContains(response, "Hidden budget")
        response = self.client.get(reverse("tasks:list"), {"q": "poster", "committee": str(self.committee.pk), "priority": "high", "overdue": "1"})
        self.assertEqual([t.pk for t in response.context["page_obj"]], [todo.pk])
        response = self.client.get(reverse("tasks:list"), {"mine": "1", "status": TaskStatus.DONE})
        self.assertContains(response, "Agenda completed")
        self.assertNotContains(response, "Publicity poster")

    def test_invalid_filters_show_feedback(self):
        self.client.force_login(self.member)
        for filters in ({"committee": "bad-id"}, {"committee": str(self.other_committee.pk)}, {"status": "invented"}, {"priority": "urgent"}, {"mine": "invalid"}):
            response = self.client.get(reverse("tasks:list"), filters)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.context["filter_form"].errors)

    def test_unknown_malformed_and_cross_committee_task_are_404(self):
        task = self.task()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[task.pk])).status_code, 404)
        self.assertEqual(self.client.get("/tasks/not-an-id/").status_code, 404)
        self.assertEqual(self.client.get(reverse("tasks:detail", args=["0123456789abcdef01234567"])).status_code, 404)

    def test_removed_committee_member_loses_assigned_task_access(self):
        task = self.task()
        self.client.force_login(self.member)
        CommitteeMember.objects.filter(user=self.member, committee=self.committee).delete()
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[task.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("tasks:update_status", args=[task.pk]), {"status": TaskStatus.DONE, "version": task.version}).status_code, 404)

    def test_assignee_updates_status_but_cannot_edit_metadata(self):
        task = self.task()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("tasks:edit", args=[task.pk])).status_code, 403)
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {"status": TaskStatus.IN_PROGRESS, "version": task.version})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(task.history[-1]["actor_id"], str(self.member.pk))

    def test_unassigned_colleague_cannot_update_someone_elses_status(self):
        task = self.task()
        self.client.force_login(self.colleague)
        self.assertEqual(self.client.post(reverse("tasks:update_status", args=[task.pk]), {"status": TaskStatus.DONE, "version": task.version}).status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)

    def test_officer_edit_and_stale_form_preserve_newer_changes(self):
        task = self.task()
        version = task.version
        self.client.force_login(self.officer)
        response = self.client.post(reverse("tasks:edit", args=[task.pk]), self.payload(task, title="Reviewed agenda"))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("tasks:edit", args=[task.pk]), self.payload(task, title="Stale overwrite", version=version))
        self.assertContains(response, "changed while you were editing", status_code=409)
        task.refresh_from_db()
        self.assertEqual(task.title, "Reviewed agenda")

    def test_stale_status_is_409(self):
        task = self.task()
        version = task.version
        self.client.force_login(self.member)
        url = reverse("tasks:update_status", args=[task.pk])
        self.assertEqual(self.client.post(url, {"status": TaskStatus.IN_PROGRESS, "version": version}).status_code, 302)
        self.assertEqual(self.client.post(url, {"status": TaskStatus.DONE, "version": version}).status_code, 409)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.IN_PROGRESS)

    def test_claim_is_post_only_and_records_member_assignment(self):
        task = self.task(assignee=None)
        self.client.force_login(self.member)
        url = reverse("tasks:claim", args=[task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        task.refresh_from_db()
        self.assertIsNone(task.assignee_id)
        self.assertEqual(self.client.post(url, {"version": task.version}).status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.assignee_id, self.member.pk)

    def test_claim_without_version_and_stale_second_claim_cannot_overwrite(self):
        task = self.task(assignee=None)
        version = task.version
        self.client.force_login(self.member)
        url = reverse("tasks:claim", args=[task.pk])
        self.assertEqual(self.client.post(url).status_code, 400)
        self.assertEqual(self.client.post(url, {"version": version}).status_code, 302)
        self.client.force_login(self.colleague)
        self.assertEqual(self.client.post(url, {"version": version}).status_code, 409)
        task.refresh_from_db()
        self.assertEqual(task.assignee_id, self.member.pk)

    def test_csrf_protects_create_status_and_claim(self):
        task = self.task(assignee=None)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(reverse("tasks:create"), self.payload()).status_code, 403)
        strict.force_login(self.member)
        self.assertEqual(strict.post(reverse("tasks:claim", args=[task.pk]), {"version": task.version}).status_code, 403)
        assigned = self.task("Assigned task")
        self.assertEqual(strict.post(reverse("tasks:update_status", args=[assigned.pk]), {"status": TaskStatus.DONE, "version": assigned.version}).status_code, 403)

    def test_task_title_description_and_audit_are_escaped(self):
        task = self.task('<script>alert("title")</script>', description='<script>alert("body")</script>')
        self.client.force_login(self.member)
        response = self.client.get(reverse("tasks:detail", args=[task.pk]))
        self.assertContains(response, "&lt;script&gt;")
        # The shared sidebar includes trusted JavaScript; task content and its
        # audit copies must still never render the submitted markup verbatim.
        self.assertContains(response, "alert(&quot;title&quot;)")
        self.assertContains(response, "alert(&quot;body&quot;)")
        self.assertNotContains(response, task.title)
        self.assertNotContains(response, task.description)

    def draft(self, status=DraftStatus.APPROVED):
        draft = MeetingDraft.objects.create(title="Planning meeting", notes="Synthetic notes", status=status, created_by=self.officer)
        ActionItem.objects.create(draft=draft, description="Book a venue", accepted=True, position=0)
        ActionItem.objects.create(draft=draft, description="Invented action", accepted=False, position=1)
        return draft

    def test_import_get_is_read_only_and_post_is_accepted_only_idempotent(self):
        draft = self.draft()
        self.client.force_login(self.officer)
        url = reverse("tasks:import_draft", args=[draft.pk])
        self.assertContains(self.client.get(url), "Book a venue")
        self.assertFalse(Task.objects.exists())
        defaults = {"committee": str(self.committee.pk), "assignee": str(self.member.pk), "priority": TaskPriority.MEDIUM, "due_date": ""}
        self.assertEqual(self.client.post(url, defaults).status_code, 302)
        self.assertEqual(self.client.post(url, defaults).status_code, 302)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Task.objects.get().title, "Book a venue")

    def test_pending_draft_and_member_direct_import_are_denied(self):
        draft = self.draft(DraftStatus.PENDING_REVIEW)
        url = reverse("tasks:import_draft", args=[draft.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.force_login(self.officer)
        self.assertContains(self.client.get(url), "Approve this meeting", status_code=400)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_import_requires_csrf(self):
        draft = self.draft()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(reverse("tasks:import_draft", args=[draft.pk]), {}).status_code, 403)
        self.assertFalse(Task.objects.exists())

    def test_assignee_choices_follow_committee_and_exclude_suspended_users(self):
        profile = self.colleague.profile
        profile.is_suspended = True
        profile.save(update_fields=["is_suspended"])
        self.client.force_login(self.officer)
        response = self.client.get(reverse("tasks:assignees"), {"committee": str(self.committee.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"assignees": [{"id": str(self.member.pk), "label": self.member.email}]})
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(reverse("tasks:assignees"))
        ids = {member["id"] for member in response.json()["assignees"]}
        self.assertIn(str(self.member.pk), ids)
        self.assertIn(str(self.outsider.pk), ids)
        self.assertNotIn(str(self.colleague.pk), ids)
        self.assertNotIn(str(self.applicant.pk), ids)

    def test_assignee_endpoint_rejects_invalid_committee_and_unauthorized_requests(self):
        url = reverse("tasks:assignees")
        self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.member, self.applicant):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.officer)
        for committee in ("bad-id", "0123456789abcdef01234567"):
            self.assertEqual(self.client.get(url, {"committee": committee}).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 405)
        profile = self.officer.profile
        profile.is_suspended = True
        profile.save(update_fields=["is_suspended"])
        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)

    def test_assignment_forms_load_shared_refresh_script(self):
        self.client.force_login(self.officer)
        for url in (reverse("tasks:create"), reverse("tasks:import_draft", args=[self.draft().pk])):
            response = self.client.get(url)
            self.assertContains(response, 'data-assignees-url="' + reverse("tasks:assignees") + '"')
            self.assertContains(response, "tasks/assignment.js")
            self.assertContains(response, 'aria-live="polite"')
