"""Real MongoDB uniqueness, safe legacy preflight and concurrent signup checks."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections
from django.test import TestCase, override_settings
from pymongo.errors import DuplicateKeyError

from membership.models import MembershipApplication

from .backends import find_user
from .forms import PasswordSignupRetryError, RegisterForm
from .google_auth import GoogleSignInError, create_google_applicant
from .models import GoogleIdentity, Profile
from .testing import PASSWORD

User = get_user_model()
identifier_migration = import_module("accounts.migrations.0006_canonical_account_identifiers")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IdentifierUniquenessTests(TestCase):
    def form(self, username, email):
        form = RegisterForm({
            "username": username, "email": email, "password": PASSWORD,
            "confirm_password": PASSWORD, "statement": "Synthetic membership request",
        })
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def parallel(self, *operations):
        gate = Barrier(len(operations), timeout=10)

        def run(operation):
            try:
                gate.wait()
                try:
                    user = operation()
                    return ("created", str(user.pk))
                except (PasswordSignupRetryError, GoogleSignInError):
                    return ("rejected", None)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def assert_one_complete_signup(self, results):
        self.assertEqual(sorted(result[0] for result in results), ["created", "rejected"])
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get()
        self.assertFalse(user.is_active)
        self.assertEqual(Profile.objects.get().user_id, user.pk)
        self.assertEqual(MembershipApplication.objects.get().user_id, user.pk)
        self.assertEqual(find_user(user.email).pk, user.pk)
        return user

    def test_migration_installs_unique_strength_two_indexes_with_supported_partial_filter(self):
        indexes = {index["name"]: index for index in connection.database[User._meta.db_table].list_indexes()}
        for name in (identifier_migration.USERNAME_INDEX, identifier_migration.EMAIL_INDEX):
            self.assertTrue(indexes[name]["unique"])
            self.assertEqual(indexes[name]["collation"]["locale"], "en")
            self.assertEqual(indexes[name]["collation"]["strength"], 2)
        self.assertEqual(indexes[identifier_migration.EMAIL_INDEX]["partialFilterExpression"], identifier_migration.NONBLANK_EMAIL)

    def test_database_rejects_case_variant_username_even_without_form_validation(self):
        User.objects.create_user("CaseUser", "first@example.com", PASSWORD)
        with self.assertRaises(IntegrityError):
            User.objects.create_user("cASEuSER", "second@example.com", PASSWORD)
        self.assertEqual(User.objects.count(), 1)

    def test_database_rejects_case_variant_nonblank_email_on_insert_and_update(self):
        first = User.objects.create_user("first", "Owner@Example.com", PASSWORD)
        with self.assertRaises(IntegrityError):
            User.objects.create_user("second", "OWNER@example.com", PASSWORD)
        other = User.objects.create_user("other", "other@example.com", PASSWORD)
        with self.assertRaises(IntegrityError):
            User.objects.filter(pk=other.pk).update(email="owner@EXAMPLE.com")
        other.refresh_from_db()
        self.assertEqual(other.email, "other@example.com")
        self.assertEqual(find_user("OWNER@example.com").pk, first.pk)

    def test_multiple_blank_admin_emails_remain_allowed(self):
        User.objects.create_superuser("root_one", "", PASSWORD)
        User.objects.create_superuser("root_two", "", PASSWORD)
        self.assertEqual(User.objects.filter(email="").count(), 2)

    def test_parallel_password_signups_with_case_variant_usernames_keep_one_complete_account(self):
        first = self.form("ConcurrentName", "first@example.com")
        second = self.form("cONCURRENTnAME", "second@example.com")
        self.assert_one_complete_signup(self.parallel(first.save, second.save))

    def test_parallel_password_signups_with_same_email_keep_one_complete_account(self):
        first = self.form("firstlocal", "Shared@Example.com")
        second = self.form("secondlocal", "SHARED@example.com")
        self.assert_one_complete_signup(self.parallel(first.save, second.save))

    def test_parallel_google_and_password_signups_cannot_duplicate_or_remove_the_winner(self):
        form = self.form("localuser", "Mixed@Example.com")
        create_user = User.objects.create_user
        before_insert = Barrier(2, timeout=10)

        def synchronized_create(*args, **kwargs):
            before_insert.wait()
            return create_user(*args, **kwargs)

        # Both paths have passed their ordinary prechecks before either insert.
        with patch.object(User.objects, "create_user", side_effect=synchronized_create):
            results = self.parallel(form.save, lambda: create_google_applicant("parallel-google-subject", "MIXED@EXAMPLE.COM", "Synthetic Google request"))
        user = self.assert_one_complete_signup(results)
        identities = list(GoogleIdentity.objects.all())
        if identities:
            self.assertEqual(len(identities), 1)
            self.assertEqual(identities[0].user_id, user.pk)
            self.assertFalse(user.has_usable_password())
        else:
            self.assertTrue(user.has_usable_password())

    def test_existing_local_email_still_does_not_auto_link_a_google_identity(self):
        user = User.objects.create_user("existing", "owner@example.com", PASSWORD)
        with self.assertRaises(GoogleSignInError):
            create_google_applicant("different-subject", "OWNER@example.com", "Synthetic request")
        self.assertEqual(list(User.objects.values_list("pk", flat=True)), [user.pk])
        self.assertFalse(GoogleIdentity.objects.exists())


class IdentifierMigrationPreflightTests(TestCase):
    def setUp(self):
        self.name = "identifier_preflight_" + uuid4().hex
        self.collection = connection.database[self.name]

    def tearDown(self):
        connection.database.drop_collection(self.name)

    def test_legacy_case_variant_usernames_stop_before_indexes_without_identity_disclosure(self):
        self.collection.insert_many([
            {"username": "PrivateLegacyName", "email": "first@example.com"},
            {"username": "pRIVATElEGACYnAME", "email": "second@example.com"},
        ])
        with self.assertRaises(RuntimeError) as error:
            identifier_migration.ensure_identifier_indexes(self.collection)
        self.assertIn("authorized data owner", str(error.exception))
        self.assertIn("usernames", str(error.exception))
        self.assertNotIn("PrivateLegacyName", str(error.exception))
        self.assertEqual(self.collection.count_documents({}), 2)
        self.assertNotIn(identifier_migration.EMAIL_INDEX, self.collection.index_information())

    def test_legacy_case_variant_emails_stop_without_deleting_or_deduplicating(self):
        self.collection.insert_many([
            {"username": "one", "email": "PrivateLegacy@Example.com"},
            {"username": "two", "email": "PRIVATELEGACY@example.com"},
        ])
        with self.assertRaises(RuntimeError) as error:
            identifier_migration.ensure_identifier_indexes(self.collection)
        self.assertIn("nonblank emails", str(error.exception))
        self.assertNotIn("PrivateLegacy", str(error.exception))
        self.assertEqual(self.collection.count_documents({}), 2)
        self.assertNotIn(identifier_migration.USERNAME_INDEX, self.collection.index_information())

    def test_blank_missing_and_null_emails_are_excluded_and_repeated_install_is_safe(self):
        self.collection.insert_many([
            {"username": "one", "email": ""}, {"username": "two", "email": ""},
            {"username": "three"}, {"username": "four", "email": None},
        ])
        identifier_migration.ensure_identifier_indexes(self.collection)
        identifier_migration.ensure_identifier_indexes(self.collection)
        self.collection.insert_one({"username": "five", "email": ""})
        with self.assertRaises(DuplicateKeyError):
            self.collection.insert_one({"username": "FIVE", "email": "unique@example.com"})
        self.assertEqual(self.collection.count_documents({}), 5)

    def test_index_build_failure_omits_private_duplicate_key_details(self):
        self.collection.insert_one({"username": "existing", "email": "private@example.com"})
        with patch.object(self.collection, "create_indexes", side_effect=DuplicateKeyError("private@example.com duplicate key")):
            with self.assertRaises(RuntimeError) as error:
                identifier_migration.ensure_identifier_indexes(self.collection)
        self.assertNotIn("private@example.com", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)
        self.assertEqual(self.collection.count_documents({}), 1)
