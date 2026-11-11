"""SCRUM-98: About section and onboarding content on the signed-out dashboard."""

import os
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from membership.models import REAPPLY_WAIT
from orgflow_project.env import env_list, env_text


class AboutSectionTests(TestCase):
    """SCRUM-98: About section on the signed-out dashboard."""

    def _get(self):
        return self.client.get(reverse("core:dashboard"))

    @override_settings(ORG_NAME="Test Org")
    def test_signed_out_sees_org_name(self):
        self.assertContains(self._get(), "Test Org")

    @override_settings(ORG_MISSION="Empowering students everywhere")
    def test_signed_out_sees_org_mission(self):
        self.assertContains(self._get(), "Empowering students everywhere")

    @override_settings(ORG_BENEFITS=["Networking", "Leadership"])
    def test_signed_out_sees_org_benefits(self):
        response = self._get()
        self.assertContains(response, "Networking")
        self.assertContains(response, "Leadership")

    @override_settings(ORG_CONTACT_EMAIL="officers@example.com")
    def test_signed_out_sees_contact_email_as_mailto(self):
        response = self._get()
        self.assertContains(response, "mailto:officers@example.com")
        self.assertContains(response, "officers@example.com")

    @override_settings(ORG_CONTACT_EMAIL="")
    def test_contact_fallback_when_email_empty(self):
        response = self._get()
        self.assertContains(response, "Contact an officer after you sign in")
        self.assertNotContains(response, "mailto:")

    def test_waiting_period_follows_reapply_wait(self):
        days = REAPPLY_WAIT.days
        response = self._get()
        self.assertContains(response, f"{days} day")

    def test_signed_out_member_only_content_hidden(self):
        response = self._get()
        self.assertNotContains(response, "Recent announcements")
        self.assertNotContains(response, "My tasks")
        self.assertNotContains(response, "Upcoming events")
        self.assertNotContains(response, "My committees")

    def test_signed_in_about_section_not_shown(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "about-section")

    @override_settings(ORG_NAME="Visible Org", ORG_MISSION="Our mission")
    def test_signed_in_does_not_see_org_name_or_mission(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "about-section")
        # The org name may appear in the page title/navigation, so we check
        # specifically the About section content doesn't bleed through
        self.assertNotContains(response, "Our mission")


class EnvHelperTests(SimpleTestCase):
    """Blank environment values fall back to the placeholder (copied .env.example)."""

    def test_unset_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(env_text("ORG_NAME", "Placeholder"), "Placeholder")

    def test_blank_uses_default(self):
        for blank in ("", "   "):
            with self.subTest(value=repr(blank)), patch.dict(os.environ, {"ORG_NAME": blank}):
                self.assertEqual(env_text("ORG_NAME", "Placeholder"), "Placeholder")

    def test_value_is_trimmed_and_used(self):
        with patch.dict(os.environ, {"ORG_NAME": "  Campus Builders  "}):
            self.assertEqual(env_text("ORG_NAME", "Placeholder"), "Campus Builders")

    def test_list_splits_and_drops_blank_items(self):
        with patch.dict(os.environ, {"ORG_BENEFITS": " Networking | |Leadership "}):
            self.assertEqual(env_list("ORG_BENEFITS", "A|B"), ["Networking", "Leadership"])

    def test_blank_list_uses_default(self):
        for blank in ("", "  ", " | | "):
            with self.subTest(value=repr(blank)), patch.dict(os.environ, {"ORG_BENEFITS": blank}):
                self.assertEqual(env_list("ORG_BENEFITS", "A|B"), ["A", "B"])

    def test_blank_contact_email_stays_empty_for_the_fallback_text(self):
        with patch.dict(os.environ, {"ORG_CONTACT_EMAIL": ""}):
            self.assertEqual(env_text("ORG_CONTACT_EMAIL", ""), "")
