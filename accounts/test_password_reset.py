import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Role
from .testing import PASSWORD, make_user

User = get_user_model()
NEW_PASSWORD = "brand-new-secret-77"


class PasswordResetTests(TestCase):
    def request_reset(self, email):
        return self.client.post(reverse("accounts:password_reset"), {"email": email})

    def reset_link(self):
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r"https?://[^/]+(/accounts/reset/\S+/)", mail.outbox[0].body).group(1)

    def test_login_page_links_to_reset(self):
        self.assertContains(self.client.get(reverse("accounts:login")), reverse("accounts:password_reset"))

    def test_full_reset_flow_lets_user_sign_in_with_new_password(self):
        user = make_user("ada@example.com", Role.MEMBER)
        response = self.request_reset("ADA@example.com")
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        link = self.reset_link()
        self.assertIn("ada@example.com", mail.outbox[0].to)

        # Django swaps the token for a session value, then shows the form.
        form_page = self.client.get(link, follow=True)
        self.assertContains(form_page, "Set a new password")
        response = self.client.post(
            form_page.redirect_chain[-1][0],
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertFalse(user.check_password(PASSWORD))

    def test_reset_link_only_works_once(self):
        make_user("ada@example.com", Role.MEMBER)
        self.request_reset("ada@example.com")
        link = self.reset_link()
        form_page = self.client.get(link, follow=True)
        self.client.post(form_page.redirect_chain[-1][0], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.client.logout()
        self.assertContains(self.client.get(link, follow=True), "invalid or has already been used")

    def test_unknown_email_gets_same_response_and_no_email(self):
        response = self.request_reset("nobody@example.com")
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_google_only_account_gets_no_email(self):
        User.objects.create_user("google_abc", "g@example.com", password=None)
        self.request_reset("g@example.com")
        self.assertEqual(len(mail.outbox), 0)

    def test_account_waiting_for_approval_gets_no_email(self):
        User.objects.create_user("pending", "p@example.com", PASSWORD, is_active=False)
        self.request_reset("p@example.com")
        self.assertEqual(len(mail.outbox), 0)
