"""Approval intent, partial action updates and retry-safe task conversion."""

from unittest.mock import patch

from bson import ObjectId
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.db.models import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from meetings.models import ActionItem, DraftStatus, MeetingDraft
from tasks.models import Task
from tasks.services import import_action_items


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MeetingReviewRecoveryTests(TestCase):
    def setUp(self):
        self.officer = make_user("intent-reviewer@example.com", Role.OFFICER)
        self.other = make_user("recovery-officer@example.com", Role.OFFICER)
        self.member = make_user("review-member@example.com", Role.MEMBER)
        self.draft = MeetingDraft.objects.create(
            title="Synthetic review", notes="Synthetic notes", created_by=self.officer,
        )
        self.item = ActionItem.objects.create(draft=self.draft, description="Original accepted action", accepted=True)

    def intent(self):
        return [
            {"id": str(self.item.pk), "description": "Reviewed existing action", "accepted": True},
            {"id": str(ObjectId()), "description": "Reviewed new action", "accepted": True},
            {"id": str(ObjectId()), "description": "Rejected new action", "accepted": False},
        ]

    def interrupt_review_after_new_item_insert(self, intent):
        original_save = ActionItem.save

        def save_then_interrupt(item, *args, **kwargs):
            original_save(item, *args, **kwargs)
            if str(item.pk) == intent[1]["id"]:
                raise OperationalError("Synthetic failure after action insert")

        with patch.object(ActionItem, "save", save_then_interrupt):
            with self.assertRaises(OperationalError):
                self.draft.review(self.officer, DraftStatus.APPROVED, "Original reviewer note", item_intent=intent)
        self.draft.refresh_from_db()

    def test_stale_http_loser_cannot_edit_or_add_actions_that_tasks_consume(self):
        stale = MeetingDraft.objects.get(pk=self.draft.pk)
        self.draft.review(self.officer, DraftStatus.APPROVED, "Winning decision")
        expected_metadata = (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note)
        self.client.force_login(self.other)
        with patch("meetings.views.get_object_or_404", return_value=stale):
            response = self.client.post(reverse("meetings:review", args=[self.draft.pk]), {
                "decision": DraftStatus.REJECTED, "note": "Losing decision",
                "new_items": "Unapproved new action",
                f"item-{self.item.pk}-description": "Unapproved changed action",
                f"item-{self.item.pk}-accepted": "on",
            })
        self.assertRedirects(response, reverse("meetings:detail", args=[self.draft.pk]))
        self.item.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(self.item.description, "Original accepted action")
        self.assertEqual(self.draft.action_items.count(), 1)
        self.assertEqual(
            (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note), expected_metadata,
        )
        result = import_action_items(self.officer, self.draft)
        self.assertEqual([task.title for task in result["created"]], ["Original accepted action"])

    def test_partial_review_blocks_all_import_paths_and_retries_original_intent(self):
        intent = self.intent()
        self.interrupt_review_after_new_item_insert(intent)
        expected_metadata = (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note)
        self.assertTrue(self.draft.review_update_pending)
        self.assertEqual(self.draft.status, DraftStatus.APPROVED)
        self.assertEqual(self.draft.action_items.count(), 2)
        with self.assertRaisesMessage(ValidationError, "Finish the recorded meeting review"):
            import_action_items(self.officer, self.draft)

        self.client.force_login(self.other)
        detail = self.client.get(reverse("meetings:detail", args=[self.draft.pk]))
        import_url = reverse("tasks:import_draft", args=[self.draft.pk])
        self.assertContains(detail, "Finish review")
        self.assertNotContains(detail, import_url)
        self.assertContains(self.client.get(import_url), "Finish the recorded meeting review", status_code=400)
        self.assertEqual(self.client.post(import_url, {"priority": "medium"}).status_code, 400)
        self.assertFalse(Task.objects.exists())

        finish_url = reverse("meetings:finish_review", args=[self.draft.pk])
        response = self.client.post(finish_url, {"decision": DraftStatus.REJECTED, "note": "Ignored replacement"})
        self.assertRedirects(response, reverse("meetings:detail", args=[self.draft.pk]))
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.review_update_pending)
        self.assertEqual(
            (self.draft.reviewed_by_id, self.draft.reviewed_at, self.draft.review_note), expected_metadata,
        )
        self.assertEqual(self.draft.review_item_intent, [{**item, "position": index} for index, item in enumerate(intent)])
        self.assertEqual(self.draft.action_items.count(), 3)
        self.assertEqual(self.client.post(finish_url).status_code, 302)
        self.assertEqual(self.draft.action_items.count(), 3)
        first = import_action_items(self.other, self.draft)
        second = import_action_items(self.other, self.draft)
        self.assertEqual({task.title for task in first["created"]}, {"Reviewed existing action", "Reviewed new action"})
        self.assertEqual(len(second["created"]), 0)
        self.assertEqual(len(second["existing"]), 2)
        self.assertEqual(Task.objects.count(), 2)

    def test_failed_final_marker_write_keeps_import_blocked_until_retry(self):
        original_update = QuerySet.update

        def interrupt_completion(queryset, **fields):
            if queryset.model is MeetingDraft and fields == {"review_update_pending": False}:
                raise OperationalError("Synthetic final marker failure")
            return original_update(queryset, **fields)

        with patch.object(QuerySet, "update", interrupt_completion):
            with self.assertRaises(OperationalError):
                self.draft.review(self.officer, DraftStatus.APPROVED, item_intent=self.intent())
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.review_update_pending)
        self.assertEqual(self.draft.action_items.count(), 3)
        with self.assertRaises(ValidationError):
            import_action_items(self.officer, self.draft)
        self.draft.complete_review_update()
        self.assertFalse(self.draft.review_update_pending)
        self.assertEqual(self.draft.action_items.count(), 3)

    def test_finish_review_is_post_only_officer_only_and_csrf_protected(self):
        self.interrupt_review_after_new_item_insert(self.intent())
        url = reverse("meetings:finish_review", args=[self.draft.pk])
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(url).status_code, 403)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.review_update_pending)

    def test_retry_database_error_has_safe_feedback_and_retains_pending_intent(self):
        self.interrupt_review_after_new_item_insert(self.intent())
        self.client.force_login(self.other)
        with patch.object(MeetingDraft, "complete_review_update", side_effect=OperationalError("private connection details")):
            response = self.client.post(reverse("meetings:finish_review", args=[self.draft.pk]))
        self.assertRedirects(response, reverse("meetings:detail", args=[self.draft.pk]))
        self.assertNotIn("private", " ".join(str(message) for message in response.wsgi_request._messages))
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.review_update_pending)

    def test_review_http_database_error_preserves_intent_and_offers_recovery(self):
        self.client.force_login(self.officer)
        with patch.object(ActionItem, "save", side_effect=OperationalError("private database details")):
            response = self.client.post(reverse("meetings:review", args=[self.draft.pk]), {
                "decision": DraftStatus.APPROVED, "note": "Recorded decision",
                "new_items": "New recorded action",
                f"item-{self.item.pk}-description": "Recorded edited action",
                f"item-{self.item.pk}-accepted": "on",
            })
        self.assertRedirects(response, reverse("meetings:detail", args=[self.draft.pk]))
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.review_update_pending)
        self.assertEqual(self.draft.review_note, "Recorded decision")
        detail = self.client.get(response.url)
        self.assertContains(detail, "Finish review")
        self.assertNotContains(detail, "private database details")
        self.assertEqual(self.client.post(reverse("meetings:finish_review", args=[self.draft.pk])).status_code, 302)
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.review_update_pending)
        self.assertEqual(self.draft.action_items.count(), 2)

    def test_unfinished_revision_request_cannot_regenerate_until_action_updates_finish(self):
        with patch.object(ActionItem, "save", side_effect=OperationalError("Synthetic action failure")):
            with self.assertRaises(OperationalError):
                self.draft.review(self.officer, DraftStatus.REVISION_REQUESTED, item_intent=self.intent())
        self.draft.refresh_from_db()
        self.client.force_login(self.officer)
        revise_url = reverse("meetings:revise", args=[self.draft.pk])
        self.assertNotContains(self.client.get(reverse("meetings:detail", args=[self.draft.pk])), revise_url)
        with patch("meetings.models.summarize_meeting") as provider:
            self.assertEqual(self.client.post(revise_url, {"title": "Revised", "notes": "New notes"}).status_code, 302)
            with self.assertRaisesMessage(ValueError, "Finish the recorded action-item review"):
                self.draft.revise("New notes")
        provider.assert_not_called()
        self.draft.complete_review_update()
        self.assertContains(self.client.get(reverse("meetings:detail", args=[self.draft.pk])), revise_url)

    def test_invalid_or_foreign_item_intent_does_not_claim_a_review(self):
        other_draft = MeetingDraft.objects.create(title="Other", notes="Synthetic", created_by=self.other)
        foreign = ActionItem.objects.create(draft=other_draft, description="Keep with other draft")
        invalid_intents = [
            [{"id": str(foreign.pk), "description": "Moved", "accepted": True}],
            [{"id": str(self.item.pk), "description": "A" * 501, "accepted": True}],
            [{"id": str(self.item.pk), "description": "Valid", "accepted": "yes"}],
        ]
        for intent in invalid_intents:
            with self.subTest(intent=intent), self.assertRaises(ValueError):
                self.draft.review(self.officer, DraftStatus.APPROVED, item_intent=intent)
        self.draft.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(self.draft.status, DraftStatus.PENDING_REVIEW)
        self.assertFalse(self.draft.review_update_pending)
        self.assertEqual(foreign.draft_id, other_draft.pk)

    def test_import_uses_recorded_accepted_text_and_excludes_later_unreviewed_items(self):
        self.draft.review(self.officer, DraftStatus.APPROVED)
        self.item.description = "Unreviewed replacement"
        self.item.save()
        ActionItem.objects.create(draft=self.draft, description="Unreviewed late addition", accepted=True)
        result = import_action_items(self.officer, self.draft)
        self.assertEqual([task.title for task in result["created"]], ["Original accepted action"])

    def test_legacy_approved_draft_without_intent_still_imports_accepted_items(self):
        self.draft.status = DraftStatus.APPROVED
        self.draft.save(update_fields=["status"])
        self.assertIsNone(self.draft.review_item_intent)
        result = import_action_items(self.officer, self.draft)
        self.assertEqual([task.title for task in result["created"]], ["Original accepted action"])
