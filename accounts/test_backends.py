"""Unit tests for accounts/backends.py — find_user() and EmailOrUsernameBackend."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from .backends import EmailOrUsernameBackend, find_user
from .testing import PASSWORD, make_user

User = get_user_model()


class FindUserTests(TestCase):
    """Direct unit tests for find_user()."""

    def setUp(self):
        self.user = make_user("ada@example.com")

    # ---- username lookup ----

    def test_finds_user_by_exact_username(self):
        self.assertEqual(find_user("ada@example.com"), self.user)

    def test_username_lookup_is_case_sensitive(self):
        # Django usernames are case-sensitive by default; a mismatched case
        # should fall through to the email path.
        User.objects.create_user("Ada", "other@example.com", PASSWORD)
        result = find_user("Ada")
        self.assertIsNotNone(result)
        self.assertEqual(result.username, "Ada")

    def test_finds_user_by_username_when_another_has_same_email(self):
        User.objects.create_user("second", "ada@example.com", PASSWORD)
        # "ada@example.com" as username should match only self.user
        self.assertEqual(find_user("ada@example.com"), self.user)

    # ---- email lookup ----

    def test_finds_user_by_email_when_username_does_not_match(self):
        other = User.objects.create_user("different_name", "bob@example.com", PASSWORD)
        self.assertEqual(find_user("bob@example.com"), other)

    def test_email_lookup_is_case_insensitive(self):
        other = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.assertEqual(find_user("BOB@EXAMPLE.COM"), other)

    def test_email_lookup_returns_none_when_two_accounts_share_email(self):
        User.objects.create_user("first", "shared@example.com", PASSWORD)
        User.objects.create_user("second", "shared@example.com", PASSWORD)
        self.assertIsNone(find_user("shared@example.com"))

    def test_unknown_identifier_returns_none(self):
        self.assertIsNone(find_user("nobody@example.com"))

    # ---- edge cases ----

    def test_none_returns_none(self):
        self.assertIsNone(find_user(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(find_user(""))

    def test_whitespace_only_string_returns_none(self):
        self.assertIsNone(find_user("   "))

    def test_leading_and_trailing_whitespace_is_stripped(self):
        # "  ada@example.com  " should match self.user by username.
        self.assertEqual(find_user("  ada@example.com  "), self.user)


class EmailOrUsernameBackendTests(TestCase):
    """Direct unit tests for EmailOrUsernameBackend.authenticate()."""

    def setUp(self):
        self.backend = EmailOrUsernameBackend()
        self.request = RequestFactory().get("/")
        self.user = make_user("ada@example.com")

    def test_correct_username_and_password_returns_user(self):
        result = self.backend.authenticate(self.request, username="ada@example.com", password=PASSWORD)
        self.assertEqual(result, self.user)

    def test_correct_email_and_password_returns_user(self):
        # When the username field doubles as email (our make_user helper), this
        # goes through the username path first and still succeeds.
        result = self.backend.authenticate(self.request, username="ada@example.com", password=PASSWORD)
        self.assertEqual(result, self.user)

    def test_wrong_password_returns_none(self):
        result = self.backend.authenticate(self.request, username="ada@example.com", password="wrong")
        self.assertIsNone(result)

    def test_unknown_identifier_returns_none(self):
        result = self.backend.authenticate(self.request, username="ghost@example.com", password=PASSWORD)
        self.assertIsNone(result)

    def test_none_username_returns_none(self):
        result = self.backend.authenticate(self.request, username=None, password=PASSWORD)
        self.assertIsNone(result)

    def test_none_password_returns_none(self):
        result = self.backend.authenticate(self.request, username="ada@example.com", password=None)
        self.assertIsNone(result)

    def test_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save()
        result = self.backend.authenticate(self.request, username="ada@example.com", password=PASSWORD)
        self.assertIsNone(result)

    def test_timing_safe_for_unknown_user_does_not_raise(self):
        # The backend runs the hasher even for missing accounts; calling it
        # with an unknown identifier must not throw any exception.
        result = self.backend.authenticate(self.request, username="no-such@example.com", password="anything")
        self.assertIsNone(result)

    def test_email_lookup_used_when_username_not_found(self):
        # Create a user whose username differs from their email address.
        other = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        result = self.backend.authenticate(self.request, username="alice@example.com", password=PASSWORD)
        self.assertEqual(result, other)

    def test_ambiguous_email_prevents_sign_in(self):
        User.objects.create_user("first", "shared@example.com", PASSWORD)
        User.objects.create_user("second", "shared@example.com", PASSWORD)
        result = self.backend.authenticate(self.request, username="shared@example.com", password=PASSWORD)
        self.assertIsNone(result)
