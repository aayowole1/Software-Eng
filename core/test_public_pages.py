from django.test import TestCase
from django.urls import reverse


class PublicInformationPageTests(TestCase):
    def test_public_pages_render_with_navigation(self):
        pages = ("about", "accessibility", "bylaws", "privacy")
        for page in pages:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"core:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"<h1>{response.context['page']['title']}</h1>", html=True)
                self.assertNotContains(response, 'aria-label="Organization information"')

    def test_footer_links_are_real_routes(self):
        response = self.client.get(reverse("core:home"))
        for page in ("about", "accessibility", "bylaws", "privacy"):
            self.assertContains(response, reverse(f"core:{page}"))
