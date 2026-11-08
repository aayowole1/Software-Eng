"""A durable review decision survives partial account-access writes."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.testing import make_user

from .models import (
    ApplicationStatus, MembershipApplication, REJECTED_RETENTION,
    purge_old_rejected_applications,
)

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewRecoveryTests(TestCase):
    def setUp(self):
        self.officer = make_user("recovery-officer@example.com", Role.OFFICER)
        self.member = make_user("recovery-member@example.com", Role.MEMBER)
        self.applicant = make_user("recovery-applicant@example.com")
        self.applicant.is_active = False
        self.applicant.save(update_fields=["is_active"])
        self.application = MembershipApplication.objects.create(user=self.applicant, statement="Join robotics")
        self.client.force_login(self.officer)

    def review_url(self):
        return reverse("membership:review_application", args=[self.application.pk])

    def recovery_url(self):
        return reverse("membership:finish_review_access", args=[self.application.pk])

    def record_pending(self, status=ApplicationStatus.APPROVED):
        MembershipApplication.objects.filter(pk=self.application.pk).update(
            status=status, reviewed_by=self.officer, reviewed_at=timezone.now(),
            review_note="Original reviewer note", access_update_pending=True,
        )
        self.application.refresh_from_db()

    def metadata(self):
        self.application.refresh_from_db()
        return (self.application.status, self.application.reviewed_by_id, self.application.reviewed_at, self.application.review_note)

    def fail_activation(self):
        original = User.save

        def save(user, *args, **kwargs):
            if user.pk == self.applicant.pk and "is_active" in (kwargs.get("update_fields") or ()):
                raise DatabaseError("Injected activation failure")
            return original(user, *args, **kwargs)
        return patch.object(User, "save", autospec=True, side_effect=save)

    def fail_update(self, predicate):
        original = QuerySet.update

        def update(queryset, **values):
            if predicate(queryset, values):
                raise DatabaseError("Injected conditional-write failure")
            return original(queryset, **values)
        return patch.object(QuerySet, "update", autospec=True, side_effect=update)

    def test_activation_failure_keeps_review_intent_and_officer_retry_preserves_decision(self):
        with self.fail_activation():
            response = self.client.post(self.review_url(), {"decision": "approve", "note": "Welcome"})
        self.assertEqual(response.status_code, 302)
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("decision was recorded", notices)
        self.assertIn("access is still pending", notices)
        self.assertNotIn("approved.", notices)
        self.application.refresh_from_db()
        self.assertTrue(self.application.access_update_pending)
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.MEMBER)
        metadata = self.metadata()
        self.assertEqual(self.client.post(self.recovery_url(), {"decision": "reject", "note": "Replace it"}).status_code, 302)
        self.assertEqual(self.metadata(), metadata)
        self.assertFalse(self.application.access_update_pending)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

    def test_promotion_failure_records_decision_without_activating_account(self):
        with self.fail_update(lambda qs, values: qs.model is Profile and values.get("role") == Role.MEMBER):
            with self.assertRaises(DatabaseError):
                self.application.review(self.officer, True, "Welcome")
        self.application.refresh_from_db()
        self.assertTrue(self.application.access_update_pending)
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.APPLICANT)
        self.application.complete_access_update()
        self.assertFalse(self.application.access_update_pending)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.MEMBER)

    def test_final_stamp_failure_retains_flag_and_retry_does_not_repeat_activation(self):
        with self.fail_update(lambda qs, values: qs.model is MembershipApplication and values == {"access_update_pending": False}):
            with self.assertRaises(DatabaseError):
                self.application.review(self.officer, True, "Welcome")
        self.application.refresh_from_db()
        self.assertTrue(self.application.access_update_pending)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)
        metadata = self.metadata()
        with self.fail_activation():
            self.application.complete_access_update()
        self.assertFalse(self.application.access_update_pending)
        self.assertEqual(self.metadata(), metadata)

    def test_failed_decision_write_does_not_claim_decision_was_recorded(self):
        with self.fail_update(lambda qs, values: qs.model is MembershipApplication and "status" in values):
            response = self.client.post(self.review_url(), {"decision": "approve"})
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("Could not complete", notices)
        self.assertNotIn("decision was recorded", notices)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.PENDING)
        self.assertFalse(self.application.access_update_pending)
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)

    def test_recovery_view_handles_repeated_database_failure_truthfully(self):
        self.record_pending()
        metadata = self.metadata()
        with self.fail_activation():
            response = self.client.post(self.recovery_url())
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("access is still pending", notices)
        self.assertEqual(self.metadata(), metadata)
        self.assertTrue(self.application.access_update_pending)

    def test_rejected_recovery_activates_applicant_without_changing_role_or_reason(self):
        self.record_pending(ApplicationStatus.REJECTED)
        metadata = self.metadata()
        self.application.complete_access_update()
        self.assertEqual(self.metadata(), metadata)
        self.assertFalse(self.application.access_update_pending)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.APPLICANT)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

    def test_suspended_account_is_not_reactivated_and_intent_remains(self):
        self.record_pending()
        profile = Profile.objects.get(user=self.applicant)
        profile.is_suspended = True
        profile.save(update_fields=["is_suspended"])
        self.assertEqual(self.client.post(self.recovery_url()).status_code, 302)
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)
        self.application.refresh_from_db()
        self.assertTrue(self.application.access_update_pending)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.APPLICANT)

    def test_completed_or_legacy_review_cannot_be_reactivated_or_reversed(self):
        self.record_pending(ApplicationStatus.REJECTED)
        MembershipApplication.objects.filter(pk=self.application.pk).update(access_update_pending=False)
        metadata = self.metadata()
        self.client.post(self.recovery_url(), {"decision": "approve", "note": "Change decision"})
        self.assertEqual(self.metadata(), metadata)
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)
        with self.assertRaises(ValueError):
            self.application.review(self.officer, True)

    def test_stale_instance_cannot_replace_first_review_decision(self):
        stale = MembershipApplication.objects.get(pk=self.application.pk)
        self.application.review(self.officer, False, "No capacity")
        metadata = self.metadata()
        with self.assertRaises(ValueError):
            stale.review(self.officer, True, "Overwrite")
        self.assertEqual(self.metadata(), metadata)

    def test_interleaving_review_uses_pending_compare_and_set(self):
        original = QuerySet.update

        def update(queryset, **values):
            if queryset.model is MembershipApplication and "status" in values:
                original(MembershipApplication.objects.filter(pk=self.application.pk), status=ApplicationStatus.REJECTED, reviewed_by=self.officer, reviewed_at=timezone.now(), review_note="Competing decision", access_update_pending=False)
            return original(queryset, **values)

        with patch.object(QuerySet, "update", autospec=True, side_effect=update):
            with self.assertRaises(ValueError):
                self.application.review(self.officer, True, "Losing decision")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
        self.assertEqual(self.application.review_note, "Competing decision")
        self.assertFalse(self.application.access_update_pending)

    def test_recovery_is_post_only_officer_only_and_csrf_protected(self):
        self.record_pending()
        url = self.recovery_url()
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(url).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.application.refresh_from_db()
        self.assertTrue(self.application.access_update_pending)

    def test_reviewed_list_shows_recovery_only_for_flagged_records(self):
        self.record_pending()
        response = self.client.get(reverse("membership:application_list"))
        self.assertContains(response, self.recovery_url())
        self.assertContains(response, "Finish account access")
        self.application.complete_access_update()
        response = self.client.get(reverse("membership:application_list"))
        self.assertNotContains(response, self.recovery_url())

    def test_retention_does_not_purge_unfinished_rejected_review(self):
        self.record_pending(ApplicationStatus.REJECTED)
        MembershipApplication.objects.filter(pk=self.application.pk).update(reviewed_at=timezone.now() - REJECTED_RETENTION - timedelta(days=1))
        self.assertEqual(purge_old_rejected_applications(), 0)
        self.assertTrue(MembershipApplication.objects.filter(pk=self.application.pk).exists())
        self.application.complete_access_update()
        self.assertEqual(purge_old_rejected_applications(), 1)

    def test_existing_officer_role_is_retained_on_approval(self):
        profile = Profile.objects.get(user=self.applicant)
        profile.role = Role.OFFICER
        profile.save(update_fields=["role"])
        self.application.review(self.officer, True)
        self.assertEqual(Profile.objects.get(user=self.applicant).role, Role.OFFICER)
        self.assertFalse(self.application.access_update_pending)
