"""SCRUM-50: in-app Help page with FAQ and role-based guides, mirrored in docs/."""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from accounts.models import Role
from accounts.testing import make_user

from core.help_content import FAQ, GUIDES, render_markdown
from core.management.commands.export_help_docs import DOC_PATH

HELP_URL = reverse("core:help")


def titles(role):
    return [guide["title"] for guide in GUIDES if guide["audience"] == role]


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HelpPageTests(TestCase):
    def page(self, role=Role.MEMBER):
        self.client.force_login(make_user(f"help-{role}@example.com", role))
        response = self.client.get(HELP_URL)
        self.assertEqual(response.status_code, 200)
        return response

    def test_signed_out_visitors_are_sent_to_sign_in(self):
        response = self.client.get(HELP_URL)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={HELP_URL}', fetch_redirect_response=False)

    def test_members_see_member_guides_and_faq_only(self):
        response = self.page(Role.MEMBER)
        for title in titles(Role.MEMBER):
            self.assertContains(response, title)
        for title in titles(Role.OFFICER) + titles(Role.ADMIN):
            self.assertNotContains(response, title)
        self.assertNotContains(response, "Officer guides")
        self.assertNotContains(response, "Admin guides")
        for question, answer in FAQ:
            self.assertContains(response, escape(question))

    def test_applicants_see_member_guides(self):
        response = self.page(Role.APPLICANT)
        self.assertContains(response, "Sign up and apply to join")
        self.assertNotContains(response, "Officer guides")

    def test_officers_see_officer_guides_but_not_admin_guides(self):
        response = self.page(Role.OFFICER)
        for title in titles(Role.MEMBER) + titles(Role.OFFICER):
            self.assertContains(response, title)
        for title in titles(Role.ADMIN):
            self.assertNotContains(response, title)

    def test_admins_see_every_guide(self):
        response = self.page(Role.ADMIN)
        for guide in GUIDES:
            self.assertContains(response, guide["title"])

    def test_bold_markers_render_as_strong_text_and_stay_escaped(self):
        response = self.page(Role.MEMBER)
        self.assertContains(response, "<strong>Edit profile</strong>", html=False)
        self.assertNotContains(response, "**Edit profile**")

    def test_sidebar_links_to_help_when_signed_in(self):
        self.client.force_login(make_user("help-sidebar@example.com", Role.APPLICANT))
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, f'href="{HELP_URL}"')

    def test_sidebar_has_no_help_link_when_signed_out(self):
        self.assertNotContains(self.client.get(reverse("accounts:login")), f'href="{HELP_URL}"')


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FeatureNoteTests(TestCase):
    """Notes for features in open PRs switch on automatically once the feature exists."""

    def officer_page(self):
        self.client.force_login(make_user("help-notes@example.com", Role.OFFICER))
        return self.client.get(HELP_URL)

    def test_notes_show_coming_soon_until_the_feature_exists(self):
        with patch.dict("core.help_content.FEATURE_CHECKS", {"ai_fallback": lambda: False, "recording_upload": lambda: False}):
            response = self.officer_page()
        self.assertContains(response, "your notes will still be saved")
        self.assertContains(response, "be able to upload a recording")
        self.assertNotContains(response, "<strong>Manual summary</strong>", html=False)

    def test_notes_show_the_finished_steps_once_the_feature_exists(self):
        with patch.dict("core.help_content.FEATURE_CHECKS", {"ai_fallback": lambda: True, "recording_upload": lambda: True}):
            response = self.officer_page()
        self.assertContains(response, "<strong>Manual summary</strong>", html=False)
        self.assertContains(response, "<strong>Upload a recording</strong>", html=False)
        self.assertNotContains(response, "your notes will still be saved")

    def test_each_note_switches_independently(self):
        with patch.dict("core.help_content.FEATURE_CHECKS", {"ai_fallback": lambda: True, "recording_upload": lambda: False}):
            response = self.officer_page()
        self.assertContains(response, "<strong>Manual summary</strong>", html=False)
        self.assertContains(response, "be able to upload a recording")

    def test_feature_checks_match_the_current_code(self):
        from core.help_content import FEATURE_CHECKS

        for name, check in FEATURE_CHECKS.items():
            with self.subTest(feature=name):
                self.assertIsInstance(check(), bool)


class HelpDocsTests(SimpleTestCase):
    def test_docs_copy_matches_the_in_app_guides(self):
        self.assertEqual(
            DOC_PATH.read_text(encoding="utf-8"), render_markdown(),
            "docs/user-and-admin-guide.md is out of date. Run: python manage.py export_help_docs",
        )

    def test_docs_include_every_guide_and_question(self):
        text = render_markdown()
        for guide in GUIDES:
            self.assertIn(guide["title"], text)
        for question, _ in FAQ:
            self.assertIn(question, text)

    def test_docs_always_use_the_finished_text(self):
        text = render_markdown()
        self.assertIn("**Manual summary**", text)
        self.assertIn("**Upload a recording**", text)
        self.assertNotIn("will still be saved", text)

    def test_guides_have_unique_slugs(self):
        slugs = [guide["slug"] for guide in GUIDES]
        self.assertEqual(len(slugs), len(set(slugs)))
