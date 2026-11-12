from django.test import TestCase
from django.urls import reverse

from .models import Profile, Role, get_role
from .testing import make_user


class UserListTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.client.force_login(self.admin)

    def test_users_are_ordered_by_privilege_and_can_be_filtered(self):
        member = make_user("member@example.com", Role.MEMBER)
        officer = make_user("officer@example.com", Role.OFFICER)
        response = self.client.get(reverse("accounts:user_list"), {"role": Role.MEMBER})

        self.assertEqual(list(response.context["profiles"]), [Profile.objects.get(user=member)])
        self.assertContains(response, "member@example.com")
        self.assertNotContains(response, "officer@example.com")

        response = self.client.get(reverse("accounts:user_list"))
        body = response.content.decode()
        self.assertLess(body.index("officer@example.com"), body.index("member@example.com"))

    def test_load_more_reveals_next_fifty_users(self):
        for index in range(51):
            make_user(f"user-{index}@example.com")

        first_page = self.client.get(reverse("accounts:user_list"))
        expanded = self.client.get(reverse("accounts:user_list"), {"load_more": 100})

        self.assertEqual(len(first_page.context["profiles"]), 50)
        self.assertEqual(len(expanded.context["profiles"]), 52)
        self.assertTrue(first_page.context["has_more"])
        self.assertFalse(expanded.context["has_more"])

    def test_bulk_role_save_updates_all_selected_users(self):
        member = make_user("member@example.com")
        officer = make_user("officer@example.com")

        response = self.client.post(
            reverse("accounts:bulk_change_roles"),
            {
                f"role_{member.pk}": Role.OFFICER,
                f"version_{member.pk}": "0",
                f"role_{officer.pk}": Role.MEMBER,
                f"version_{officer.pk}": "0",
            },
        )

        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertEqual(get_role(member), Role.OFFICER)
        self.assertEqual(get_role(officer), Role.MEMBER)
