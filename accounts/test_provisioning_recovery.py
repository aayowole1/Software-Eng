"""Failure recovery and fail-closed access checks against the real database."""

import time
from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse

from membership.models import ApplicationStatus, MembershipApplication

from .backends import EmailOrUsernameBackend
from .google_auth import PENDING_SIGNUP_SESSION_KEY
from .models import GoogleIdentity, Profile, Role
from .testing import PASSWORD, make_user

User = get_user_model()
CLIENT_ID = "recovery-tests.apps.googleusercontent.com"


@override_settings(
    GOOGLE_CLIENT_ID=CLIENT_ID,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class GoogleSignupRecoveryTests(TestCase):
    statement = "I would like to help organize student events."

    def setUp(self):
        session = self.client.session
        session[PENDING_SIGNUP_SESSION_KEY] = {
            "subject": "recovery-subject", "email": "new@example.com", "issued": time.time(),
        }
        session.save()

    def apply(self):
        return self.client.post(reverse("accounts:google_apply"), {"statement": self.statement})

    def assert_retry_form(self, response):
        self.assertContains(response, "Please try submitting it again.", status_code=503)
        self.assertEqual(response.context["form"]["statement"].value(), self.statement)
        self.assertIn(PENDING_SIGNUP_SESSION_KEY, self.client.session)
        self.assertNotIn("_auth_user_id", self.client.session)

    def assert_successful_retry(self):
        self.assertRedirects(self.apply(), reverse("core:home"))
        user = GoogleIdentity.objects.select_related("user").get(subject="recovery-subject").user
        self.assertFalse(user.is_active)
        self.assertEqual(MembershipApplication.objects.get(user=user).statement, self.statement)
        self.assertNotIn(PENDING_SIGNUP_SESSION_KEY, self.client.session)

    def test_identity_database_failure_cleans_only_new_attempt_and_can_retry(self):
        existing = make_user("existing@example.com", Role.MEMBER)
        with patch("accounts.google_auth.GoogleIdentity.objects.create", side_effect=OperationalError("private details")):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertNotContains(response, "private details", status_code=503)
        self.assertEqual(list(User.objects.values_list("pk", flat=True)), [existing.pk])
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assert_successful_retry()
        self.assertTrue(User.objects.get(pk=existing.pk).check_password(PASSWORD))

    def test_application_database_failure_preserves_statement_and_can_retry(self):
        with patch("accounts.google_auth.MembershipApplication.objects.create", side_effect=OperationalError("private details")):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assert_successful_retry()

    def test_user_creation_database_failure_preserves_signup_and_can_retry(self):
        with patch.object(User.objects, "create_user", side_effect=OperationalError("private details")):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assert_successful_retry()

    def test_profile_signal_database_failure_removes_already_inserted_user(self):
        with patch("accounts.signals.Profile.objects.get_or_create", side_effect=OperationalError("private details")):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assert_successful_retry()

    def test_profile_signal_integrity_failure_removes_already_inserted_user(self):
        with patch("accounts.signals.Profile.objects.get_or_create", side_effect=IntegrityError("duplicate profile")):
            response = self.apply()
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertFalse(User.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())

    def test_precheck_database_failure_preserves_signup_without_creating_user(self):
        with patch("accounts.google_auth._ensure_email_unused", side_effect=OperationalError("private details")):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertFalse(User.objects.exists())
        self.assert_successful_retry()

    def test_cleanup_failure_logs_safe_recovery_alert_and_does_not_sign_in(self):
        with (
            patch("accounts.google_auth.GoogleIdentity.objects.create", side_effect=OperationalError("private identity details")),
            patch("django.db.models.query.QuerySet.delete", side_effect=OperationalError("private connection credentials")),
            self.assertLogs("accounts.google_auth", level="ERROR") as logs,
        ):
            response = self.apply()
        self.assert_retry_form(response)
        self.assertIn("operator recovery is required", logs.output[0])
        self.assertNotIn("private", " ".join(logs.output))
        self.assertFalse(User.objects.get().is_active)
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())


@override_settings(
    GOOGLE_CLIENT_ID=CLIENT_ID,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AccountAccessRecoveryTests(TestCase):
    def setUp(self):
        self.user = make_user("member@example.com", Role.MEMBER)
        GoogleIdentity.objects.create(subject="existing-subject", user=self.user)

    def google_signin(self, client):
        page = client.get(reverse("accounts:login"))
        claims = {
            "sub": "existing-subject", "email": self.user.email,
            "email_verified": True, "nonce": page.context["google_nonce"],
        }
        with patch("accounts.google_auth.verify_google_credential", return_value=claims):
            return client.post(reverse("accounts:google_signin"), {"credential": "synthetic-token"})

    def test_password_and_backend_session_lookup_deny_suspension_until_reinstated(self):
        Profile.objects.filter(user=self.user).update(is_suspended=True)
        self.assertTrue(User.objects.get(pk=self.user.pk).is_active)
        self.assertIsNone(authenticate(username=self.user.username, password=PASSWORD))
        self.assertIsNone(EmailOrUsernameBackend().get_user(self.user.pk))
        Profile.objects.filter(user=self.user).update(is_suspended=False)
        self.assertEqual(authenticate(username=self.user.username, password=PASSWORD).pk, self.user.pk)
        self.assertEqual(EmailOrUsernameBackend().get_user(self.user.pk).pk, self.user.pk)

    def test_existing_session_loses_access_when_only_suspension_flag_is_written(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        Profile.objects.filter(user=self.user).update(is_suspended=True)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)
        Profile.objects.filter(user=self.user).update(is_suspended=False)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_google_suspension_is_denied_and_reinstatement_allows_valid_signin(self):
        Profile.objects.filter(user=self.user).update(is_suspended=True)
        response = self.google_signin(self.client)
        self.assertContains(response, "administratively suspended", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        Profile.objects.filter(user=self.user).update(is_suspended=False)
        self.assertRedirects(self.google_signin(self.client), reverse("core:dashboard"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_unfinished_membership_access_update_blocks_password_and_existing_session(self):
        self.client.force_login(self.user)
        application = MembershipApplication.objects.create(
            user=self.user, statement="Reviewed application", status=ApplicationStatus.APPROVED,
            access_update_pending=True,
        )
        self.assertIsNone(authenticate(username=self.user.username, password=PASSWORD))
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)
        application.access_update_pending = False
        application.save(update_fields=["access_update_pending"])
        self.assertEqual(authenticate(username=self.user.username, password=PASSWORD).pk, self.user.pk)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_unfinished_membership_access_update_blocks_google_until_completion(self):
        application = MembershipApplication.objects.create(
            user=self.user, statement="Reviewed application", status=ApplicationStatus.APPROVED,
            access_update_pending=True,
        )
        response = self.google_signin(self.client)
        self.assertContains(response, "membership review is still being applied", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        application.access_update_pending = False
        application.save(update_fields=["access_update_pending"])
        self.assertRedirects(self.google_signin(self.client), reverse("core:dashboard"))
