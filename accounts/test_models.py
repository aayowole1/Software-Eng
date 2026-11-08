"""Unit tests for accounts/models.py helper functions.

Tests for has_minimum_role(), get_role(), and set_role() that complement the
integration-level coverage in tests.py and focus on the functions' contracts
in isolation.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    ROLE_LEVELS,
    ROSTER_ROLES,
    Role,
    Profile,
    get_role,
    has_minimum_role,
    set_role,
)
from .testing import PASSWORD, make_user

User = get_user_model()


class HasMinimumRoleTests(TestCase):
    """Unit tests for has_minimum_role()."""

    def test_equal_roles_pass(self):
        for role in Role.values:
            with self.subTest(role=role):
                self.assertTrue(has_minimum_role(role, role))

    def test_admin_passes_all_requirements(self):
        for required in Role.values:
            with self.subTest(required=required):
                self.assertTrue(has_minimum_role(Role.ADMIN, required))

    def test_applicant_fails_all_requirements_above_itself(self):
        for required in [Role.MEMBER, Role.OFFICER, Role.ADMIN]:
            with self.subTest(required=required):
                self.assertFalse(has_minimum_role(Role.APPLICANT, required))

    def test_member_fails_officer_and_above(self):
        self.assertFalse(has_minimum_role(Role.MEMBER, Role.OFFICER))
        self.assertFalse(has_minimum_role(Role.MEMBER, Role.ADMIN))

    def test_officer_fails_admin(self):
        self.assertFalse(has_minimum_role(Role.OFFICER, Role.ADMIN))

    def test_none_user_role_always_fails(self):
        for required in Role.values:
            with self.subTest(required=required):
                self.assertFalse(has_minimum_role(None, required))

    def test_unknown_required_role_always_fails(self):
        # Unknown required role maps to inf, so nothing can satisfy it.
        for user_role in Role.values:
            with self.subTest(user_role=user_role):
                self.assertFalse(has_minimum_role(user_role, "superhero"))

    def test_unknown_user_role_always_fails(self):
        self.assertFalse(has_minimum_role("superhero", Role.APPLICANT))

    def test_role_levels_are_strictly_ordered(self):
        levels = [ROLE_LEVELS[r] for r in [Role.APPLICANT, Role.MEMBER, Role.OFFICER, Role.ADMIN]]
        self.assertEqual(levels, sorted(levels))
        self.assertEqual(len(set(levels)), 4)  # all distinct


class GetRoleTests(TestCase):
    """Unit tests for get_role()."""

    def test_unauthenticated_user_returns_none(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(get_role(AnonymousUser()))

    def test_new_user_starts_as_applicant(self):
        user = make_user("new@example.com")
        self.assertEqual(get_role(user), Role.APPLICANT)

    def test_superuser_always_returns_admin(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.assertEqual(get_role(su), Role.ADMIN)

    def test_superuser_returns_admin_even_when_profile_role_differs(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        # Force the stored role to something lower.
        Profile.objects.filter(user=su).update(role=Role.MEMBER)
        self.assertEqual(get_role(su), Role.ADMIN)

    def test_creates_profile_when_missing(self):
        user = make_user("no_profile@example.com")
        Profile.objects.filter(user=user).delete()
        self.assertFalse(Profile.objects.filter(user=user).exists())
        role = get_role(user)
        self.assertEqual(role, Role.APPLICANT)
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_officer_returns_officer(self):
        user = make_user("officer@example.com", Role.OFFICER)
        self.assertEqual(get_role(user), Role.OFFICER)


class SetRoleTests(TestCase):
    """Unit tests for set_role()."""

    def test_can_set_any_valid_role_on_regular_user(self):
        user = make_user("ada@example.com")
        for role in [Role.MEMBER, Role.OFFICER, Role.ADMIN, Role.APPLICANT]:
            with self.subTest(role=role):
                set_role(user, role)
                self.assertEqual(get_role(user), role)

    def test_raises_for_invalid_role_string(self):
        user = make_user("ada@example.com")
        with self.assertRaises(ValueError):
            set_role(user, "emperor")

    def test_raises_when_demoting_superuser(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        for role in [Role.APPLICANT, Role.MEMBER, Role.OFFICER]:
            with self.subTest(role=role), self.assertRaises(ValueError):
                set_role(su, role)

    def test_setting_admin_on_superuser_is_allowed(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        profile = set_role(su, Role.ADMIN)
        self.assertEqual(profile.role, Role.ADMIN)

    def test_creates_profile_when_missing(self):
        user = make_user("new@example.com")
        Profile.objects.filter(user=user).delete()
        set_role(user, Role.MEMBER)
        self.assertEqual(Profile.objects.get(user=user).role, Role.MEMBER)

    def test_returns_profile_instance(self):
        user = make_user("ada@example.com")
        result = set_role(user, Role.MEMBER)
        self.assertIsInstance(result, Profile)
        self.assertEqual(result.role, Role.MEMBER)


class ProfileCleanTests(TestCase):
    """Unit tests for Profile.clean() validation."""

    def test_clean_rejects_non_admin_role_for_superuser(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        profile = Profile.objects.get_or_create(user=su)[0]
        profile.role = Role.MEMBER
        with self.assertRaises(ValidationError):
            profile.clean()

    def test_clean_accepts_admin_role_for_superuser(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        profile = Profile.objects.get_or_create(user=su)[0]
        profile.role = Role.ADMIN
        profile.clean()  # must not raise

    def test_clean_accepts_any_role_for_regular_user(self):
        user = make_user("ada@example.com")
        profile = Profile.objects.get(user=user)
        for role in Role.values:
            profile.role = role
            profile.clean()  # must not raise


class RosterRolesTests(TestCase):
    """Sanity-check ROSTER_ROLES constant."""

    def test_roster_roles_does_not_include_applicant(self):
        self.assertNotIn(Role.APPLICANT, ROSTER_ROLES)

    def test_roster_roles_includes_member_officer_admin(self):
        for role in [Role.MEMBER, Role.OFFICER, Role.ADMIN]:
            self.assertIn(role, ROSTER_ROLES)
