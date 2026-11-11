from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils.http import urlencode
from django.utils import timezone

from accounts.models import Profile, Role
from committees.models import Committee, CommitteeMember

from announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementComment,
    AnnouncementReadReceipt,
)
from announcements.views import publish_due_announcements

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

    def test_cleared_search_query_returns_unfiltered_announcements(self):
        self.login(self.officer)
        response = self.client.get(self.url, {"q": ""})

        self.assertEqual(response.context["search_query"], "")
        self.assertContains(response, "Published notice")
        self.assertContains(response, "Draft notice")

    def test_members_can_filter_by_category(self):
        self.login(self.member)
        response = self.client.get(self.url, {"category": "events"})
        self.assertNotContains(response, "Published notice")
        self.assertNotContains(response, "Scheduled notice")

    def test_member_can_mark_announcement_read_via_read_route(self):
        self.login(self.member)
        response = self.client.post(
            reverse("announcements:mark_read", args=[self.published.pk]),
        )

        self.assertRedirects(response, reverse("announcements:list"))
        self.assertTrue(
            AnnouncementReadReceipt.objects.filter(
                user=self.member,
                announcement=self.published,
            ).exists()
        )

    def test_admin_context_contains_status_counts(self):
        self.login(self.officer)
        response = self.client.get(self.url)
        self.assertEqual(response.context["stats"]["total"], 3)
        self.assertEqual(response.context["stats"]["total_published"], 1)
        self.assertEqual(response.context["stats"]["active_drafts"], 1)
        self.assertEqual(response.context["stats"]["scheduled_queue"], 1)

    def test_member_read_url_resolves_to_read_view(self):
        self.assertEqual(
            resolve(
                reverse("announcements:mark_read", args=[self.published.pk])
            ).url_name,
            "mark_read",
        )

    def test_due_scheduled_announcement_is_published(self):
        due = self.make_announcement(
            author=self.officer,
            status="scheduled",
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(publish_due_announcements(), 1)
        due.refresh_from_db()
        self.assertEqual(due.status, "published")

    def test_all_members_audience_is_visible_without_committee_membership(self):
        self.login(self.member)
        response = self.client.get(self.url)
        self.assertContains(response, "Published notice")

    def test_committee_audience_is_limited_to_committee_members(self):
        committee = Committee.objects.create(
            name="Events",
            created_by=self.officer,
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)
        self.category.committee = committee
        self.category.save(update_fields=["committee"])
        self.published.audience = committee
        self.published.save(update_fields=["audience"])

        self.login(self.make_user("outside"))
        response = self.client.get(self.url)
        self.assertNotContains(response, "Published notice")


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
        self.assertNotIn("status", response.context["form"].fields)

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

    def test_authorized_user_can_download_attachment(self):
        officer = self.make_officer()
        announcement = self.make_announcement(author=officer)
        attachment = AnnouncementAttachment.objects.create(
            announcement=announcement,
            file=SimpleUploadedFile("notice.txt", b"notice"),
            name="Notice",
        )
        self.login(officer)
        response = self.client.get(
            reverse("announcements:attachment_download", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"notice")

    def test_officer_can_save_a_draft(self):
        officer = self.make_officer()
        self.login(officer)
        response = self.client.post(
            self.url,
            {
                "title": "Saved draft",
                "content": "Draft content",
                "save_action": "draft",
            },
        )
        announcement = Announcement.objects.get(title="Saved draft")
        self.assertRedirects(
            response,
            reverse("announcements:detail", args=[announcement.pk]),
        )
        self.assertEqual(announcement.status, "draft")

    def test_future_schedule_publishes_as_scheduled(self):
        officer = self.make_officer()
        self.login(officer)
        self.client.post(
            self.url,
            {
                "title": "Future notice",
                "content": "Future content",
                "scheduled_for": "2099-01-01T12:00",
                "save_action": "publish",
            },
        )
        announcement = Announcement.objects.get(title="Future notice")
        self.assertEqual(announcement.status, "scheduled")

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

    def test_detail_does_not_mark_announcement_read_automatically(self):
        self.login(self.member)
        first = self.client.get(self.detail_url)
        second = self.client.get(self.detail_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(AnnouncementReadReceipt.objects.filter(
            user=self.member,
            announcement=self.announcement,
        ).exists())
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.read_count, 0)

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

    def test_mark_read_can_be_reversed(self):
        self.login(self.member)
        read_url = reverse(
            "announcements:mark_read",
            args=[self.announcement.pk],
        )
        self.client.post(read_url)
        response = self.client.post(read_url, {"action": "unread"})
        self.assertRedirects(response, reverse("announcements:list"))
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.read_count, 0)
        self.assertFalse(
            AnnouncementReadReceipt.objects.filter(
                user=self.member,
                announcement=self.announcement,
            ).exists()
        )

    def test_mark_read_ajax_returns_success_for_member(self):
        self.login(self.member)
        response = self.client.post(
            reverse("announcements:mark_read", args=[self.announcement.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"is_read": True})

    def test_malformed_mark_read_id_returns_not_found(self):
        self.login(self.member)
        response = self.client.post(
            reverse("announcements:mark_read", args=["not-an-object-id"])
        )
        self.assertEqual(response.status_code, 404)

    def test_member_can_comment_when_enabled(self):
        self.announcement.comments_enabled = True
        self.announcement.save(update_fields=["comments_enabled"])
        self.login(self.member)

        response = self.client.post(
            reverse("announcements:comment_create", args=[self.announcement.pk]),
            {"content": "Thanks for the update."},
        )

        self.assertRedirects(response, self.detail_url)
        self.assertTrue(
            AnnouncementComment.objects.filter(
                announcement=self.announcement,
                author=self.member,
                content="Thanks for the update.",
            ).exists()
        )
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.comments_count, 1)

    def test_member_cannot_comment_when_disabled(self):
        self.login(self.member)
        response = self.client.post(
            reverse("announcements:comment_create", args=[self.announcement.pk]),
            {"content": "Not allowed."},
        )
        self.assertEqual(response.status_code, 403)

    def test_officer_can_mark_another_officers_announcement_read(self):
        another_officer = self.make_officer("another-officer")
        self.announcement.author = another_officer
        self.announcement.save(update_fields=["author"])
        self.login(self.officer)

        response = self.client.post(
            reverse("announcements:mark_read", args=[self.announcement.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"is_read": True})
        self.assertTrue(
            AnnouncementReadReceipt.objects.filter(
                user=self.officer,
                announcement=self.announcement,
            ).exists()
        )

    def test_author_cannot_mark_own_announcement_read(self):
        self.login(self.officer)

        response = self.client.post(
            reverse("announcements:mark_read", args=[self.announcement.pk]),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            AnnouncementReadReceipt.objects.filter(
                user=self.officer,
                announcement=self.announcement,
            ).exists()
        )
