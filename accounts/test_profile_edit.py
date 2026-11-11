from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import GoogleIdentity, Profile, Role


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="profile-member", email="old@example.com",
        )
        Profile.objects.filter(user=self.user).update(role=Role.MEMBER)
        self.url = reverse("accounts:edit_profile")
        self.profile_url = reverse("accounts:profile")
        self.data = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "New@example.com",
            "graduation_year": str(timezone.localdate().year),
        }
        self.client.force_login(self.user)

    def test_owner_can_edit_and_name_appears_in_roster(self):
        other = get_user_model().objects.create_user(username="other-member")
        self.assertContains(self.client.get(self.profile_url), self.url)
        response = self.client.post(self.url, {
            **self.data, "user": other.pk, "role": Role.ADMIN,
        })
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), "Ada Lovelace")
        self.assertEqual(self.user.email, "new@example.com")
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.graduation_year, int(self.data["graduation_year"]))
        self.assertEqual(profile.role, Role.MEMBER)
        other.refresh_from_db()
        self.assertEqual(other.first_name, "")
        self.assertContains(self.client.get(reverse("membership:roster")), "Ada Lovelace")
        detail_url = reverse("membership:member_detail", args=[profile.pk])
        self.assertContains(self.client.get(detail_url), "<h1>Ada Lovelace</h1>", html=True)

        self.assertRedirects(self.client.post(self.url, {
            **self.data, "graduation_year": "",
        }), self.profile_url)
        profile.refresh_from_db()
        self.assertIsNone(profile.graduation_year)

    def test_invalid_years_do_not_save_profile(self):
        for year in ("026", "2026.0", "1899", "9999"):
            with self.subTest(year=year):
                response = self.client.post(self.url, {**self.data, "graduation_year": year})
                self.assertIn("graduation_year", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_contact_email_cannot_match_another_email_or_legacy_username(self):
        get_user_model().objects.create_user(
            username="legacy@example.com", email="taken@example.com",
        )
        for email in ("TAKEN@example.com", "LEGACY@example.com"):
            with self.subTest(email=email):
                response = self.client.post(self.url, {**self.data, "email": email})
                self.assertFormError(
                    response.context["form"], "email", "An account with this email already exists.",
                )
        self.assertRedirects(self.client.post(self.url, {
            **self.data, "email": "OLD@example.com",
        }), self.profile_url)

    def test_google_identity_preserves_email_on_forged_post(self):
        GoogleIdentity.objects.create(user=self.user, subject="profile-google-subject")
        self.assertTrue(self.client.get(self.url).context["form"].fields["email"].disabled)
        self.assertRedirects(self.client.post(self.url, self.data), self.profile_url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertEqual(self.user.first_name, "Ada")

    def test_signed_out_post_requires_login(self):
        self.client.logout()
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
