"""New meeting creation recovery without live provider requests."""

from unittest.mock import patch

from django.db import OperationalError
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from meetings.ai import MeetingSummary
from meetings.models import ActionItem, MeetingDraft


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MeetingCreationRecoveryTests(TestCase):
    def setUp(self):
        self.officer = make_user("meeting-creator@example.com", Role.OFFICER)
        self.existing = MeetingDraft.objects.create(
            title="Existing meeting", notes="Retain original notes", summary="Original summary",
            created_by=self.officer,
        )
        self.existing_item = ActionItem.objects.create(draft=self.existing, description="Retain existing action")
        self.client.force_login(self.officer)
        self.payload = {"title": "New synthetic meeting", "notes": "New synthetic transcript"}
        self.summary = MeetingSummary("Synthetic summary", ["Action: first", "Action: second"])

    def submit(self):
        return self.client.post(reverse("meetings:create"), self.payload)

    def assert_existing_unchanged(self):
        self.existing.refresh_from_db()
        self.existing_item.refresh_from_db()
        self.assertEqual(self.existing.notes, "Retain original notes")
        self.assertEqual(self.existing.summary, "Original summary")
        self.assertEqual(self.existing_item.description, "Retain existing action")

    def assert_no_new_attempt(self):
        self.assertEqual(MeetingDraft.objects.count(), 1)
        self.assertEqual(ActionItem.objects.count(), 1)
        self.assert_existing_unchanged()

    def test_provider_failure_retains_form_and_creates_no_draft(self):
        with patch("meetings.models.summarize_meeting", side_effect=RuntimeError("private provider details")):
            response = self.submit()
        self.assertContains(response, "No new draft was retained", status_code=503)
        self.assertNotContains(response, "private provider details", status_code=503)
        self.assertEqual(response.context["form"]["title"].value(), self.payload["title"])
        self.assertEqual(response.context["form"]["notes"].value(), self.payload["notes"])
        self.assert_no_new_attempt()

    def test_retry_after_provider_failure_creates_exactly_one_complete_draft(self):
        with patch("meetings.models.summarize_meeting", side_effect=[RuntimeError("Synthetic failure"), self.summary]):
            self.assertEqual(self.submit().status_code, 503)
            response = self.submit()
        created = MeetingDraft.objects.get(title=self.payload["title"])
        self.assertRedirects(response, reverse("meetings:detail", args=[created.pk]))
        self.assertEqual(MeetingDraft.objects.count(), 2)
        self.assertEqual(list(created.action_items.values_list("description", flat=True)), self.summary.action_items)
        # A browser refresh follows GET rather than resubmitting the creation POST.
        self.assertEqual(self.client.get(response.url).status_code, 200)
        self.assertEqual(MeetingDraft.objects.count(), 2)
        self.assert_existing_unchanged()

    def test_failed_initial_database_write_does_not_change_existing_drafts(self):
        with (
            patch("meetings.models.summarize_meeting", return_value=self.summary),
            patch.object(MeetingDraft, "save", side_effect=OperationalError("private database details")),
        ):
            response = self.submit()
        self.assertContains(response, "No new draft was retained", status_code=503)
        self.assert_no_new_attempt()

    def test_failure_after_insert_is_cleaned_using_reserved_attempt_id(self):
        original_save = MeetingDraft.save

        def save_then_fail(draft, *args, **kwargs):
            original_save(draft, *args, **kwargs)
            raise OperationalError("Synthetic failure after insert")

        with (
            patch("meetings.models.summarize_meeting", return_value=self.summary),
            patch.object(MeetingDraft, "save", save_then_fail),
        ):
            response = self.submit()
        self.assertContains(response, "No new draft was retained", status_code=503)
        self.assert_no_new_attempt()

    def test_reserved_id_collision_cannot_update_or_remove_an_existing_draft(self):
        with (
            patch("meetings.models.summarize_meeting", return_value=self.summary),
            patch("meetings.views.ObjectId", return_value=self.existing.pk),
        ):
            response = self.submit()
        self.assertContains(response, "No new draft was retained", status_code=503)
        self.assert_no_new_attempt()

    def test_partial_action_writes_are_removed_and_retry_creates_one_draft(self):
        original_create = ActionItem.objects.create

        def create_then_fail(**fields):
            item = original_create(**fields)
            if fields.get("position") == 1:
                raise OperationalError("Synthetic failure after second action insert")
            return item

        with (
            patch("meetings.models.summarize_meeting", return_value=self.summary),
            patch("meetings.models.ActionItem.objects.create", side_effect=create_then_fail),
        ):
            response = self.submit()
        self.assertContains(response, "No new draft was retained", status_code=503)
        self.assert_no_new_attempt()
        with patch("meetings.models.summarize_meeting", return_value=self.summary):
            response = self.submit()
        created = MeetingDraft.objects.get(title=self.payload["title"])
        self.assertRedirects(response, reverse("meetings:detail", args=[created.pk]))
        self.assertEqual(created.action_items.count(), 2)
        self.assertEqual(MeetingDraft.objects.count(), 2)
        self.assert_existing_unchanged()

    def test_cleanup_failure_reports_possible_partial_draft_without_private_details(self):
        original_create = ActionItem.objects.create
        original_delete = QuerySet.delete

        def create_then_fail(**fields):
            item = original_create(**fields)
            raise OperationalError("private action details")

        def fail_draft_cleanup(queryset):
            if queryset.model is MeetingDraft:
                raise OperationalError("private connection credentials")
            return original_delete(queryset)

        with (
            patch("meetings.models.summarize_meeting", return_value=self.summary),
            patch("meetings.models.ActionItem.objects.create", side_effect=create_then_fail),
            patch.object(QuerySet, "delete", fail_draft_cleanup),
            self.assertLogs("meetings.views", level="ERROR") as logs,
        ):
            response = self.submit()
        self.assertContains(response, "A partial draft may remain", status_code=503)
        self.assertNotContains(response, "No new draft was retained", status_code=503)
        self.assertNotContains(response, "private", status_code=503)
        self.assertIn("operator recovery is required", logs.output[0])
        self.assertNotIn("private", " ".join(logs.output))
        self.assertEqual(MeetingDraft.objects.count(), 2)
        self.assertEqual(ActionItem.objects.count(), 2)
        self.assert_existing_unchanged()
