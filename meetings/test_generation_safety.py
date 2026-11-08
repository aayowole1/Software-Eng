"""Meeting generation publication and approved import consistency regressions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.db import OperationalError, close_old_connections, connection
from django.db.models import QuerySet
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from meetings.ai import MeetingSummary
from meetings.models import ActionItem, DraftStatus, MeetingDraft, MeetingReviewConflict
from tasks.services import import_action_items


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MeetingGenerationSafetyTests(TestCase):
    def setUp(self):
        self.officer = make_user("generation-officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)
        self.output = MeetingSummary("Complete summary", ["First complete action", "Second complete action"])

    def draft(self):
        draft = MeetingDraft.objects.create(title="Original", notes="Original notes", created_by=self.officer)
        ActionItem.objects.create(draft=draft, description="Original action")
        return draft

    def test_creation_is_not_visible_while_actions_are_being_staged(self):
        visible = []
        original_create = ActionItem.objects.create

        def observe_visibility(**fields):
            draft_id = fields.get("draft_id") or fields["draft"].pk
            visible.append(MeetingDraft.objects.filter(pk=draft_id).exists())
            return original_create(**fields)

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch("meetings.models.ActionItem.objects.create", side_effect=observe_visibility),
        ):
            response = self.client.post(reverse("meetings:create"), {"title": "Created", "notes": "New notes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(visible, [False, False])
        draft = MeetingDraft.objects.get(title="Created")
        self.assertEqual(draft.current_action_items.count(), 2)

    def test_stale_revision_cannot_replace_a_subsequently_approved_generation(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        stale = MeetingDraft.objects.get(pk=draft.pk)
        with patch("meetings.models.summarize_meeting", return_value=self.output):
            draft.revise("Winning revised notes")
        draft.review(self.officer, DraftStatus.APPROVED, "Approved complete winner")
        with patch("meetings.models.summarize_meeting", return_value=MeetingSummary("Stale", ["Stale action"])):
            with self.assertRaises(MeetingReviewConflict):
                stale.revise("Losing revised notes")
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.notes, draft.review_note), (
            DraftStatus.APPROVED, "Winning revised notes", "Approved complete winner",
        ))

    def test_import_preview_and_conversion_use_the_same_approved_snapshot(self):
        draft = self.draft()
        item = draft.action_items.get()
        draft.review(self.officer, DraftStatus.APPROVED)
        ActionItem.objects.filter(pk=item.pk).update(description="Unreviewed replacement", accepted=False)
        ActionItem.objects.create(draft=draft, description="Unreviewed late addition")
        response = self.client.get(reverse("tasks:import_draft", args=[draft.pk]))
        self.assertContains(response, "Original action")
        self.assertNotContains(response, "Unreviewed replacement")
        self.assertNotContains(response, "Unreviewed late addition")
        self.assertEqual([task.title for task in import_action_items(self.officer, draft)["created"]], ["Original action"])

    def test_django_admin_cannot_bypass_generation_and_review_services(self):
        administrator = make_user("generation-admin@example.com", Role.ADMIN)
        administrator.is_staff = administrator.is_superuser = True
        administrator.save(update_fields=["is_staff", "is_superuser"])
        request = RequestFactory().get("/admin/meetings/meetingdraft/")
        request.user = administrator
        registered = admin.site._registry[MeetingDraft]
        self.assertTrue(registered.has_view_permission(request))
        self.assertFalse(registered.has_add_permission(request))
        self.assertFalse(registered.has_change_permission(request, self.draft()))
        self.assertFalse(registered.has_delete_permission(request, self.draft()))
        draft = self.draft()
        self.client.force_login(administrator)
        self.assertContains(self.client.get(reverse("admin:meetings_meetingdraft_change", args=[draft.pk])), "Original action")
        for name, args in (
            ("add", []), ("change", [draft.pk]), ("delete", [draft.pk]),
        ):
            with self.subTest(route=name):
                response = self.client.post(reverse(f"admin:meetings_meetingdraft_{name}", args=args), {
                    "title": "Bypass", "status": "approved", "notes": "Bypass notes",
                })
                self.assertEqual(response.status_code, 403)
        draft.refresh_from_db()
        self.assertEqual((draft.title, draft.status), ("Original", DraftStatus.PENDING_REVIEW))

    def test_revision_keeps_previous_generation_visible_until_complete(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        observations = []
        original_create = ActionItem.objects.create

        def observe(**fields):
            item = original_create(**fields)
            current = MeetingDraft.objects.get(pk=draft.pk)
            observations.append((current.status, current.notes, list(current.current_action_items.values_list("description", flat=True))))
            return item

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch("meetings.models.ActionItem.objects.create", side_effect=observe),
        ):
            draft.revise("Revised notes")
        self.assertEqual(observations, [(DraftStatus.REVISION_REQUESTED, "Original notes", ["Original action"])] * 2)
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), self.output.action_items)
        detail = self.client.get(reverse("meetings:detail", args=[draft.pk]))
        self.assertNotContains(detail, "Original action")
        self.assertContains(detail, "First complete action")

    def test_old_review_form_cannot_approve_a_new_generation(self):
        draft = self.draft()
        stale = MeetingDraft.objects.get(pk=draft.pk)
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        with patch("meetings.models.summarize_meeting", return_value=self.output):
            draft.revise("Revised notes")
        with self.assertRaises(MeetingReviewConflict):
            stale.review(self.officer, DraftStatus.APPROVED)
        response = self.client.post(reverse("meetings:review", args=[draft.pk]), {
            "decision": "approved", "expected_generation": "", "new_items": "Unreviewed addition",
        })
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertEqual(draft.current_action_items.count(), 2)
        detail = self.client.get(response.url)
        self.assertContains(detail, f'value="{draft.generation_token}"')

    def test_actual_competing_revisions_publish_only_one_complete_generation(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        barrier = Barrier(2)

        def summarize(notes):
            barrier.wait(timeout=10)
            return MeetingSummary(notes, [f"{notes} first", f"{notes} second"])

        def revise(notes):
            close_old_connections()
            try:
                loaded = MeetingDraft.objects.get(pk=draft.pk)
                try:
                    loaded.revise(notes)
                    return notes
                except MeetingReviewConflict:
                    return "conflict"
            finally:
                close_old_connections()

        with patch("meetings.models.summarize_meeting", side_effect=summarize), ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(revise, "First revision")
            second = workers.submit(revise, "Second revision")
            results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(results.count("conflict"), 1)
        winner = next(result for result in results if result != "conflict")
        draft.refresh_from_db()
        self.assertEqual((draft.notes, draft.summary, draft.status), (winner, winner, DraftStatus.PENDING_REVIEW))
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), [f"{winner} first", f"{winner} second"])
        self.assertEqual(draft.action_items.count(), 3)  # Prior generation retained; loser stage removed.
        draft.review(self.officer, DraftStatus.APPROVED)
        self.assertEqual(len(import_action_items(self.officer, draft)["created"]), 2)

    def test_partial_revision_failure_leaves_published_generation_unchanged(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        original_create = ActionItem.objects.create

        def create_then_fail(**fields):
            original_create(**fields)
            raise OperationalError("Private stage failure")

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch("meetings.models.ActionItem.objects.create", side_effect=create_then_fail),
        ):
            response = self.client.post(reverse("meetings:revise", args=[draft.pk]), {
                "title": "Changed", "notes": "Changed notes", "expected_generation": "",
            })
        self.assertContains(response, "could not be confirmed", status_code=503)
        self.assertNotContains(response, "Private stage failure", status_code=503)
        draft.refresh_from_db()
        self.assertEqual((draft.title, draft.notes, draft.status), ("Original", "Original notes", DraftStatus.REVISION_REQUESTED))
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), ["Original action"])
        self.assertEqual(draft.action_items.count(), 1)

    def test_deleted_draft_is_not_resurrected_by_revision_publication(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        original_create = ActionItem.objects.create
        pk = draft.pk

        def stage_then_delete(**fields):
            item = original_create(**fields)
            MeetingDraft.objects.filter(pk=pk).delete()
            return item

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch("meetings.models.ActionItem.objects.create", side_effect=stage_then_delete),
        ):
            with self.assertRaises(MeetingReviewConflict):
                draft.revise("Must not resurrect")
        self.assertFalse(MeetingDraft.objects.filter(pk=pk).exists())
        self.assertFalse(ActionItem.objects.filter(draft_id=pk).exists())

    def test_acknowledgement_lost_after_creation_and_review_does_not_compensate_approval(self):
        original_save = MeetingDraft.save

        def publish_review_then_fail(draft, *args, **kwargs):
            original_save(draft, *args, **kwargs)
            draft.review(self.officer, DraftStatus.APPROVED, "Approved after complete publication")
            raise OperationalError("Private acknowledgement failure")

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch.object(MeetingDraft, "save", publish_review_then_fail),
        ):
            response = self.client.post(reverse("meetings:create"), {"title": "Created", "notes": "New notes"})
        self.assertEqual(response.status_code, 302)
        draft = MeetingDraft.objects.get(title="Created")
        self.assertEqual(draft.status, DraftStatus.APPROVED)
        self.assertEqual(draft.current_action_items.count(), 2)
        self.assertEqual(len(import_action_items(self.officer, draft)["created"]), 2)

    def test_unknown_revision_publication_can_be_retried_without_showing_unpublished_items(self):
        draft = self.draft()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        original_update = QuerySet.update

        def fail_publication(queryset, **fields):
            if queryset.model is MeetingDraft and "summary" in fields:
                raise OperationalError("Private publication failure")
            return original_update(queryset, **fields)

        with (
            patch("meetings.models.summarize_meeting", return_value=self.output),
            patch.object(QuerySet, "update", fail_publication),
        ):
            with self.assertRaises(OperationalError):
                draft.revise("Unconfirmed revision")
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.REVISION_REQUESTED)
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), ["Original action"])
        with patch("meetings.models.summarize_meeting", return_value=self.output):
            draft.revise("Confirmed retry")
        self.assertEqual(draft.current_action_items.count(), 2)
        self.assertEqual(draft.action_items.count(), 5)  # Unknown stage retained but never selected.
        draft.review(self.officer, DraftStatus.APPROVED)
        self.assertEqual(len(import_action_items(self.officer, draft)["created"]), 2)

    def test_raw_missing_legacy_tokens_support_review_recovery_and_legacy_import(self):
        draft = self.draft()
        item = draft.action_items.get()
        connection.get_collection(MeetingDraft._meta.db_table).update_one({"_id": draft.pk}, {"$unset": {"generation_token": ""}})
        connection.get_collection(ActionItem._meta.db_table).update_one({"_id": item.pk}, {"$unset": {"generation_token": ""}})
        draft.refresh_from_db()
        self.assertEqual(draft.current_action_items.count(), 1)
        draft.review(self.officer, DraftStatus.APPROVED)
        self.assertFalse(draft.review_update_pending)
        self.assertEqual([task.title for task in import_action_items(self.officer, draft)["created"]], ["Original action"])
