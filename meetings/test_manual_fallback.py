"""FR-7.6 / SCRUM-92: officers write the summary and action items when the AI is unavailable."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user

from .ai import MeetingSummary
from .models import DraftStatus, MeetingDraft

AI_DOWN = patch("meetings.models.summarize_meeting", side_effect=RuntimeError("provider offline: secret detail"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ManualFallbackTests(TestCase):
    def setUp(self):
        self.officer = make_user("fallback-officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)

    def create_while_ai_down(self, **data):
        with AI_DOWN, patch("meetings.models.generate_meeting_title") as title:
            response = self.client.post(reverse("meetings:create"), {"title": "Budget meeting", "notes": "We agreed to book the hall.", **data})
        title.assert_not_called()  # no second call to a provider that is already down
        return response, MeetingDraft.objects.get()

    def review(self, draft, decision, **data):
        return self.client.post(reverse("meetings:review", args=[draft.pk]), {
            "decision": decision, "expected_generation": draft.generation_token, "notes": draft.notes, **data,
        })

    def test_ai_outage_saves_notes_and_explains_next_step(self):
        response, draft = self.create_while_ai_down()
        self.assertRedirects(response, reverse("meetings:detail", args=[draft.pk]))
        self.assertTrue(draft.ai_unavailable)
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertIn("AI summarizer is unavailable", " ".join(str(m) for m in response.wsgi_request._messages))
        page = self.client.get(response.url)
        self.assertContains(page, "AI summary unavailable")
        self.assertContains(page, 'name="summary"')
        self.assertNotContains(page, "secret detail")
        self.assertContains(self.client.get(reverse("meetings:list")), "Manual summary")

    def test_untitled_notes_keep_the_default_title_when_ai_is_down(self):
        _, draft = self.create_while_ai_down(title="")
        self.assertTrue(draft.title.endswith(" - Untitled Notes"))

    def test_processing_page_path_also_falls_back(self):
        start = self.client.post(reverse("meetings:processing_start"), {"title": "Live notes", "transcript": "", "notes": "Hall booked."})
        submission_id = parse_qs(urlparse(start.url).query)["submission_id"][0]
        with AI_DOWN:
            response = self.client.post(f'{reverse("meetings:process")}?submission_id={submission_id}')
        draft = MeetingDraft.objects.get()
        self.assertEqual(response.json()["redirect"], reverse("meetings:detail", args=[draft.pk]))
        self.assertTrue(draft.ai_unavailable)
        self.assertContains(self.client.get(response.json()["redirect"]), "AI summarizer is unavailable")

    def test_officer_writes_summary_and_action_items_then_approves(self):
        _, draft = self.create_while_ai_down()
        response = self.review(
            draft, DraftStatus.APPROVED,
            summary="  We booked the hall for the spring social.  ",
            new_items="Action: owner=Mia; task=Pay the deposit\nAction: task=Send invitations",
        )
        self.assertRedirects(response, reverse("meetings:list"))
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.APPROVED)
        self.assertEqual(draft.summary, "We booked the hall for the spring social.")
        self.assertEqual(
            list(draft.current_action_items.filter(accepted=True).values_list("description", flat=True)),
            ["Action: owner=Mia; task=Pay the deposit", "Action: task=Send invitations"],
        )

    def test_approval_requires_a_summary(self):
        _, draft = self.create_while_ai_down()
        self.review(draft, DraftStatus.APPROVED, summary="   ", new_items="Action: task=Pay the deposit")
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertFalse(draft.current_action_items.exists())

    def test_ai_drafts_can_still_be_approved_without_editing_the_summary(self):
        with patch("meetings.models.summarize_meeting", return_value=MeetingSummary("", [])):
            self.client.post(reverse("meetings:create"), {"title": "Quiet meeting", "notes": "Nothing decided."})
        draft = MeetingDraft.objects.get()
        self.review(draft, DraftStatus.APPROVED)
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.APPROVED)

    def test_revision_requests_do_not_need_a_summary(self):
        _, draft = self.create_while_ai_down()
        self.review(draft, DraftStatus.REVISION_REQUESTED, summary="")
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.REVISION_REQUESTED)

    def test_officer_can_correct_an_ai_summary(self):
        with patch("meetings.models.summarize_meeting", return_value=MeetingSummary("AI wrote this", ["Action: task=One"])):
            self.client.post(reverse("meetings:create"), {"title": "AI meeting", "notes": "Notes."})
        draft = MeetingDraft.objects.get()
        self.assertFalse(draft.ai_unavailable)
        self.assertContains(self.client.get(reverse("meetings:detail", args=[draft.pk])), "AI summary")
        self.review(draft, DraftStatus.APPROVED, summary="Corrected by an officer")
        draft.refresh_from_db()
        self.assertEqual(draft.summary, "Corrected by an officer")

    def test_overlong_summary_is_rejected(self):
        _, draft = self.create_while_ai_down()
        self.review(draft, DraftStatus.APPROVED, summary="x" * 10001)
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.summary), (DraftStatus.PENDING_REVIEW, ""))

    def test_revision_while_ai_is_down_keeps_current_summary_and_kept_items(self):
        with patch("meetings.models.summarize_meeting", return_value=MeetingSummary("Original summary", ["Action: task=Keep me", "Action: task=Drop me"])):
            self.client.post(reverse("meetings:create"), {"title": "Revise me", "notes": "First notes."})
        draft = MeetingDraft.objects.get()
        keep, drop = draft.current_action_items
        self.review(draft, DraftStatus.REVISION_REQUESTED, **{
            f"item-{keep.pk}-description": keep.description, f"item-{keep.pk}-accepted": "on",
            f"item-{drop.pk}-description": drop.description,
        })
        with AI_DOWN:
            response = self.client.post(reverse("meetings:revise", args=[draft.pk]), {
                "title": "Revise me", "notes": "Second notes.", "expected_generation": draft.generation_token,
            })
        self.assertRedirects(response, reverse("meetings:detail", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertTrue(draft.ai_unavailable)
        self.assertEqual((draft.status, draft.notes, draft.summary), (DraftStatus.PENDING_REVIEW, "Second notes.", "Original summary"))
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), ["Action: task=Keep me"])

    def test_successful_revision_clears_the_manual_flag(self):
        _, draft = self.create_while_ai_down()
        self.review(draft, DraftStatus.REVISION_REQUESTED, summary="")
        draft.refresh_from_db()
        with patch("meetings.models.summarize_meeting", return_value=MeetingSummary("AI is back", [])):
            self.client.post(reverse("meetings:revise", args=[draft.pk]), {
                "title": draft.title, "notes": "Updated notes.", "expected_generation": draft.generation_token,
            })
        draft.refresh_from_db()
        self.assertFalse(draft.ai_unavailable)
        self.assertEqual(draft.summary, "AI is back")

    def test_empty_input_is_still_a_validation_error_not_a_fallback(self):
        with AI_DOWN:
            response = self.client.post(reverse("meetings:create"), {"title": "Empty", "notes": "  "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MeetingDraft.objects.exists())
