"""Google trust-boundary tests; no real account or provider requests are made."""

import base64
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from google.auth.exceptions import TransportError

from .google_auth import (
    BoundedGoogleRequest,
    GoogleSignInError,
    MAX_NONCES,
    NONCE_SESSION_KEY,
    NONCE_TTL_SECONDS,
    VERIFY_TIMEOUT_SECONDS,
    verify_google_credential,
)
from .models import GoogleIdentity, Role, get_role
from .testing import make_user

User = get_user_model()
CLIENT_ID = "orgflow-test.apps.googleusercontent.com"


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleVerificationTests(SimpleTestCase):
    @patch("accounts.google_auth.id_token.verify_oauth2_token")
    def test_google_verifier_receives_configured_audience(self, verifier):
        verifier.return_value = {"sub": "subject"}
        self.assertEqual(verify_google_credential("signed-token"), verifier.return_value)
        args, kwargs = verifier.call_args
        self.assertEqual(args[0], "signed-token")
        self.assertIsInstance(args[1], BoundedGoogleRequest)
        self.assertEqual(kwargs, {"audience": CLIENT_ID})

    @patch("google.auth.transport.requests.Request.__call__", return_value="response")
    def test_verifier_transport_uses_bounded_timeout(self, transport):
        result = BoundedGoogleRequest()("https://example.test/certs", timeout=120)
        self.assertEqual(result, "response")
        self.assertEqual(transport.call_args.kwargs["timeout"], VERIFY_TIMEOUT_SECONDS)

    @patch("accounts.google_auth.id_token.verify_oauth2_token")
    def test_verifier_failures_become_safe_signin_errors(self, verifier):
        for error in (
            ValueError("invalid signature"),
            TypeError("invalid token shape"),
            KeyError("missing issuer"),
            TransportError("private transport details"),
        ):
            with self.subTest(error=type(error).__name__):
                verifier.side_effect = error
                with self.assertRaisesMessage(GoogleSignInError, "could not be verified"):
                    verify_google_credential("signed-token")

    @patch("google.oauth2.id_token._fetch_certs", return_value={})
    def test_malformed_jwt_header_is_rejected_by_real_google_decoder(self, certificates):
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

        for header in ({"alg": []}, {"alg": "RS256", "kid": ["invalid-key"]}):
            with self.subTest(header=header):
                credential = f"{encode(header)}.{encode({})}."
                with self.assertRaisesMessage(GoogleSignInError, "could not be verified"):
                    verify_google_credential(credential)

    @patch("accounts.google_auth.id_token.verify_oauth2_token")
    def test_missing_or_oversized_credentials_are_not_verified(self, verifier):
        for credential in ("", None, "x" * 16385):
            with self.subTest(credential_type=type(credential).__name__):
                with self.assertRaises(GoogleSignInError):
                    verify_google_credential(credential)
        verifier.assert_not_called()


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleSignInTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:google_signin")
        self.login_url = reverse("accounts:login")
        self.verification = patch("accounts.google_auth.verify_google_credential")
        self.verifier = self.verification.start()
        self.addCleanup(self.verification.stop)

    def nonce(self, client=None):
        response = (client or self.client).get(self.login_url)
        return response.context["google_nonce"]

    def claims(self, client=None, **overrides):
        claims = {
            "sub": "google-subject-123",
            "email": "ada@gmail.com",
            "email_verified": True,
            "nonce": self.nonce(client),
        }
        claims.update(overrides)
        return claims

    def signin(self, claims=None, client=None, **post):
        active_client = client or self.client
        self.verifier.return_value = claims if claims is not None else self.claims(active_client)
        return active_client.post(self.url, {"credential": "verified-by-mock", **post})

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_disabled_google_signin_hides_button_and_rejects_endpoint(self):
        self.assertNotContains(self.client.get(self.login_url), "g_id_onload")
        response = self.client.post(self.url, {"credential": "anything"})
        self.assertEqual(response.status_code, 503)
        self.verifier.assert_not_called()
        self.assertFalse(User.objects.exists())

    def test_google_login_uses_popup_compatible_opener_policy(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin-allow-popups")
        self.assertContains(response, "google_signin.js")

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_disabled_google_login_preserves_default_opener_policy(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin")

    def test_endpoint_is_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(User.objects.exists())

    def test_new_google_user_is_applicant_with_unusable_password(self):
        response = self.signin(self.claims(email="Ada@Gmail.com", role="admin", is_superuser=True))
        self.assertRedirects(response, reverse("core:dashboard"))
        identity = GoogleIdentity.objects.select_related("user").get()
        user = identity.user
        self.assertEqual(identity.subject, "google-subject-123")
        self.assertEqual(user.email, "ada@gmail.com")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(get_role(user), Role.APPLICANT)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_returning_google_subject_uses_same_user_when_email_changes(self):
        self.signin()
        original = GoogleIdentity.objects.get().user
        self.client.logout()
        self.signin(self.claims(email="changed@gmail.com"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(GoogleIdentity.objects.count(), 1)
        self.assertEqual(self.client.session["_auth_user_id"], str(original.pk))
        original.refresh_from_db()
        self.assertEqual(original.email, "ada@gmail.com")

    def test_google_signin_cannot_link_existing_local_email(self):
        local = make_user("ADA@gmail.com", Role.OFFICER)
        response = self.signin()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "not linked automatically", status_code=400)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(get_role(local), Role.OFFICER)

    def test_google_signin_cannot_take_over_legacy_email_username(self):
        User.objects.create_user(username="ada@gmail.com", email="different@example.com", password="secret")
        response = self.signin()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_second_google_subject_with_same_email_is_not_linked(self):
        self.signin()
        self.client.logout()
        response = self.signin(self.claims(sub="different-subject"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(GoogleIdentity.objects.count(), 1)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_linked_user_cannot_sign_in(self):
        self.signin()
        self.client.logout()
        User.objects.update(is_active=False)
        response = self.signin()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "inactive", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_email_is_rejected(self):
        for unverified in (False, "true", None):
            with self.subTest(email_verified=unverified):
                response = self.signin(self.claims(email_verified=unverified))
                self.assertEqual(response.status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_invalid_subject_or_email_is_rejected(self):
        for claim in ({"sub": ""}, {"sub": None}, {"email": "invalid"}, {"email": None}):
            with self.subTest(claim=claim):
                response = self.signin(self.claims(**claim))
                self.assertEqual(response.status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_invalid_token_does_not_create_account_or_reveal_details(self):
        self.nonce()
        self.verifier.side_effect = GoogleSignInError("Google sign-in could not be verified. Please try again.")
        response = self.client.post(self.url, {"credential": "bad-token"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, f'action="{self.login_url}"', status_code=400)
        self.assertFalse(User.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_or_wrong_nonce_is_rejected(self):
        for nonce in (None, "wrong", "non-ascii-\u00e9"):
            with self.subTest(nonce=nonce):
                response = self.signin(self.claims(nonce=nonce))
                self.assertEqual(response.status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_expired_nonce_is_rejected(self):
        with patch("accounts.google_auth.time.time", return_value=1000):
            claims = self.claims()
        with patch("accounts.google_auth.time.time", return_value=1000 + NONCE_TTL_SECONDS + 1):
            response = self.signin(claims)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_nonce_from_another_browser_session_is_rejected(self):
        claims = self.claims(Client())
        self.nonce()
        response = self.signin(claims)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_failed_account_attempt_consumes_nonce_to_prevent_replay(self):
        local = make_user("ada@gmail.com")
        claims = self.claims()
        self.assertEqual(self.signin(claims).status_code, 400)
        local.delete()
        response = self.signin(claims)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "expired", status_code=400)
        self.assertFalse(User.objects.exists())

    def test_nonce_storage_is_bounded_and_all_valid_tabs_can_complete(self):
        for _ in range(MAX_NONCES + 3):
            self.nonce()
        entries = self.client.session[NONCE_SESSION_KEY]
        self.assertEqual(len(entries), MAX_NONCES)
        response = self.signin({
            "sub": "google-subject-123",
            "email": "ada@gmail.com",
            "email_verified": True,
            "nonce": entries[0]["token"],
        })
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertNotIn(NONCE_SESSION_KEY, self.client.session)

    def test_failed_identity_creation_cleans_up_new_user(self):
        claims = self.claims()
        with patch("accounts.google_auth.GoogleIdentity.objects.create", side_effect=IntegrityError("duplicate")):
            response = self.signin(claims)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_failed_user_creation_is_a_safe_login_error(self):
        claims = self.claims()
        with patch.object(User.objects, "create_user", side_effect=IntegrityError("duplicate")):
            response = self.signin(claims)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_requires_django_csrf_protection(self):
        strict_client = Client(enforce_csrf_checks=True)
        claims = self.claims(strict_client)
        self.verifier.return_value = claims
        response = strict_client.post(self.url, {"credential": "token"})
        self.assertEqual(response.status_code, 403)
        self.verifier.assert_not_called()
        self.assertFalse(User.objects.exists())

    def test_csrf_protected_post_can_complete(self):
        strict_client = Client(enforce_csrf_checks=True)
        claims = self.claims(strict_client)
        self.verifier.return_value = claims
        response = strict_client.post(
            self.url,
            {"credential": "token", "csrfmiddlewaretoken": strict_client.cookies["csrftoken"].value},
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertIn("_auth_user_id", strict_client.session)

    def test_google_login_does_not_redirect_to_external_next(self):
        response = self.signin(next="https://attacker.example/steal")
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_google_login_preserves_safe_local_next(self):
        response = self.signin(next=reverse("accounts:profile"))
        self.assertRedirects(response, reverse("accounts:profile"))

    def test_logged_in_user_is_not_switched_to_another_google_account(self):
        user = make_user("local@example.com", Role.MEMBER)
        self.client.force_login(user)
        response = self.client.post(self.url, {"credential": "someone-else"})
        self.assertRedirects(response, reverse("core:dashboard"))
        self.verifier.assert_not_called()
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertFalse(GoogleIdentity.objects.exists())
