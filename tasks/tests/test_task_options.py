"""Urgent and Under Review use the existing task permissions and version checks."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember

from ..forms import TaskImportForm
from ..models import Task, TaskPriority, TaskStatus
from ..services import create_task, update_task


class TaskOptionsTests(TestCase):
    def setUp(self):
        self.officer = make_user("options-officer@example.com", Role.OFFICER)
        self.member = make_user("options-member@example.com", Role.MEMBER)
        self.other = make_user("options-other@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Options rehearsal")
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        CommitteeMember.objects.create(committee=self.committee, user=self.other)

    def make_task(self, **overrides):
        fields = {"title": "Prepare handoff", "committee": self.committee, "assignee": self.member}
        fields.update(overrides)
        return create_task(self.officer, **fields)

    def test_officer_creates_urgent_under_review_task_and_history_shows_labels(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("tasks:create"), {
            "title": "Urgent handoff", "description": "Check the fixtures.",
            "committee": str(self.committee.pk), "assignee": str(self.member.pk),
            "due_date": "", "priority": "urgent", "status": "under_review",
        })
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Urgent handoff")
        self.assertEqual((task.priority, task.status), ("urgent", "under_review"))
        self.assertEqual(task.history[0]["changes"]["priority"]["to"], "urgent")
        self.assertEqual(task.history[0]["changes"]["status"]["to"], "under_review")
        detail = self.client.get(response["Location"])
        self.assertContains(detail, "Urgent")
        self.assertContains(detail, "Under Review")

    def test_assignee_can_choose_under_review_then_done_without_extra_approval(self):
        task = self.make_task()
        self.client.force_login(self.member)
        for status in (TaskStatus.UNDER_REVIEW, TaskStatus.DONE):
            response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
                "status": status, "version": task.version,
            })
            self.assertEqual(response.status_code, 302)
            task.refresh_from_db()
            self.assertEqual(task.status, status)
        self.assertEqual(task.version, 2)
        self.assertEqual(len(task.history), 3)
        self.assertEqual(task.history[1]["changes"]["status"], {"from": "todo", "to": "under_review"})
        self.assertEqual(task.history[2]["changes"]["status"], {"from": "under_review", "to": "done"})

    def test_filters_select_urgent_under_review_records(self):
        matching = self.make_task(priority=TaskPriority.URGENT, status=TaskStatus.UNDER_REVIEW)
        self.make_task(title="Ordinary review", status=TaskStatus.UNDER_REVIEW)
        self.make_task(title="Urgent work", priority=TaskPriority.URGENT)
        self.client.force_login(self.member)
        response = self.client.get(reverse("tasks:list"), {"priority": "urgent", "status": "under_review"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([task.pk for task in response.context["page_obj"]], [matching.pk])
        self.assertContains(response, 'value="urgent" selected')
        self.assertContains(response, 'value="under_review" selected')

    def test_new_choices_do_not_allow_unrelated_member_to_change_status(self):
        task = self.make_task()
        self.client.force_login(self.other)
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": "under_review", "version": task.version,
        })
        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.version, 0)
        self.assertEqual(len(task.history), 1)

    def test_stale_status_form_preserves_under_review_and_its_history(self):
        task = self.make_task()
        update_task(self.member, task, {"status": TaskStatus.UNDER_REVIEW}, expected_version=0)
        self.client.force_login(self.member)
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": "done", "version": 0,
        })
        self.assertEqual(response.status_code, 409)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.UNDER_REVIEW)
        self.assertEqual(task.version, 1)
        self.assertEqual(len(task.history), 2)

    def test_invalid_status_is_rejected_without_a_task_write(self):
        task = self.make_task()
        self.client.force_login(self.member)
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": "needs_approval", "version": 0,
        })
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.version, 0)
        self.assertEqual(len(task.history), 1)

    def test_import_confirmation_accepts_urgent_priority(self):
        form = TaskImportForm(self.officer, {
            "committee": str(self.committee.pk), "assignee": str(self.member.pk),
            "due_date": "", "priority": "urgent",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["priority"], TaskPriority.URGENT)
