from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlencode

from accounts.models import Profile, Role

from announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementReadReceipt,
)

from .test_support import AnnouncementTestDataMixin


User = get_user_model()


class AnnouncementListViewTests(AnnouncementTestDataMixin, TestCase):
    url = reverse("announcements:list")

    def setUp(self):
        self.member = self.make_user()
        self.officer = self.make_officer()
        self.category = self.make_category()
        self.other_category = self.make_category("Events", "events")
        self.published = self.make_announcement(
            author=self.officer,
            title="Published notice",
            category=self.category,
            status="published",
        )
        self.draft = self.make_announcement(
            author=self.officer,
            title="Draft notice",
            category=self.category,
            status="draft",
        )
        self.scheduled = self.make_announcement(
            author=self.officer,
            title="Scheduled notice",
            category=self.other_category,
            status="scheduled",
        )

    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.url}",
        )

    def test_members_only_see_published_announcements(self):
        self.login(self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published notice")
        self.assertNotContains(response, "Draft notice")
        self.assertNotContains(response, "Scheduled notice")

    def test_officers_can_filter_by_status(self):
        self.login(self.officer)
        response = self.client.get(self.url, {"status": "draft"})
        self.assertContains(response, "Draft notice")
        self.assertNotContains(response, "Published notice")

    def test_officers_can_search_title_and_content(self):
        self.published.content = "Important budget meeting"
        self.published.save(update_fields=["content"])
        self.login(self.officer)
        response = self.client.get(self.url, {"q": "budget"})
        self.assertContains(response, "Published notice")
        self.assertNotContains(response, "Draft notice")

    def test_members_can_filter_by_category(self):
        self.login(self.member)
        response = self.client.get(self.url, {"category": "events"})
        self.assertNotContains(response, "Published notice")
        self.assertNotContains(response, "Scheduled notice")

    def test_admin_context_contains_status_counts(self):
        self.login(self.officer)
        response = self.client.get(self.url)
        self.assertEqual(response.context["stats"]["total_published"], 1)
        self.assertEqual(response.context["stats"]["active_drafts"], 1)
        self.assertEqual(response.context["stats"]["scheduled_queue"], 1)


class AnnouncementCreateViewTests(AnnouncementTestDataMixin, TestCase):
    url = reverse("announcements:create")

    def test_anonymous_users_are_redirected(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.url}",
        )

    def test_members_cannot_create_announcements(self):
        self.login(self.make_user())
        response = self.client.get(self.url)
        expected_url = (
            f"{reverse('announcements:list')}?"
            f"{urlencode({'next': self.url})}"
        )
        self.assertRedirects(response, expected_url, msg_prefix=str(response))

    def test_get_prefills_published_defaults_for_officer(self):
        self.login(self.make_officer())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["status"], "published")
        self.assertEqual(response.context["form"].initial["target_reach"], 165)

    def test_officer_can_create_with_attachment(self):
        officer = self.make_officer()
        category = self.make_category()
        self.login(officer)
        upload = SimpleUploadedFile("agenda.txt", b"agenda")
        response = self.client.post(
            self.url,
            {
                "title": "Created notice",
                "category": category.pk,
                "status": "published",
                "content": "Created content",
                "target_reach": 20,
                "attachments": upload,
            },
        )
        announcement = Announcement.objects.get(title="Created notice")
        self.assertRedirects(
            response,
            reverse("announcements:detail", args=[announcement.pk]),
        )
        self.assertEqual(announcement.author, officer)
        self.assertEqual(announcement.author_role, "Officer")
        self.assertEqual(announcement.attachments.count(), 1)

    def test_create_uses_profile_role_display_when_available(self):
        officer = self.make_officer("profile-officer")
        Profile.objects.filter(user=officer).update(role=Role.ADMIN)
        category = self.make_category()
        self.login(officer)

        self.client.post(
            self.url,
            {
                "title": "Role-labelled notice",
                "category": category.pk,
                "status": "published",
                "content": "Created content",
                "target_reach": 20,
            },
        )

        announcement = Announcement.objects.get(title="Role-labelled notice")
        self.assertEqual(announcement.author_role, "Admin")

    def test_create_uses_system_administrator_for_superuser(self):
        admin = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="test-password",
        )
        category = self.make_category()
        self.login(admin)

        self.client.post(
            self.url,
            {
                "title": "System notice",
                "category": category.pk,
                "status": "published",
                "content": "Created content",
                "target_reach": 20,
            },
        )

        announcement = Announcement.objects.get(title="System notice")
        self.assertEqual(announcement.author_role, "System Administrator")

    def test_invalid_post_does_not_create_announcement(self):
        self.login(self.make_officer())
        response = self.client.post(
            self.url,
            {"title": "", "content": "", "status": "published"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Announcement.objects.exists())
        self.assertContains(response, "Please correct")


class AnnouncementDetailAndEditTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.member = self.make_user()
        self.officer = self.make_officer()
        self.announcement = self.make_announcement(author=self.officer)
        self.detail_url = reverse(
            "announcements:detail",
            args=[self.announcement.pk],
        )
        self.edit_url = reverse(
            "announcements:edit",
            args=[self.announcement.pk],
        )

    def test_detail_records_only_one_read_receipt(self):
        self.login(self.member)
        first = self.client.get(self.detail_url)
        second = self.client.get(self.detail_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            AnnouncementReadReceipt.objects.filter(
                user=self.member,
                announcement=self.announcement,
            ).count(),
            1,
        )
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.read_count, 1)

    def test_members_cannot_view_unpublished_details(self):
        self.announcement.status = "draft"
        self.announcement.save(update_fields=["status"])
        self.login(self.member)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_officers_can_view_unpublished_details(self):
        self.announcement.status = "draft"
        self.announcement.save(update_fields=["status"])
        self.login(self.officer)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)

    def test_non_author_officer_cannot_edit(self):
        another_officer = self.make_officer("another-officer")
        self.login(another_officer)
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 403)

    def test_author_can_edit_and_remove_attachment(self):
        attachment = AnnouncementAttachment.objects.create(
            announcement=self.announcement,
            file=SimpleUploadedFile("old.txt", b"old"),
            name="Old file",
        )
        self.login(self.officer)
        category = self.announcement.category
        response = self.client.post(
            self.edit_url,
            {
                "title": "Updated title",
                "category": category.pk,
                "status": "published",
                "content": "Updated content",
                "target_reach": 20,
                "delete_attachments": [attachment.pk],
            },
        )
        self.assertRedirects(
            response,
            reverse("announcements:detail", args=[self.announcement.pk]),
        )
        self.assertFalse(
            AnnouncementAttachment.objects.filter(pk=attachment.pk).exists()
        )
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.title, "Updated title")

    def test_mark_read_is_idempotent_and_redirects_to_list(self):
        self.login(self.member)
        read_url = reverse(
            "announcements:mark_read",
            args=[self.announcement.pk],
        )
        first = self.client.post(read_url)
        second = self.client.post(read_url)
        self.assertRedirects(first, reverse("announcements:list"))
        self.assertRedirects(second, reverse("announcements:list"))
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.read_count, 1)
