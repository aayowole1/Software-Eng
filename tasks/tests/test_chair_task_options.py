"""The proposed task choices compose with scoped Chair authority."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember, CommitteeRole
from tasks.models import Task, TaskPriority, TaskStatus


class ChairTaskOptionsIntegrationTests(TestCase):
    def setUp(self):
        self.chair = make_user("chair-options@example.invalid", Role.MEMBER)
        self.member = make_user("member-options@example.invalid", Role.MEMBER)
        self.committee = Committee.objects.create(name="Outreach options")
        self.other = Committee.objects.create(name="Finance options")
        CommitteeMember.objects.create(committee=self.committee, user=self.chair, role=CommitteeRole.CHAIR)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        self.client.force_login(self.chair)

    def payload(self, committee):
        return {"title": "Urgent committee review", "description": "Synthetic integration",
                "committee": str(committee.pk), "assignee": str(self.member.pk),
                "due_date": "", "priority": TaskPriority.URGENT,
                "status": TaskStatus.UNDER_REVIEW}

    def test_chair_creates_new_options_and_assignee_can_finish_without_approval(self):
        response = self.client.post(reverse("tasks:create"), self.payload(self.committee))
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get()
        self.assertEqual((task.priority, task.status), (TaskPriority.URGENT, TaskStatus.UNDER_REVIEW))
        self.assertEqual(task.history[0]["actor_id"], str(self.chair.pk))
        self.assertEqual(task.history[0]["changes"]["priority"]["to"], "urgent")
        self.assertContains(self.client.get(response["Location"]), "Under Review")
        self.client.force_login(self.member)
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
            "status": TaskStatus.DONE, "version": task.version,
        })
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DONE)
        self.assertEqual(task.history[-1]["changes"]["status"], {"from": "under_review", "to": "done"})

    def test_new_options_do_not_allow_cross_committee_chair_creation(self):
        response = self.client.post(reverse("tasks:create"), self.payload(self.other))
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Task.objects.exists())
