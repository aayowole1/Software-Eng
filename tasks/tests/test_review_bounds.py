"""Regression cases for task capacity, effective access and dangling assignments."""

from hashlib import sha256
from unittest.mock import patch

from bson import BSON
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile, Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from committees.views import AddMemberForm
from membership.models import ApplicationStatus, MembershipApplication
from tasks.forms import TaskForm
from tasks.models import Task, TaskStatus
from tasks.services import create_task, update_task
from tasks.views import task_access


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskReviewBoundsTests(TestCase):
    def setUp(self):
        self.officer = make_user("bounds-officer@example.com", Role.OFFICER)
        self.member = make_user("bounds-member@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Bounds", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)

    def payload(self, **overrides):
        data = {
            "title": "Task", "description": "", "committee": "", "assignee": "",
            "priority": "medium", "status": "todo", "due_date": "",
        }
        data.update(overrides)
        return data

    def test_over_limit_description_rejected_by_service_and_form(self):
        with self.assertRaises(ValidationError) as caught:
            create_task(self.officer, title="Too long", description="x" * 5001)
        self.assertIn("description", caught.exception.message_dict)
        form = TaskForm(self.officer, data=self.payload(description="x" * 5001))
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)
        self.assertFalse(Task.objects.exists())

    def test_limit_and_help_are_exposed_in_form(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("tasks:create"))
        self.assertContains(response, 'maxlength="5000"')
        self.assertContains(response, "Maximum 5,000 characters.")

    def test_long_current_description_retained_but_audit_is_compact(self):
        original = "original🙂" * 500
        task = create_task(self.officer, title="Full text", description=original)
        replacement = "updated🙂" * 625  # Exactly 5,000 Unicode characters.
        task = update_task(self.officer, task, {"description": replacement}, 0)
        task.refresh_from_db()
        self.assertEqual(task.description, replacement)
        old = task.history[-1]["changes"]["description"]["from"]
        new = task.history[-1]["changes"]["description"]["to"]
        for text, recorded in ((original, old), (replacement, new)):
            self.assertTrue(recorded["abbreviated"])
            self.assertEqual(recorded["length"], len(text))
            self.assertEqual(recorded["sha256"], sha256(text.encode("utf-8")).hexdigest())
            self.assertEqual(recorded["preview"], text[:160])
        self.assertLess(len(BSON.encode({"history": task.history})), 2500)
        self.client.force_login(self.officer)
        response = self.client.get(reverse("tasks:detail", args=[task.pk]))
        self.assertContains(response, replacement)
        self.assertContains(response, "Abbreviated: 5000 characters; SHA-256")

    def test_short_audit_values_remain_readable_and_escaped(self):
        task = create_task(self.officer, title="Short", description="<script>attack()</script>")
        self.assertEqual(task.history[0]["changes"]["description"]["to"], task.description)
        self.client.force_login(self.officer)
        response = self.client.get(reverse("tasks:detail", args=[task.pk]))
        self.assertNotContains(response, "<script>attack()</script>")
        self.assertContains(response, "&lt;script&gt;attack()&lt;/script&gt;")

    def test_history_capacity_rejects_before_state_version_or_history_write(self):
        task = create_task(self.officer, title="Capacity", description="Saved")
        history = task.history
        limit = len(BSON.encode({"history": history}))
        with patch("tasks.services.MAX_HISTORY_BSON_BYTES", limit):
            with self.assertRaisesMessage(ValidationError, "history has reached its storage limit"):
                update_task(self.officer, task, {"description": "Must not save"}, 0)
        task.refresh_from_db()
        self.assertEqual((task.version, task.description, task.history), (0, "Saved", history))

    def test_capacity_error_uses_safe_http_feedback(self):
        task = create_task(self.officer, title="Capacity")
        self.client.force_login(self.officer)
        with patch("tasks.services.MAX_HISTORY_BSON_BYTES", 1):
            response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {
                "status": TaskStatus.DONE, "version": 0,
            })
        self.assertContains(response, "This change was not saved", status_code=400)
        task.refresh_from_db()
        self.assertEqual((task.version, task.status), (0, TaskStatus.TODO))

    def test_capacity_checked_on_creation_without_inserting_task(self):
        with patch("tasks.services.MAX_HISTORY_BSON_BYTES", 1):
            with self.assertRaises(ValidationError):
                create_task(self.officer, title="Must not insert")
        self.assertFalse(Task.objects.exists())

    def test_noop_does_not_require_history_space_or_advance_version(self):
        task = create_task(self.officer, title="No change")
        history = task.history
        with patch("tasks.services.MAX_HISTORY_BSON_BYTES", 1):
            result = update_task(self.officer, task, {"status": TaskStatus.TODO}, 0)
        result.refresh_from_db()
        self.assertEqual((result.version, result.history), (0, history))

    def test_decorator_rechecks_pending_access_even_for_loaded_user(self):
        request = RequestFactory().get("/tasks/")
        request.user = self.officer
        protected = task_access(lambda request: HttpResponse("Allowed"))
        self.assertEqual(protected(request).status_code, 200)
        application = MembershipApplication.objects.create(
            user=self.officer, statement="Interrupted access change", status=ApplicationStatus.APPROVED,
            access_update_pending=True,
        )
        with self.assertRaises(PermissionDenied):
            protected(request)
        MembershipApplication.objects.filter(pk=application.pk).update(access_update_pending=False)
        self.assertEqual(protected(request).status_code, 200)

    def test_committee_add_choices_and_posts_exclude_unavailable_members(self):
        inactive = make_user("bounds-inactive@example.com", Role.MEMBER)
        inactive.__class__.objects.filter(pk=inactive.pk).update(is_active=False)
        suspended = make_user("bounds-suspended@example.com", Role.MEMBER)
        Profile.objects.filter(user=suspended).update(is_suspended=True)
        unfinished = make_user("bounds-unfinished@example.com", Role.MEMBER)
        MembershipApplication.objects.create(
            user=unfinished, statement="Interrupted access", status=ApplicationStatus.APPROVED,
            access_update_pending=True,
        )
        eligible = make_user("bounds-eligible@example.com", Role.MEMBER)
        offered = set(AddMemberForm(self.committee).fields["user"].queryset.values_list("pk", flat=True))
        self.assertIn(eligible.pk, offered)
        self.assertNotIn(self.member.pk, offered)
        self.client.force_login(self.officer)
        for unavailable in (inactive, suspended, unfinished):
            with self.subTest(user=unavailable.username):
                self.assertNotIn(unavailable.pk, offered)
                response = self.client.post(reverse("committees:add_member", args=[self.committee.pk]), {
                    "user": str(unavailable.pk), "role": "member",
                })
                self.assertEqual(response.status_code, 302)
                self.assertFalse(CommitteeMember.objects.filter(committee=self.committee, user=unavailable).exists())
        self.client.post(reverse("committees:add_member", args=[self.committee.pk]), {
            "user": str(eligible.pk), "role": "member",
        })
        self.assertTrue(CommitteeMember.objects.filter(committee=self.committee, user=eligible).exists())

    def test_dangling_committee_displays_and_reassignment_recovers_without_500(self):
        task = create_task(self.officer, title="Dangling", committee=self.committee, assignee=self.member)
        # Standalone MongoDB cannot enforce a relational FK across a deletion race.
        Committee.objects.filter(pk=self.committee.pk)._raw_delete(using="default")
        self.client.force_login(self.officer)
        self.assertContains(self.client.get(reverse("tasks:list")), "Missing committee")
        self.assertContains(self.client.get(reverse("tasks:detail", args=[task.pk])), "Missing committee")
        self.assertContains(self.client.get(reverse("tasks:edit", args=[task.pk])), "previous committee no longer exists")
        response = self.client.post(reverse("tasks:update_status", args=[task.pk]), {"status": "done", "version": 0})
        self.assertContains(response, "committee no longer exists", status_code=400)
        task.refresh_from_db()
        self.assertEqual((task.version, task.status), (0, TaskStatus.TODO))
        response = self.client.post(reverse("tasks:edit", args=[task.pk]), self.payload(
            title="Recovered", committee="", assignee=str(self.member.pk), version=0,
        ))
        self.assertRedirects(response, reverse("tasks:detail", args=[task.pk]))
        task.refresh_from_db()
        self.assertIsNone(task.committee_id)
        self.assertEqual(task.version, 1)

    def test_dangling_committee_does_not_expose_task_to_unrelated_member(self):
        task = create_task(self.officer, title="Still private", committee=self.committee, assignee=self.member)
        Committee.objects.filter(pk=self.committee.pk)._raw_delete(using="default")
        outsider = make_user("bounds-outsider@example.com", Role.MEMBER)
        self.client.force_login(outsider)
        self.assertNotContains(self.client.get(reverse("tasks:list")), task.title)
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[task.pk])).status_code, 404)
