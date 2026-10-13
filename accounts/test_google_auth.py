"""Google trust-boundary tests; no real account or provider requests are made."""

import base64
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from google.auth.exceptions import TransportError

from membership.models import ApplicationStatus, MembershipApplication

from .google_auth import (
    BoundedGoogleRequest,
    GoogleSignInError,
    MAX_NONCES,
    NONCE_SESSION_KEY,
    NONCE_TTL_SECONDS,
    PENDING_SIGNUP_SESSION_KEY,
    PENDING_SIGNUP_TTL_SECONDS,
    VERIFY_TIMEOUT_SECONDS,
    _login_error,
    apply_google_login_headers,
    verify_google_credential,
)
from .models import GoogleIdentity, Role, get_role
from .testing import make_user
from .views import EmailLoginView

User = get_user_model()
CLIENT_ID = "orgflow-test.apps.googleusercontent.com"


@override_settings(
    GOOGLE_CLIENT_ID=CLIENT_ID,
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "app.example"],
)
class GoogleLoginHeaderTests(SimpleTestCase):
    def response_for(self, host, secure=False, referrer_policy="same-origin"):
        request = RequestFactory().get("/accounts/login/", HTTP_HOST=host, secure=secure)
        response = HttpResponse(headers={
            "Referrer-Policy": referrer_policy,
            "Cross-Origin-Opener-Policy": "same-origin",
        })
        return apply_google_login_headers(request, response)

    def test_http_localhost_uses_google_local_development_policy(self):
        response = self.response_for("localhost:8000")
        self.assertEqual(response["Referrer-Policy"], "no-referrer-when-downgrade")
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin-allow-popups")

    def test_http_loopback_address_uses_google_local_development_policy(self):
        response = self.response_for("127.0.0.1:8000")
        self.assertEqual(response["Referrer-Policy"], "no-referrer-when-downgrade")

    def test_https_localhost_retains_existing_referrer_policy(self):
        response = self.response_for("localhost:8000", secure=True)
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_remote_http_host_retains_existing_referrer_policy(self):
        response = self.response_for("app.example:8000")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_production_https_retains_custom_referrer_policy(self):
        response = self.response_for(
            "app.example", secure=True, referrer_policy="strict-origin-when-cross-origin"
        )
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_disabled_google_signin_preserves_both_policies(self):
        response = self.response_for("localhost:8000")
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin")

    def test_normal_login_response_applies_local_policy(self):
        request = RequestFactory().get("/accounts/login/", HTTP_HOST="localhost:8000")
        view = EmailLoginView()
        view.setup(request)
        response = view.render_to_response({"google_enabled": True})
        self.assertEqual(response["Referrer-Policy"], "no-referrer-when-downgrade")

    def test_google_failure_login_response_applies_local_policy(self):
        request = RequestFactory().post("/accounts/google/", HTTP_HOST="localhost:8000")
        with (
            patch("accounts.google_auth.messages.error"),
            patch("accounts.google_auth.google_login_context", return_value={"google_enabled": True}),
            patch("accounts.google_auth.render", return_value=HttpResponse(status=400)),
        ):
            response = _login_error(request, "Sign-in could not be verified.")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Referrer-Policy"], "no-referrer-when-downgrade")


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

    def apply(self, statement="I'd like to help with events.", client=None):
        return (client or self.client).post(reverse("accounts:google_apply"), {"statement": statement})

    def google_signup(self, claims=None):
        """Sign in with a new Google account and submit the application."""
        self.assertRedirects(self.signin(claims), reverse("accounts:google_apply"))
        self.assertRedirects(self.apply(), reverse("core:home"))
        return GoogleIdentity.objects.select_related("user").get(
            subject=(claims or {}).get("sub", "google-subject-123")
        ).user

    def approved_google_user(self, claims=None):
        user = self.google_signup(claims)
        officer = make_user("officer@example.com", Role.OFFICER)
        MembershipApplication.objects.get(user=user).review(officer, approve=True)
        user.refresh_from_db()
        return user

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

    def test_new_google_user_must_apply_before_anything_is_created(self):
        response = self.signin(self.claims(email="Ada@Gmail.com", role="admin", is_superuser=True))
        self.assertRedirects(response, reverse("accounts:google_apply"))
        self.assertFalse(User.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        page = self.client.get(reverse("accounts:google_apply"))
        self.assertContains(page, "ada@gmail.com")
        self.assertContains(page, "Why do you want to join?")

    def test_google_application_creates_inactive_applicant_with_unusable_password(self):
        self.signin(self.claims(email="Ada@Gmail.com", role="admin", is_superuser=True))
        response = self.apply("Please let me join")
        self.assertRedirects(response, reverse("core:home"))
        identity = GoogleIdentity.objects.select_related("user").get()
        user = identity.user
        self.assertEqual(identity.subject, "google-subject-123")
        self.assertEqual(user.email, "ada@gmail.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(get_role(user), Role.APPLICANT)
        application = MembershipApplication.objects.get(user=user)
        self.assertEqual(application.statement, "Please let me join")
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn(PENDING_SIGNUP_SESSION_KEY, self.client.session)

    def test_google_application_statement_is_required(self):
        self.signin()
        response = self.apply("")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_google_apply_without_verified_signin_is_refused(self):
        response = self.apply()
        self.assertRedirects(response, self.login_url)
        self.assertFalse(User.objects.exists())

    def test_expired_google_signup_is_refused(self):
        with patch("accounts.google_auth.time.time", return_value=1000):
            self.signin(self.claims())
        with patch("accounts.google_auth.time.time", return_value=1000 + PENDING_SIGNUP_TTL_SECONDS + 1):
            response = self.apply()
        self.assertRedirects(response, self.login_url)
        self.assertFalse(User.objects.exists())

    def test_email_taken_between_steps_is_refused(self):
        self.signin()
        make_user("ada@gmail.com")
        response = self.apply()
        self.assertRedirects(response, self.login_url)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(GoogleIdentity.objects.exists())

    def test_pending_google_account_cannot_sign_in_and_is_told_why(self):
        self.google_signup()
        response = self.signin()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "still pending", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rejected_google_account_can_sign_in_as_applicant(self):
        user = self.google_signup()
        MembershipApplication.objects.get(user=user).review(
            make_user("o@example.com", Role.OFFICER), approve=False, note="Not this time."
        )
        response = self.signin()
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(get_role(user), Role.APPLICANT)
        self.assertEqual(GoogleIdentity.objects.count(), 1)

    def test_approved_google_account_signs_in_as_member(self):
        user = self.approved_google_user()
        response = self.signin()
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(get_role(user), Role.MEMBER)

    def test_returning_google_subject_uses_same_user_when_email_changes(self):
        original = self.approved_google_user()
        self.signin(self.claims(email="changed@gmail.com"))
        self.assertEqual(User.objects.exclude(username="officer@example.com").count(), 1)
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
        self.google_signup()
        response = self.signin(self.claims(sub="different-subject"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(GoogleIdentity.objects.count(), 1)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_linked_user_cannot_sign_in(self):
        user = self.approved_google_user()
        MembershipApplication.objects.filter(user=user).delete()
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
        self.assertRedirects(response, reverse("accounts:google_apply"))
        self.assertNotIn(NONCE_SESSION_KEY, self.client.session)

    def test_failed_identity_creation_cleans_up_new_user(self):
        self.signin()
        with patch("accounts.google_auth.GoogleIdentity.objects.create", side_effect=IntegrityError("duplicate")):
            response = self.apply()
        self.assertRedirects(response, self.login_url)
        self.assertFalse(User.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_failed_application_creation_cleans_up_new_user(self):
        self.signin()
        with patch("accounts.google_auth.MembershipApplication.objects.create", side_effect=IntegrityError("x")):
            with self.assertRaises(IntegrityError):
                self.apply()
        self.assertFalse(User.objects.exists())

    def test_failed_user_creation_is_a_safe_login_error(self):
        self.signin()
        with patch.object(User.objects, "create_user", side_effect=IntegrityError("duplicate")):
            response = self.apply()
        self.assertRedirects(response, self.login_url)
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
        self.assertRedirects(response, reverse("accounts:google_apply"))
        self.assertIn(PENDING_SIGNUP_SESSION_KEY, strict_client.session)
        self.assertNotIn("_auth_user_id", strict_client.session)

    def test_google_application_requires_csrf(self):
        strict_client = Client(enforce_csrf_checks=True)
        claims = self.claims(strict_client)
        self.verifier.return_value = claims
        strict_client.post(
            self.url,
            {"credential": "token", "csrfmiddlewaretoken": strict_client.cookies["csrftoken"].value},
        )
        response = self.apply(client=strict_client)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_google_login_does_not_redirect_to_external_next(self):
        self.approved_google_user()
        response = self.signin(next="https://attacker.example/steal")
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_google_login_preserves_safe_local_next(self):
        self.approved_google_user()
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
