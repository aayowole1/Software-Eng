"""Regression coverage for the Accounts 1.3 progress checkpoint."""

from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.db.migrations.loader import MigrationLoader
from django.forms import modelform_factory
from django.test import Client, TestCase
from django.urls import reverse

from .models import Profile, Role, get_role, set_role
from .testing import PASSWORD, make_user

User = get_user_model()


class SuperuserRoleSafetyTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.superuser = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.force_login(self.admin)

    def test_superuser_demotion_rejected_by_service(self):
        for role in (Role.APPLICANT, Role.MEMBER, Role.OFFICER):
            with self.subTest(role=role), self.assertRaisesMessage(ValueError, "Superusers must remain admins"):
                set_role(self.superuser, role)
        self.assertEqual(Profile.objects.get(user=self.superuser).role, Role.ADMIN)

    def test_admin_post_cannot_demote_another_superuser(self):
        response = self.client.post(
            reverse("accounts:change_role", args=[self.superuser.pk]),
            {"role": Role.APPLICANT}, follow=True,
        )
        self.assertContains(response, "Superuser accounts always have the Admin role.")
        self.assertEqual(Profile.objects.get(user=self.superuser).role, Role.ADMIN)
        self.assertEqual(get_role(self.superuser), Role.ADMIN)

    def test_profile_admin_form_rejects_superuser_demotion(self):
        ProfileForm = modelform_factory(Profile, fields=["user", "role"])
        form = ProfileForm(
            {"user": str(self.superuser.pk), "role": Role.MEMBER},
            instance=Profile.objects.get(user=self.superuser),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Superusers must remain admins.", form.errors["role"])

    def test_list_displays_effective_admin_and_no_editor_for_drifted_superuser(self):
        Profile.objects.filter(user=self.superuser).update(role=Role.APPLICANT)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertContains(response, "Superuser (fixed Admin role)")
        self.assertContains(response, '<span class="badge">Admin</span>', html=True)
        self.assertNotContains(response, reverse("accounts:change_role", args=[self.superuser.pk]))

    def test_role_change_requires_post(self):
        target = make_user("target@example.com")
        response = self.client.get(reverse("accounts:change_role", args=[target.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(get_role(target), Role.APPLICANT)

    def test_role_change_requires_csrf_even_for_admin(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        target = make_user("target@example.com")
        response = client.post(reverse("accounts:change_role", args=[target.pk]), {"role": Role.ADMIN})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_role(target), Role.APPLICANT)


class ExistingAccountMigrationTests(TestCase):
    def test_backfill_is_repeatable_and_preserves_existing_roles(self):
        applicant = make_user("legacy@example.com")
        admin = User.objects.create_superuser("oldroot", "oldroot@example.com", PASSWORD)
        officer = make_user("officer@example.com", Role.OFFICER)
        Profile.objects.filter(user__in=[applicant, admin]).delete()
        # Use historical models just as Django's migration runner does.
        apps = MigrationLoader(connection).project_state([("accounts", "0001_initial")]).apps
        migration = import_module("accounts.migrations.0002_backfill_profiles")
        with connection.schema_editor() as editor:
            migration.backfill_profiles(apps, editor)
            migration.backfill_profiles(apps, editor)
        self.assertEqual(Profile.objects.get(user=applicant).role, Role.APPLICANT)
        self.assertEqual(Profile.objects.get(user=admin).role, Role.ADMIN)
        self.assertEqual(Profile.objects.get(user=officer).role, Role.OFFICER)
        self.assertEqual(Profile.objects.count(), 3)
        self.client.force_login(admin)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertContains(response, "legacy@example.com")


class RegistrationConflictTests(TestCase):
    @patch("accounts.views.RegisterForm.save", side_effect=IntegrityError("username duplicate"))
    def test_save_conflict_renders_form_instead_of_signing_in(self, save):
        response = self.client.post(reverse("accounts:register"), {
            "username": "ada", "email": "ada@example.com",
            "password": PASSWORD, "confirm_password": PASSWORD,
            "statement": "Hello",
        })
        self.assertContains(response, "Account creation could not be completed.")
        save.assert_called_once()
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(User.objects.count(), 0)
