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
    AnnouncementReadReceipt,
    Category,
)

from .test_support import AnnouncementTestDataMixin


class AnnouncementModelTests(AnnouncementTestDataMixin, TestCase):
    def test_string_representation_uses_title(self):
        announcement = self.make_announcement(title="Town hall")
        self.assertEqual(str(announcement), "Town hall")

    def test_read_percentage_is_calculated(self):
        announcement = self.make_announcement(read_count=25, target_reach=100)
        self.assertEqual(announcement.read_percentage, 25)

    def test_read_percentage_is_zero_when_target_is_zero(self):
        announcement = self.make_announcement(read_count=10, target_reach=0)
        self.assertEqual(announcement.read_percentage, 0)

    def test_read_percentage_is_capped_at_one_hundred(self):
        announcement = self.make_announcement(read_count=125, target_reach=100)
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

    def test_category_slug_must_be_unique(self):
        self.make_category(slug="updates")
        duplicate = Category(name="Other", slug="updates")
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate.save()


class AnnouncementFormTests(AnnouncementTestDataMixin, TestCase):
    def test_valid_published_announcement_form(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Valid title",
                "category": category.pk,
                "status": "published",
                "content": "Valid content",
                "target_reach": 10,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_scheduled_status_requires_schedule_time(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Scheduled",
                "category": category.pk,
                "status": "scheduled",
                "content": "Future content",
                "target_reach": 10,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("scheduled_for", form.errors)

    def test_scheduled_status_accepts_schedule_time(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Scheduled",
                "category": category.pk,
                "status": "scheduled",
                "content": "Future content",
                "scheduled_for": "2030-01-01T12:00",
                "target_reach": 10,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

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
                "target_reach": 10,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("meeting_virtual_url", form.errors)

    def test_negative_target_reach_is_rejected(self):
        category = self.make_category()
        form = AnnouncementForm(
            data={
                "title": "Invalid reach",
                "category": category.pk,
                "status": "published",
                "content": "Details",
                "target_reach": -1,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("target_reach", form.errors)

    def test_attachment_form_requires_a_name(self):
        form = AnnouncementAttachmentForm(
            files={"file": SimpleUploadedFile("notice.txt", b"notice")},
            data={},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
