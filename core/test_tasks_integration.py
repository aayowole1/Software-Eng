"""Task acceptance across accounts, committees, dashboard and meeting review."""

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from meetings.models import ActionItem, DraftStatus, MeetingDraft
from membership.models import MembershipApplication
from tasks.models import Task, TaskStatus
from tasks.services import create_task


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskIntegrationTests(TestCase):
    def setUp(self):
        self.officer = make_user("integration-officer@example.com", Role.OFFICER)
        self.admin = make_user("integration-admin@example.com", Role.ADMIN)
        self.member = make_user("integration-member@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Outreach", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)

    def test_dashboard_counts_only_my_accessible_assignments(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        create_task(self.officer, title="Assigned poster", committee=self.committee,
                    assignee=self.member, due_date=yesterday)
        create_task(self.officer, title="Completed poster", committee=self.committee,
                    assignee=self.member, due_date=yesterday, status=TaskStatus.DONE)
        create_task(self.officer, title="Committee queue", committee=self.committee)
        create_task(self.officer, title="Officer private task", assignee=self.officer)
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["my_task_counts"], {"total": 2, "completed": 1, "overdue": 1})
        self.assertContains(response, "Assigned poster")
        self.assertNotContains(response, "Officer private task")
        self.assertNotContains(response, "Completed poster")
        self.assertContains(response, reverse("tasks:list"))
        self.assertNotContains(response, reverse("meetings:create"))

    def test_public_and_applicant_dashboards_hide_tasks(self):
        create_task(self.officer, title="Internal follow-up", committee=self.committee)
        for user in (None, make_user("integration-applicant@example.com")):
            if user:
                self.client.force_login(user)
            response = self.client.get(reverse("core:dashboard"))
            self.assertNotContains(response, "Internal follow-up")
            self.assertNotContains(response, reverse("tasks:list"))
            self.assertNotContains(response, reverse("meetings:create"))

    def test_committee_task_summary_requires_membership_or_officer_role(self):
        create_task(self.officer, title="Committee work", committee=self.committee)
        self.client.force_login(self.member)
        response = self.client.get(reverse("committees:detail", args=[self.committee.pk]))
        self.assertContains(response, "1 total")
        self.assertContains(response, f"{reverse('tasks:list')}?committee={self.committee.pk}")
        outsider = make_user("integration-outsider@example.com", Role.MEMBER)
        self.client.force_login(outsider)
        response = self.client.get(reverse("committees:detail", args=[self.committee.pk]))
        self.assertNotContains(response, "Committee tasks")

    def test_deleting_committee_with_tasks_keeps_roster_and_history(self):
        task = create_task(self.officer, title="Keep audit", committee=self.committee)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("committees:delete", args=[self.committee.pk]), follow=True)
        self.assertContains(response, "Move this committee&#x27;s tasks")
        self.assertTrue(Committee.objects.filter(pk=self.committee.pk).exists())
        self.assertTrue(CommitteeMember.objects.filter(committee=self.committee, user=self.member).exists())
        self.assertEqual(Task.objects.get(pk=task.pk).history, task.history)

    def test_committee_without_tasks_still_deletes_with_roster(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("committees:delete", args=[self.committee.pk]))
        self.assertRedirects(response, reverse("committees:list"))
        self.assertFalse(Committee.objects.filter(pk=self.committee.pk).exists())
        self.assertFalse(CommitteeMember.objects.filter(committee_id=self.committee.pk).exists())

    def test_only_approved_meeting_shows_conversion_link(self):
        draft = MeetingDraft.objects.create(title="Reviewed planning", notes="Private notes", created_by=self.officer)
        self.client.force_login(self.officer)
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("meetings:create"))
        link = reverse("tasks:import_draft", args=[draft.pk])
        self.assertNotContains(self.client.get(reverse("meetings:detail", args=[draft.pk])), link)
        draft.review(self.officer, DraftStatus.APPROVED)
        self.assertContains(self.client.get(reverse("meetings:detail", args=[draft.pk])), link)

    def test_approved_member_can_receive_and_complete_a_task_then_import_reviewed_actions(self):
        applicant = make_user("integration-new-member@example.com")
        applicant.is_active = False
        applicant.save(update_fields=["is_active"])
        application = MembershipApplication.objects.create(user=applicant, statement="Volunteer for outreach")
        self.client.force_login(self.officer)
        response = self.client.post(reverse("membership:review_application", args=[application.pk]),
                                    {"decision": "approve", "note": "Welcome"})
        self.assertEqual(response.status_code, 302)
        applicant.refresh_from_db()
        self.assertTrue(applicant.is_active)
        self.assertEqual(applicant.profile.role, Role.MEMBER)
        response = self.client.post(reverse("committees:add_member", args=[self.committee.pk]),
                                    {"user": str(applicant.pk), "role": "member"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CommitteeMember.objects.filter(committee=self.committee, user=applicant).exists())
        response = self.client.post(reverse("tasks:create"), {
            "title": "Welcome event", "description": "Prepare the room",
            "committee": str(self.committee.pk), "assignee": str(applicant.pk),
            "priority": "high", "status": "todo", "due_date": "2026-11-01",
        })
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Welcome event")
        member_client = Client()
        member_client.force_login(applicant)
        self.assertContains(member_client.get(reverse("tasks:list")), "Welcome event")
        response = member_client.post(reverse("tasks:update_status", args=[task.pk]),
                                      {"status": "done", "version": task.version})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(member_client.get(reverse("core:dashboard")).context["my_task_counts"]["completed"], 1)
        task.refresh_from_db()
        self.assertEqual(task.history[-1]["actor_id"], str(applicant.pk))

        draft = MeetingDraft.objects.create(title="Outreach follow-up", notes="Private officer notes", created_by=self.officer)
        ActionItem.objects.create(draft=draft, description="Send the invitation", accepted=True)
        ActionItem.objects.create(draft=draft, description="Discarded proposal", accepted=False)
        draft.review(self.officer, DraftStatus.APPROVED)
        response = self.client.post(reverse("tasks:import_draft", args=[draft.pk]), {
            "committee": str(self.committee.pk), "assignee": str(applicant.pk),
            "priority": "medium", "due_date": "2026-11-01",
        })
        self.assertEqual(response.status_code, 302)
        listing = member_client.get(reverse("tasks:list"))
        self.assertContains(listing, "Send the invitation")
        self.assertNotContains(listing, "Discarded proposal")
        self.assertNotContains(listing, "Private officer notes")
