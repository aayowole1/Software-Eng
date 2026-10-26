"""Password signup compensates failures across user, profile and application."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse

from membership.models import MembershipApplication

from .models import Profile, Role
from .testing import PASSWORD, make_user

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PasswordSignupRecoveryTests(TestCase):
    payload = {
        "username": "newlocal", "email": "newlocal@example.com",
        "password": "Strong-local-password!2026", "confirm_password": "Strong-local-password!2026",
        "statement": "I would like to help organize student events.",
    }

    def submit(self):
        return self.client.post(reverse("accounts:register"), dict(self.payload))

    def assert_retry_form(self, response):
        self.assertContains(response, "Please try submitting it again.", status_code=503)
        for field in ("username", "email", "statement"):
            self.assertEqual(response.context["form"][field].value(), self.payload[field])
        self.assertNotContains(response, self.payload["password"], status_code=503)
        self.assertNotContains(response, "private details", status_code=503)
        self.assertNotIn("_auth_user_id", self.client.session)

    def assert_successful_retry(self):
        self.assertRedirects(self.submit(), reverse("core:home"))
        user = User.objects.get(username=self.payload["username"])
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertEqual(Profile.objects.get(user=user).role, Role.APPLICANT)
        self.assertEqual(MembershipApplication.objects.get(user=user).statement, self.payload["statement"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_normal_password_signup_creates_one_pending_inactive_applicant(self):
        self.assert_successful_retry()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Profile.objects.count(), 1)
        self.assertEqual(MembershipApplication.objects.count(), 1)

    def test_user_creation_database_failure_preserves_input_and_can_retry(self):
        with patch.object(User.objects, "create_user", side_effect=OperationalError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_user_integrity_failure_does_not_remove_an_existing_account(self):
        existing = make_user("existing@example.com", Role.MEMBER)
        with patch.object(User.objects, "create_user", side_effect=IntegrityError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertEqual(list(User.objects.values_list("pk", flat=True)), [existing.pk])
        self.assertTrue(User.objects.get(pk=existing.pk).check_password(PASSWORD))
        self.assert_successful_retry()

    def test_profile_signal_database_failure_cleans_inserted_user_and_can_retry(self):
        with patch("accounts.signals.Profile.objects.get_or_create", side_effect=OperationalError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_profile_signal_integrity_failure_cleans_inserted_user_and_can_retry(self):
        with patch("accounts.signals.Profile.objects.get_or_create", side_effect=IntegrityError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_application_database_failure_cleans_user_and_profile_and_can_retry(self):
        with patch("accounts.forms.MembershipApplication.objects.create", side_effect=OperationalError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_application_integrity_failure_cleans_user_and_profile_and_can_retry(self):
        with patch("accounts.forms.MembershipApplication.objects.create", side_effect=IntegrityError("private details")):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_application_insert_then_failure_compensates_all_new_records_only(self):
        existing = make_user("existing@example.com", Role.MEMBER)
        original = MembershipApplication.objects.create

        def inserted_then_failed(**values):
            original(**values)
            raise OperationalError("private details")

        with patch("accounts.forms.MembershipApplication.objects.create", side_effect=inserted_then_failed):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertEqual(list(User.objects.values_list("pk", flat=True)), [existing.pk])
        self.assertEqual(list(Profile.objects.values_list("user_id", flat=True)), [existing.pk])
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()

    def test_cleanup_failure_logs_safe_operator_alert_and_never_signs_in(self):
        with (
            patch("accounts.signals.Profile.objects.get_or_create", side_effect=OperationalError("private details")),
            patch("django.db.models.query.QuerySet.delete", side_effect=OperationalError("private connection credentials")),
            self.assertLogs("accounts.forms", level="ERROR") as logs,
        ):
            response = self.submit()
        self.assert_retry_form(response)
        self.assertIn("operator recovery is required", logs.output[0])
        self.assertNotIn("private", " ".join(logs.output))
        self.assertFalse(User.objects.get().is_active)
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
