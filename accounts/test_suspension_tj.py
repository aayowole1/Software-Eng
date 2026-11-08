
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile, Role, get_role
from accounts.testing import make_user
from membership.models import ApplicationStatus, MembershipApplication

#These tests cover the main administrative restrictions and membership safeguards.

class SuspensionIntegrationTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.admin = User.objects.create_superuser(
            username="tj_admin",
            email="tj_admin@example.com",
            password="TestingPassword123!"
        )

        self.member = make_user(
            "tj_member@example.com",
            Role.MEMBER
        )

        self.applicant = make_user(
            "tj_applicant@example.com"
        )

    def suspension_url(self, user):
        return reverse(
            "accounts:change_suspension",
            args=[user.pk]
        )

    def test_admin_can_suspend_member(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.suspension_url(self.member),
            {"action": "suspend"}
        )

        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db()
        profile = Profile.objects.get(user=self.member)

        self.assertFalse(self.member.is_active)
        self.assertTrue(profile.is_suspended)

    def test_member_cannot_suspend_another_user(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.suspension_url(self.applicant),
            {"action": "suspend"}
        )

        self.assertEqual(response.status_code, 403)

        self.applicant.refresh_from_db()
        self.assertFalse(
            self.applicant.profile.is_suspended
        )

    def test_suspended_applicant_cannot_be_approved(self):
        application = MembershipApplication.objects.create(
            user=self.applicant,
            statement="I would like to join."
        )

        self.applicant.profile.is_suspended = True
        self.applicant.profile.save(
            update_fields=["is_suspended"]
        )

        with self.assertRaises(ValueError):
            application.review(
                reviewer=self.admin,
                approve=True
            )

        application.refresh_from_db()

        self.assertEqual(
            application.status,
            ApplicationStatus.PENDING
        )
        self.assertEqual(
            get_role(self.applicant),
            Role.APPLICANT
        )

    def test_pending_applicant_not_activated_by_reinstatement(self):
        self.applicant.is_active = False
        self.applicant.save(update_fields=["is_active"])

        self.applicant.profile.is_suspended = True
        self.applicant.profile.save(
            update_fields=["is_suspended"]
        )

        self.client.force_login(self.admin)

        response = self.client.post(
            self.suspension_url(self.applicant),
            {"action": "reinstate"}
        )

        self.assertEqual(response.status_code, 302)

        self.applicant.refresh_from_db()
        self.applicant.profile.refresh_from_db()

        self.assertFalse(self.applicant.is_active)
        self.assertFalse(
            self.applicant.profile.is_suspended
        )
