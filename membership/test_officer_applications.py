from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile, Role, set_role
from officer_applications.models import OfficerApplication

from .models import ApplicationStatus, MembershipApplication


class OfficerApplicationTests(TestCase):
    def setUp(self):
        self.member = self.make_user("member", Role.MEMBER)
        self.officer = self.make_user("officer", Role.OFFICER)
        self.admin = self.make_user("admin", Role.ADMIN)
        self.apply_url = reverse("membership:apply_for_officer")
        self.queue_url = reverse("membership:application_list")

    @staticmethod
    def make_user(username, role):
        user = get_user_model().objects.create_user(username, email=f"{username}@example.com")
        Profile.objects.filter(user=user).update(role=role)
        return user

    def application(self):
        return OfficerApplication.objects.create(user=self.member, statement="I can lead outreach.")

    def review_url(self, application):
        return reverse("membership:review_officer_application", args=[application.pk])

    def test_member_can_apply_once_and_database_blocks_duplicate_pending(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("core:dashboard")), self.apply_url)
        self.assertContains(self.client.post(self.apply_url, {"statement": ""}), "This field is required.")
        data = {"statement": "I can lead outreach.", "user": self.officer.pk}
        for _ in range(2):
            self.assertRedirects(self.client.post(self.apply_url, data), self.apply_url)
        application = OfficerApplication.objects.get()
        self.assertEqual(application.user_id, self.member.pk)
        self.assertEqual(application.statement, data["statement"])
        with self.assertRaises(IntegrityError):
            self.application()

    def test_officers_and_admins_cannot_apply(self):
        for user in (self.officer, self.admin):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.post(self.apply_url, {"statement": "Test"}).status_code, 403)
        self.assertFalse(OfficerApplication.objects.exists())

    def test_queue_combines_application_types_and_officer_cannot_approve(self):
        application = self.application()
        MembershipApplication.objects.create(user=self.member, statement="I want to join.")
        self.client.force_login(self.officer)
        response = self.client.get(self.queue_url)
        self.assertContains(response, application.statement)
        self.assertContains(response, "I want to join.")
        self.assertNotContains(response, self.review_url(application))
        self.assertEqual(self.client.post(self.review_url(application), {"decision": "approve"}).status_code, 403)
        response = self.client.get(self.queue_url, {"type": "officer", "q": "member@example"})
        self.assertEqual(response.context["pending"], [application])
        response = self.client.get(self.queue_url, {"type": "member"})
        self.assertNotContains(response, application.statement)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)

    def test_admin_approval_changes_role_and_records_audit(self):
        application = self.application()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.queue_url), self.review_url(application))
        for _ in range(2):
            self.assertRedirects(
                self.client.post(self.review_url(application), {"decision": "approve"}),
                self.queue_url,
            )
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.APPROVED)
        self.assertEqual(application.reviewed_by_id, self.admin.pk)
        profile = Profile.objects.get(user=self.member)
        self.assertEqual(profile.role, Role.OFFICER)
        self.assertEqual(len(profile.role_history), 1)
        entry = profile.role_history[0]
        self.assertEqual(entry["source"], f"officer_application:{application.pk}")
        self.assertEqual(entry["actor_id"], str(self.admin.pk))
        self.assertEqual(entry["old_role"], Role.MEMBER)
        self.assertEqual(entry["new_role"], Role.OFFICER)
        self.assertContains(self.client.get(reverse("accounts:user_list")), entry["source"])

    def test_rejection_requires_reason_and_member_can_see_it_and_reapply(self):
        application = self.application()
        url = self.review_url(application)
        self.client.force_login(self.admin)
        self.client.post(url, {"decision": "reject", "note": " "})
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.client.post(url, {"decision": "reject", "note": "Please finish your term first."})
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.REJECTED)
        self.assertEqual(Profile.objects.get(user=self.member).role, Role.MEMBER)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(self.apply_url), application.review_note)
        self.assertRedirects(self.client.post(self.apply_url, {"statement": "My term is complete."}), self.apply_url)
        self.assertEqual(OfficerApplication.objects.filter(user=self.member).count(), 2)

    def test_retry_finishes_approval_after_role_write_acknowledgement_is_lost(self):
        application = self.application()
        self.client.force_login(self.admin)
        url = self.review_url(application)

        def write_then_fail(*args, **kwargs):
            set_role(*args, **kwargs)
            raise DatabaseError("Lost acknowledgement")

        with patch("officer_applications.models.set_role", side_effect=write_then_fail):
            self.client.post(url, {"decision": "approve"})
        application.refresh_from_db()
        self.assertTrue(application.approval_in_progress)
        self.assertContains(self.client.get(self.queue_url), "Finish approval")
        self.client.post(url, {"decision": "approve"})
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.APPROVED)
        self.assertFalse(application.approval_in_progress)
        self.assertEqual(len(Profile.objects.get(user=self.member).role_history), 1)

    def test_pending_approval_does_not_overwrite_a_newer_admin_assignment(self):
        application = self.application()
        self.client.force_login(self.admin)
        url = self.review_url(application)
        with patch("officer_applications.models.set_role", side_effect=DatabaseError("Write failed")):
            self.client.post(url, {"decision": "approve"})
        set_role(self.member, Role.ADMIN, actor=self.admin)
        self.client.post(url, {"decision": "approve"})
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.assertFalse(application.approval_in_progress)
        self.assertEqual(Profile.objects.get(user=self.member).role, Role.ADMIN)
