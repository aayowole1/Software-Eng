from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from announcements.forms import AnnouncementAttachmentForm, AnnouncementForm
from announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementComment,
    AnnouncementReadReceipt,
    Category,
)
from committees.models import Committee
from accounts.models import Profile

from .test_support import AnnouncementTestDataMixin


class AnnouncementModelTests(AnnouncementTestDataMixin, TestCase):
    def test_string_representation_uses_title(self):
        announcement = self.make_announcement(title="Town hall")
        self.assertEqual(str(announcement), "Town hall")

    def test_read_percentage_is_calculated(self):
        author = self.make_user()
        announcement = self.make_announcement(author=author, read_count=25)
        for _ in range(100):
            member = self.make_user()
            Profile.objects.filter(user=member).update(role="member")
        self.assertEqual(announcement.read_percentage, 25)

    def test_read_percentage_excludes_the_poster_from_the_audience(self):
        author = self.make_user()
        Profile.objects.filter(user=author).update(role="member")
        announcement = self.make_announcement(author=author, read_count=100)
        for _ in range(100):
            member = self.make_user()
            Profile.objects.filter(user=member).update(role="member")

        self.assertEqual(announcement.audience_count, 100)
        self.assertEqual(announcement.read_percentage, 100)

    def test_read_percentage_is_zero_when_target_is_zero(self):
        announcement = self.make_announcement(read_count=10)
        self.assertEqual(announcement.read_percentage, 0)

    def test_read_percentage_treats_missing_read_count_as_zero(self):
        announcement = self.make_announcement()
        announcement.read_count = None
        self.assertEqual(announcement.read_percentage, 0)

    def test_read_percentage_is_capped_at_one_hundred(self):
        announcement = self.make_announcement(read_count=125)
        member = self.make_user()
        Profile.objects.filter(user=member).update(role="member")
        self.assertEqual(announcement.read_percentage, 100)

    def test_announcement_ordering_places_pinned_items_first(self):
        older = self.make_announcement(title="Older", published_at=timezone.now())
        pinned = self.make_announcement(
            title="Pinned",
            is_pinned=True,
            published_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(list(Announcement.objects.all()), [pinned, older])

    def test_attachment_string_representation_and_relation(self):
        announcement = self.make_announcement()
        attachment = AnnouncementAttachment.objects.create(
            announcement=announcement,
            file=SimpleUploadedFile("agenda.txt", b"agenda"),
            name="Agenda",
        )
        self.assertEqual(str(attachment), "Agenda")
        self.assertEqual(list(announcement.attachments.all()), [attachment])

    def test_duplicate_read_receipts_are_rejected(self):
        user = self.make_user()
        announcement = self.make_announcement()
        AnnouncementReadReceipt.objects.create(user=user, announcement=announcement)
        with self.assertRaises((IntegrityError, ValidationError)):
            AnnouncementReadReceipt.objects.create(
                user=user,
                announcement=announcement,
            )

    def test_comments_are_disabled_by_default(self):
        announcement = self.make_announcement()
        self.assertFalse(announcement.comments_enabled)

    def test_comment_string_representation(self):
        author = self.make_user()
        announcement = self.make_announcement()
        comment = AnnouncementComment.objects.create(
            announcement=announcement,
            author=author,
            content="A useful reply.",
        )
        self.assertEqual(str(comment), f"Comment by {author} on {announcement}")

    def test_category_slug_must_be_unique(self):
        self.make_category(slug="updates")
        duplicate = Category(name="Other", slug="updates")
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate.save()


class AnnouncementFormTests(AnnouncementTestDataMixin, TestCase):
    def test_new_form_does_not_prefill_schedule_time(self):
        form = AnnouncementForm()
        self.assertEqual(form.initial.get("scheduled_for"), "")

    def test_valid_published_announcement_form(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Valid title",
                "category": category.pk,
                "status": "published",
                "content": "Valid content",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_audience_defaults_to_all_members(self):
        form = AnnouncementForm(
            data={
                "title": "Committee notice",
                "status": "published",
                "content": "Committee content",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["audience"])

    def test_audience_lists_committees_the_user_belongs_to(self):
        user = self.make_user()
        committee = Committee.objects.create(
            name="Events",
            created_by=user,
        )
        from committees.models import CommitteeMember

        CommitteeMember.objects.create(committee=committee, user=user)
        category = self.make_category()
        form = AnnouncementForm(user=user)
        self.assertIn(committee, form.fields["audience"].queryset)
        self.assertEqual(form.fields["audience"].empty_label, "All members")

    def test_blank_schedule_is_valid_for_immediate_publication(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Scheduled",
                "category": category.pk,
                "content": "Future content",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_future_schedule_is_valid(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Scheduled",
                "category": category.pk,
                "content": "Future content",
                "scheduled_for": "2099-01-01T12:00",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_past_schedule_is_rejected(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Past schedule",
                "category": category.pk,
                "content": "Past content",
                "scheduled_for": "2000-01-01T12:00",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("scheduled_for", form.errors)

    def test_required_title_and_content_are_validated(self):
        form = AnnouncementForm(data={"status": "published"})
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertIn("content", form.errors)

    def test_invalid_virtual_meeting_url_is_rejected(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Meeting",
                "category": category.pk,
                "status": "published",
                "content": "Details",
                "meeting_virtual_url": "not-a-url",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("meeting_virtual_url", form.errors)

    def test_attachment_form_requires_a_name(self):
        form = AnnouncementAttachmentForm(
            files={"file": SimpleUploadedFile("notice.txt", b"notice")},
            data={},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
