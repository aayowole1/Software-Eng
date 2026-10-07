from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Profile, Role, get_role, has_minimum_role, set_role
from .testing import PASSWORD, make_user

User = get_user_model()


class RoleHierarchyTests(TestCase):
    def test_each_role_includes_lower_roles(self):
        self.assertTrue(has_minimum_role(Role.ADMIN, Role.OFFICER))
        self.assertTrue(has_minimum_role(Role.OFFICER, Role.MEMBER))
        self.assertTrue(has_minimum_role(Role.MEMBER, Role.MEMBER))
        self.assertFalse(has_minimum_role(Role.MEMBER, Role.OFFICER))
        self.assertFalse(has_minimum_role(Role.APPLICANT, Role.MEMBER))

    def test_unknown_or_missing_roles_never_pass(self):
        self.assertFalse(has_minimum_role(None, Role.APPLICANT))
        self.assertFalse(has_minimum_role("superhero", Role.APPLICANT))
        self.assertFalse(has_minimum_role(Role.ADMIN, "superhero"))

    def test_new_users_start_as_applicants(self):
        user = make_user("new@example.com")
        self.assertEqual(Profile.objects.get(user=user).role, Role.APPLICANT)

    def test_superusers_are_admins(self):
        admin = User.objects.create_superuser("root@example.com", "root@example.com", PASSWORD)
        self.assertEqual(get_role(admin), Role.ADMIN)

    def test_set_role_rejects_unknown_role(self):
        user = make_user("x@example.com")
        with self.assertRaises(ValueError):
            set_role(user, "superhero")


class RegistrationTests(TestCase):
    url = reverse("accounts:register")

    def post(self, **overrides):
        data = {
            "username": "ada",
            "email": "ada@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_register_creates_applicant_and_signs_in(self):
        response = self.post()
        self.assertRedirects(response, reverse("core:dashboard"))
        user = User.objects.get(username="ada")
        self.assertEqual(user.email, "ada@example.com")
        self.assertEqual(get_role(user), Role.APPLICANT)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)  # stored hashed, never raw
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_new_account_can_sign_in_with_username_or_email(self):
        self.post()
        for identifier in ["ada", "ada@example.com"]:
            with self.subTest(identifier=identifier):
                self.client.logout()
                self.client.post(reverse("accounts:login"), {"username": identifier, "password": PASSWORD})
                self.assertIn("_auth_user_id", self.client.session)

    def test_email_is_stored_lowercase(self):
        self.post(email="Ada@Example.com")
        self.assertEqual(User.objects.get(username="ada").email, "ada@example.com")

    def test_short_password_rejected(self):
        response = self.post(password="short1", confirm_password="short1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_mismatched_passwords_rejected(self):
        self.post(confirm_password="something-else-entirely")
        self.assertFalse(User.objects.exists())

    def test_missing_email_rejected(self):
        self.post(email="")
        self.assertFalse(User.objects.exists())

    def test_missing_username_rejected(self):
        self.post(username="")
        self.assertFalse(User.objects.exists())

    def test_taken_username_rejected(self):
        User.objects.create_user("ada", "other@example.com", PASSWORD)
        response = self.post()
        self.assertContains(response, "This username is already taken.")
        self.assertEqual(User.objects.count(), 1)

    def test_taken_username_check_ignores_case(self):
        User.objects.create_user("ada", "other@example.com", PASSWORD)
        response = self.post(username="ADA")
        self.assertContains(response, "This username is already taken.")
        self.assertEqual(User.objects.count(), 1)

    def test_username_with_invalid_characters_rejected(self):
        for bad in ["ada@example.com", "ada smith", "ada!"]:
            with self.subTest(username=bad):
                response = self.post(username=bad)
                self.assertContains(response, "Use only letters, numbers")
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_rejected(self):
        User.objects.create_user("someone", "ada@example.com", PASSWORD)
        response = self.post(email="ADA@example.com")
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_email_used_as_older_accounts_username_rejected(self):
        make_user("ada@example.com")  # older accounts: username == email
        response = self.post()
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        make_user("ada@example.com")

    def test_login_with_email_and_password(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ada@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_wrong_password_rejected(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ada@example.com", "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_email_rejected(self):
        self.client.post(reverse("accounts:login"), {"username": "who@example.com", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

    def login(self, identifier, password=PASSWORD):
        self.client.post(reverse("accounts:login"), {"username": identifier, "password": password})
        return "_auth_user_id" in self.client.session

    def test_email_is_case_insensitive(self):
        self.assertTrue(self.login("Ada@Example.com"))

    def test_login_with_username_when_it_differs_from_email(self):
        # e.g. an account made with `createsuperuser` using a plain username
        User.objects.create_superuser("aayowole1", "mide@example.com", PASSWORD)
        self.assertTrue(self.login("aayowole1"))

    def test_login_with_email_when_username_differs(self):
        User.objects.create_superuser("aayowole1", "mide@example.com", PASSWORD)
        self.assertTrue(self.login("mide@example.com"))

    def test_wrong_password_with_username_rejected(self):
        User.objects.create_superuser("aayowole1", "mide@example.com", PASSWORD)
        self.assertFalse(self.login("aayowole1", "wrong-password"))

    def test_email_shared_by_two_accounts_is_ambiguous(self):
        User.objects.create_user("first", "shared@example.com", PASSWORD)
        User.objects.create_user("second", "shared@example.com", PASSWORD)
        self.assertFalse(self.login("shared@example.com"))
        self.assertTrue(self.login("first"))

    def test_inactive_user_rejected(self):
        User.objects.filter(username="ada@example.com").update(is_active=False)
        self.assertFalse(self.login("ada@example.com"))

    def test_logout(self):
        self.client.login(username="ada@example.com", password=PASSWORD)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfileTests(TestCase):
    def test_profile_requires_sign_in(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}")

    def test_profile_shows_role_without_password_hash(self):
        user = make_user("ada@example.com", Role.MEMBER)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "ada@example.com")
        self.assertContains(response, "member")
        self.assertNotContains(response, user.password)


class AdminRoleManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.target = make_user("ada@example.com")

    def change(self, user, role):
        return self.client.post(reverse("accounts:change_role", args=[user.pk]), {"role": role})

    def test_admin_can_change_role(self):
        self.client.force_login(self.admin)
        self.change(self.target, Role.OFFICER)
        self.assertEqual(get_role(self.target), Role.OFFICER)

    def test_invalid_role_is_ignored(self):
        self.client.force_login(self.admin)
        self.change(self.target, "superhero")
        self.assertEqual(get_role(self.target), Role.APPLICANT)

    def test_admin_cannot_change_own_role(self):
        self.client.force_login(self.admin)
        self.change(self.admin, Role.MEMBER)
        self.assertEqual(get_role(self.admin), Role.ADMIN)

    def test_unknown_user_is_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:change_role", args=["0123456789abcdef01234567"]), {"role": Role.MEMBER}
        )
        self.assertEqual(response.status_code, 404)

    def test_non_admins_get_403(self):
        for role in [Role.APPLICANT, Role.MEMBER, Role.OFFICER]:
            with self.subTest(role=role):
                self.client.force_login(make_user(f"{role}@example.com", role))
                self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)
                self.assertEqual(self.change(self.target, Role.ADMIN).status_code, 403)
        self.assertEqual(get_role(self.target), Role.APPLICANT)

    def test_user_list_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertContains(response, "ada@example.com")
