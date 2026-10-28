"""Unit tests for accounts/google_auth.py helper functions.

These tests target the internal helper functions that are not already covered
by the integration-level tests in test_google_auth.py.
"""

import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from membership.models import ApplicationStatus, MembershipApplication

from .google_auth import (
    GoogleSignInError,
    MAX_NONCES,
    NONCE_SESSION_KEY,
    NONCE_TTL_SECONDS,
    PENDING_SIGNUP_SESSION_KEY,
    PENDING_SIGNUP_TTL_SECONDS,
    _consume_nonce,
    _ensure_email_unused,
    _existing_identity_user,
    _live_nonces,
    _pending_signup,
    _safe_next,
    _validated_claims,
    create_google_applicant,
    google_login_context,
)
from .models import GoogleIdentity, Role
from .testing import PASSWORD, make_user

User = get_user_model()
CLIENT_ID = "orgflow-test.apps.googleusercontent.com"


# ---------------------------------------------------------------------------
# _live_nonces
# ---------------------------------------------------------------------------

class LiveNoncesTests(SimpleTestCase):
    """Unit tests for _live_nonces()."""

    def _request_with_nonces(self, entries):
        request = RequestFactory().get("/")
        request.session = {NONCE_SESSION_KEY: entries}
        return request

    def test_returns_empty_list_when_session_is_empty(self):
        request = RequestFactory().get("/")
        request.session = {}
        self.assertEqual(_live_nonces(request), [])

    def test_valid_fresh_entry_is_returned(self):
        entry = {"token": "abc", "issued": time.time()}
        request = self._request_with_nonces([entry])
        result = _live_nonces(request)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["token"], "abc")

    def test_expired_entry_is_filtered_out(self):
        old_issued = time.time() - NONCE_TTL_SECONDS - 1
        entry = {"token": "old", "issued": old_issued}
        request = self._request_with_nonces([entry])
        self.assertEqual(_live_nonces(request), [])

    def test_malformed_entries_are_filtered_out(self):
        bad_entries = [
            "not-a-dict",
            {"token": 123, "issued": time.time()},          # token not a str
            {"token": "abc", "issued": "now"},              # issued not a number
            {"only_token": "abc"},                          # missing issued
            {},
        ]
        request = self._request_with_nonces(bad_entries)
        self.assertEqual(_live_nonces(request), [])

    def test_result_is_bounded_to_max_nonces(self):
        now = time.time()
        entries = [{"token": f"tok-{i}", "issued": now} for i in range(MAX_NONCES + 5)]
        request = self._request_with_nonces(entries)
        result = _live_nonces(request)
        self.assertLessEqual(len(result), MAX_NONCES)


# ---------------------------------------------------------------------------
# _consume_nonce
# ---------------------------------------------------------------------------

class ConsumeNonceTests(SimpleTestCase):
    """Unit tests for _consume_nonce()."""

    def _request_with_nonce(self, token):
        request = RequestFactory().get("/")
        request.session = {
            NONCE_SESSION_KEY: [{"token": token, "issued": time.time()}]
        }
        return request

    def test_valid_nonce_is_consumed_and_returns_true(self):
        request = self._request_with_nonce("valid-nonce")
        self.assertTrue(_consume_nonce(request, "valid-nonce"))
        # The nonce must be removed from the session.
        remaining = request.session.get(NONCE_SESSION_KEY, [])
        self.assertFalse(any(e.get("token") == "valid-nonce" for e in remaining))

    def test_wrong_nonce_returns_false_and_keeps_original(self):
        request = self._request_with_nonce("correct-nonce")
        self.assertFalse(_consume_nonce(request, "wrong-nonce"))
        remaining = request.session.get(NONCE_SESSION_KEY, [])
        self.assertTrue(any(e.get("token") == "correct-nonce" for e in remaining))

    def test_none_nonce_returns_false(self):
        request = self._request_with_nonce("some-nonce")
        self.assertFalse(_consume_nonce(request, None))

    def test_non_ascii_nonce_returns_false(self):
        request = self._request_with_nonce("some-nonce")
        self.assertFalse(_consume_nonce(request, "nonce-\u00e9"))

    def test_empty_nonce_returns_false(self):
        request = self._request_with_nonce("some-nonce")
        self.assertFalse(_consume_nonce(request, ""))

    def test_each_nonce_can_only_be_consumed_once(self):
        request = self._request_with_nonce("one-time")
        self.assertTrue(_consume_nonce(request, "one-time"))
        self.assertFalse(_consume_nonce(request, "one-time"))

    def test_other_nonces_are_kept_after_consumption(self):
        now = time.time()
        request = RequestFactory().get("/")
        request.session = {
            NONCE_SESSION_KEY: [
                {"token": "first", "issued": now},
                {"token": "second", "issued": now},
            ]
        }
        self.assertTrue(_consume_nonce(request, "first"))
        remaining = request.session.get(NONCE_SESSION_KEY, [])
        tokens = [e["token"] for e in remaining]
        self.assertNotIn("first", tokens)
        self.assertIn("second", tokens)


# ---------------------------------------------------------------------------
# google_login_context
# ---------------------------------------------------------------------------

@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleLoginContextTests(SimpleTestCase):
    """Unit tests for google_login_context()."""

    def _request(self):
        request = RequestFactory().get("/accounts/login/")
        request.session = {}
        return request

    def test_returns_enabled_with_client_id_and_nonce(self):
        request = self._request()
        ctx = google_login_context(request)
        self.assertTrue(ctx["google_enabled"])
        self.assertEqual(ctx["google_client_id"], CLIENT_ID)
        self.assertIsInstance(ctx["google_nonce"], str)
        self.assertTrue(ctx["google_nonce"])

    def test_each_call_issues_unique_nonce(self):
        request = self._request()
        first = google_login_context(request)["google_nonce"]
        second = google_login_context(request)["google_nonce"]
        self.assertNotEqual(first, second)

    def test_nonce_is_stored_in_session(self):
        request = self._request()
        nonce = google_login_context(request)["google_nonce"]
        entries = request.session.get(NONCE_SESSION_KEY, [])
        tokens = [e["token"] for e in entries]
        self.assertIn(nonce, tokens)

    def test_session_is_bounded_to_max_nonces(self):
        request = self._request()
        for _ in range(MAX_NONCES + 3):
            google_login_context(request)
        self.assertLessEqual(len(request.session[NONCE_SESSION_KEY]), MAX_NONCES)

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_disabled_when_client_id_is_empty(self):
        request = self._request()
        ctx = google_login_context(request)
        self.assertFalse(ctx["google_enabled"])
        self.assertNotIn("google_nonce", ctx)

    @override_settings(GOOGLE_CLIENT_ID="   ")
    def test_disabled_when_client_id_is_whitespace(self):
        request = self._request()
        ctx = google_login_context(request)
        self.assertFalse(ctx["google_enabled"])


# ---------------------------------------------------------------------------
# _validated_claims
# ---------------------------------------------------------------------------

class ValidatedClaimsTests(SimpleTestCase):
    """Unit tests for _validated_claims()."""

    def _valid(self):
        return {
            "sub": "google-subject-001",
            "email": "user@example.com",
            "email_verified": True,
        }

    def test_valid_claims_return_subject_and_normalised_email(self):
        subject, email = _validated_claims(self._valid())
        self.assertEqual(subject, "google-subject-001")
        self.assertEqual(email, "user@example.com")

    def test_email_is_lowercased_and_stripped(self):
        claims = self._valid()
        claims["email"] = "  User@EXAMPLE.COM  "
        _, email = _validated_claims(claims)
        self.assertEqual(email, "user@example.com")

    def test_missing_subject_raises(self):
        claims = self._valid()
        del claims["sub"]
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_empty_subject_raises(self):
        claims = {**self._valid(), "sub": ""}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_whitespace_only_subject_raises(self):
        claims = {**self._valid(), "sub": "   "}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_oversized_subject_raises(self):
        claims = {**self._valid(), "sub": "x" * 256}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_non_string_subject_raises(self):
        claims = {**self._valid(), "sub": 12345}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_unverified_email_raises(self):
        claims = {**self._valid(), "email_verified": False}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_missing_email_verified_raises(self):
        claims = self._valid()
        del claims["email_verified"]
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_non_bool_email_verified_raises(self):
        claims = {**self._valid(), "email_verified": "true"}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_invalid_email_format_raises(self):
        claims = {**self._valid(), "email": "not-an-email"}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_oversized_email_raises(self):
        # 250 + len("@example.com") = 262 characters, over the 254 limit.
        local = "a" * 250
        claims = {**self._valid(), "email": f"{local}@example.com"}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)

    def test_none_email_raises(self):
        claims = {**self._valid(), "email": None}
        with self.assertRaises(GoogleSignInError):
            _validated_claims(claims)


# ---------------------------------------------------------------------------
# _ensure_email_unused
# ---------------------------------------------------------------------------

@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class EnsureEmailUnusedTests(TestCase):
    """Unit tests for _ensure_email_unused()."""

    def test_unused_email_does_not_raise(self):
        _ensure_email_unused("brand-new@example.com")  # must not raise

    def test_email_used_by_existing_account_raises(self):
        make_user("taken@example.com")
        with self.assertRaises(GoogleSignInError):
            _ensure_email_unused("taken@example.com")

    def test_email_comparison_is_case_insensitive(self):
        make_user("taken@example.com")
        with self.assertRaises(GoogleSignInError):
            _ensure_email_unused("TAKEN@EXAMPLE.COM")

    def test_email_used_as_username_raises(self):
        # Legacy accounts where username == email.
        User.objects.create_user("legacy@example.com", "", PASSWORD)
        with self.assertRaises(GoogleSignInError):
            _ensure_email_unused("legacy@example.com")


# ---------------------------------------------------------------------------
# _existing_identity_user
# ---------------------------------------------------------------------------

@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class ExistingIdentityUserTests(TestCase):
    """Unit tests for _existing_identity_user()."""

    def test_unknown_subject_returns_none(self):
        result = _existing_identity_user("unknown-subject")
        self.assertIsNone(result)

    def test_known_active_subject_returns_user(self):
        user = make_user("ada@example.com", Role.MEMBER)
        GoogleIdentity.objects.create(subject="sub-001", user=user)
        result = _existing_identity_user("sub-001")
        self.assertEqual(result, user)

    def test_known_inactive_subject_raises_google_signin_error(self):
        user = make_user("inactive@example.com")
        user.is_active = False
        user.save()
        GoogleIdentity.objects.create(subject="sub-inactive", user=user)
        with self.assertRaises(GoogleSignInError):
            _existing_identity_user("sub-inactive")

    def test_inactive_with_pending_application_mentions_pending(self):
        user = make_user("pending@example.com")
        user.is_active = False
        user.save()
        MembershipApplication.objects.create(user=user, statement="Hi")
        GoogleIdentity.objects.create(subject="sub-pending", user=user)
        with self.assertRaisesMessage(GoogleSignInError, "still pending"):
            _existing_identity_user("sub-pending")


# ---------------------------------------------------------------------------
# create_google_applicant
# ---------------------------------------------------------------------------

@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class CreateGoogleApplicantTests(TestCase):
    """Unit tests for create_google_applicant()."""

    def test_creates_inactive_user_with_application_and_identity(self):
        user = create_google_applicant("sub-new", "new@example.com", "I want to help.")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(GoogleIdentity.objects.filter(subject="sub-new", user=user).exists())
        app = MembershipApplication.objects.get(user=user)
        self.assertEqual(app.statement, "I want to help.")
        self.assertEqual(app.status, ApplicationStatus.PENDING)

    def test_duplicate_subject_raises(self):
        create_google_applicant("sub-dup", "first@example.com", "First.")
        with self.assertRaises(GoogleSignInError):
            create_google_applicant("sub-dup", "second@example.com", "Second.")
        self.assertEqual(User.objects.count(), 1)

    def test_email_already_taken_raises_before_creating_user(self):
        make_user("taken@example.com")
        with self.assertRaises(GoogleSignInError):
            create_google_applicant("sub-new", "taken@example.com", "Hi.")
        # No new user should have been created.
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(GoogleIdentity.objects.exists())

    def test_user_is_not_staff_or_superuser(self):
        user = create_google_applicant("sub-safe", "safe@example.com", "Statement.")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_generated_username_starts_with_google_prefix(self):
        user = create_google_applicant("sub-prefix", "prefix@example.com", "Ok.")
        self.assertTrue(user.username.startswith("google_"))


# ---------------------------------------------------------------------------
# _safe_next
# ---------------------------------------------------------------------------

class SafeNextTests(SimpleTestCase):
    """Unit tests for _safe_next()."""

    def _post(self, next_url="", host="testserver"):
        request = RequestFactory().post("/accounts/google/", {"next": next_url}, HTTP_HOST=host)
        return request

    def test_valid_local_path_is_returned(self):
        request = self._post("/accounts/profile/")
        result = _safe_next(request)
        self.assertEqual(result, "/accounts/profile/")

    def test_external_url_returns_dashboard(self):
        request = self._post("https://evil.example/steal")
        result = _safe_next(request)
        self.assertEqual(result, reverse("core:dashboard"))

    def test_empty_next_returns_dashboard(self):
        request = self._post("")
        result = _safe_next(request)
        self.assertEqual(result, reverse("core:dashboard"))

    def test_missing_next_returns_dashboard(self):
        request = RequestFactory().post("/accounts/google/", {})
        result = _safe_next(request)
        self.assertEqual(result, reverse("core:dashboard"))


# ---------------------------------------------------------------------------
# _pending_signup
# ---------------------------------------------------------------------------

class PendingSignupTests(SimpleTestCase):
    """Unit tests for _pending_signup()."""

    def _request_with_pending(self, issued=None, subject="sub-001", email="g@example.com"):
        request = RequestFactory().get("/")
        request.session = {
            PENDING_SIGNUP_SESSION_KEY: {
                "subject": subject,
                "email": email,
                "issued": issued if issued is not None else time.time(),
            }
        }
        return request

    def test_valid_fresh_pending_is_returned(self):
        request = self._request_with_pending()
        result = _pending_signup(request)
        self.assertIsNotNone(result)
        self.assertEqual(result["subject"], "sub-001")
        self.assertEqual(result["email"], "g@example.com")

    def test_expired_pending_returns_none_and_clears_session(self):
        old = time.time() - PENDING_SIGNUP_TTL_SECONDS - 1
        request = self._request_with_pending(issued=old)
        result = _pending_signup(request)
        self.assertIsNone(result)
        self.assertNotIn(PENDING_SIGNUP_SESSION_KEY, request.session)

    def test_missing_pending_session_returns_none(self):
        request = RequestFactory().get("/")
        request.session = {}
        self.assertIsNone(_pending_signup(request))

    def test_malformed_pending_returns_none(self):
        request = RequestFactory().get("/")
        request.session = {PENDING_SIGNUP_SESSION_KEY: "not-a-dict"}
        self.assertIsNone(_pending_signup(request))

    def test_missing_subject_returns_none(self):
        request = self._request_with_pending()
        del request.session[PENDING_SIGNUP_SESSION_KEY]["subject"]
        self.assertIsNone(_pending_signup(request))

    def test_missing_email_returns_none(self):
        request = self._request_with_pending()
        del request.session[PENDING_SIGNUP_SESSION_KEY]["email"]
        self.assertIsNone(_pending_signup(request))

    def test_non_string_subject_returns_none(self):
        request = RequestFactory().get("/")
        request.session = {
            PENDING_SIGNUP_SESSION_KEY: {
                "subject": 12345,
                "email": "g@example.com",
                "issued": time.time(),
            }
        }
        self.assertIsNone(_pending_signup(request))
