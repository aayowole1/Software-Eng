from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from urllib.parse import parse_qs

from accounts.models import Profile, Role


class RosterPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.users = User.objects.bulk_create([
            User(username=f"member-{i:03}", email=f"person-{i:03}@example.com", is_active=True)
            for i in range(61)
        ])
        Profile.objects.bulk_create([
            Profile(user=user, role=Role.MEMBER if i % 2 == 0 else Role.OFFICER)
            for i, user in enumerate(cls.users)
        ])
        cls.applicant = User.objects.create_user(username="applicant", email="applicant@example.com")
        cls.url = reverse("membership:roster")

    def setUp(self):
        self.client.force_login(self.users[0])

    def test_first_page_is_bounded_and_contains_navigation(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["members"]), 25)
        self.assertEqual(response.context["page_obj"].paginator.count, 61)
        self.assertContains(response, "Page 1 of 3")
        self.assertNotContains(response, "applicant@example.com")

    def test_all_pages_have_no_duplicates_or_omitted_members(self):
        found = []
        for number in (1, 2, 3):
            response = self.client.get(self.url, {"page": number})
            found.extend(profile.user_id for profile in response.context["members"])
        self.assertEqual(len(found), 61)
        self.assertEqual(set(found), {user.pk for user in self.users})

    def test_filters_are_applied_before_pagination_and_preserved_in_links(self):
        response = self.client.get(self.url, {"q": "person", "role": "member", "page": 2})
        self.assertEqual(response.context["page_obj"].paginator.count, 31)
        self.assertEqual(len(response.context["members"]), 6)
        self.assertTrue(all(profile.role == Role.MEMBER for profile in response.context["members"]))
        self.assertEqual(parse_qs(response.context["query_string"]), {"q": ["person"], "role": ["member"]})
        self.assertContains(response, "q=person&amp;role=member&amp;page=1")

    def test_invalid_page_and_empty_results_remain_usable(self):
        response = self.client.get(self.url, {"page": "invalid"})
        self.assertEqual(response.context["page_obj"].number, 1)
        response = self.client.get(self.url, {"page": 9999})
        self.assertEqual(response.context["page_obj"].number, 3)
        response = self.client.get(self.url, {"q": "not-present"})
        self.assertEqual(len(response.context["members"]), 0)
        self.assertContains(response, "No members found")

    def test_applicant_is_still_denied(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.url).status_code, 403)
