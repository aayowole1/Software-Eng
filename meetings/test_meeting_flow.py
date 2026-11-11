from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .ai import MeetingSummary
from .models import MeetingDraft


class MeetingFlowTests(TestCase):
    def setUp(self):
        self.officer = make_user("meeting-flow@example.com", Role.OFFICER)
        self.client.force_login(self.officer)

    @patch("meetings.models.generate_meeting_title", return_value="Officer Notes Meeting")
    @patch("meetings.models.summarize_meeting")
    def test_blank_title_gets_llm_descriptive_title(self, summarize, generate_title):
        summarize.return_value = MeetingSummary("Summary", [])

        response = self.client.post(
            reverse("meetings:create"),
            {"title": "", "transcript": "", "notes": "Officer notes from the meeting"},
        )

        self.assertEqual(response.status_code, 302)
        draft = MeetingDraft.objects.get()
        self.assertEqual(draft.title, "Officer Notes Meeting")
        generate_title.assert_called_once()

    @patch("meetings.models.summarize_meeting")
    def test_submit_requires_notes_or_transcript(self, summarize):
        response = self.client.post(
            reverse("meetings:create"),
            {"title": "", "transcript": "", "notes": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add officer notes or record audio before submitting.")
        self.assertContains(response, 'class="notes-submit-warning"')
        summarize.assert_not_called()
        self.assertFalse(MeetingDraft.objects.exists())

    def test_creation_page_keeps_transcript_hidden_and_wires_recording_flow(self):
        response = self.client.get(reverse("meetings:create"))

        self.assertContains(response, 'id="start-recording"')
        self.assertContains(response, 'id="stop-recording"')
        self.assertContains(response, 'id="submit-meeting"')
        self.assertContains(response, 'id="id_transcript"')
        self.assertContains(response, 'type="hidden"')
        self.assertContains(response, "let isPaused = false;")
        self.assertContains(response, "async function finalizeRecording()")
        self.assertContains(response, 'X-Recording-Final')
        self.assertContains(response, "form.submit();")
        self.assertContains(response, 'action="/meetings/new/processing/start/"')
        self.assertNotContains(response, 'class="meeting-transcript"')
        self.assertNotContains(response, "Click Start Notes and allow microphone access")
        self.assertContains(response, "Start Notes before selecting Stop Notes.")
        self.assertContains(response, "Start Notes and record audio, or add officer notes before submitting.")
        self.assertContains(response, "Submitting notes and preparing the draft")
        self.assertContains(response, "function showProcessingPage()")
        self.assertNotContains(response, "Start Notes to resume or Submit Notes to finish.")
        self.assertContains(response, 'placeholder="Enter Title Here"')
        self.assertContains(response, 'placeholder="Add Notes Here"')
        self.assertNotContains(response, "Add your own notes below.")
        self.assertNotContains(response, "until an officer approves it.")

    def test_notes_list_uses_note_labels(self):
        response = self.client.get(reverse("meetings:list"))
        self.assertContains(response, "Start Note Transcription")
        self.assertNotContains(response, "Notes drafts")

    def test_submit_redirects_to_separate_processing_page(self):
        response = self.client.post(
            reverse("meetings:processing_start"),
            {"title": "Processing test", "transcript": "Transcript", "notes": ""},
        )
        self.assertRedirects(response, reverse("meetings:processing"))
        page = self.client.get(response.url)
        self.assertContains(page, "Processing notes")
        self.assertContains(page, "Transcribing audio and preparing the notes summary and action items.")

    @patch("meetings.models.summarize_meeting")
    def test_processing_page_completes_generation_and_redirects_to_draft(self, summarize):
        summarize.return_value = MeetingSummary("Processed summary", ["Action: Follow up"])

        self.client.post(
            reverse("meetings:processing_start"),
            {"title": "Async meeting", "transcript": "Deepgram text", "notes": "Officer notes"},
        )
        response = self.client.post(reverse("meetings:process"))

        self.assertEqual(response.status_code, 200)
        draft = MeetingDraft.objects.get(title="Async meeting")
        self.assertEqual(response.json()["redirect"], reverse("meetings:detail", args=[draft.pk]))
        self.assertEqual(draft.summary, "Processed summary")

    def test_review_submission_saves_officer_notes(self):
        draft = MeetingDraft.objects.create(
            title="Review notes",
            notes="Initial notes",
            summary="AI summary",
            created_by=self.officer,
        )

        response = self.client.post(
            reverse("meetings:review", args=[draft.pk]),
            {"notes": "Officer merged notes", "decision": "approved", "expected_generation": ""},
        )

        self.assertRedirects(response, reverse("meetings:list"))
        draft.refresh_from_db()
        self.assertEqual(draft.notes, "Officer merged notes")

    def test_every_review_decision_returns_to_notes_list(self):
        for decision in ("approved", "rejected", "revision_requested"):
            with self.subTest(decision=decision):
                draft = MeetingDraft.objects.create(
                    title=f"{decision} notes",
                    notes="Officer notes",
                    created_by=self.officer,
                )
                response = self.client.post(
                    reverse("meetings:review", args=[draft.pk]),
                    {"notes": "Reviewed notes", "decision": decision, "expected_generation": ""},
                )
                self.assertRedirects(response, reverse("meetings:list"))

    def test_officer_can_review_but_cannot_delete(self):
        draft = MeetingDraft.objects.create(title="Protected notes", created_by=self.officer)
        review = self.client.post(
            reverse("meetings:review", args=[draft.pk]),
            {"decision": "approved", "expected_generation": ""},
        )
        self.assertRedirects(review, reverse("meetings:list"))
        draft.refresh_from_db()
        self.assertEqual(draft.status, "approved")
        deletion = self.client.post(reverse("meetings:delete", args=[draft.pk]))
        self.assertEqual(deletion.status_code, 403)
        self.assertTrue(MeetingDraft.objects.filter(pk=draft.pk).exists())

    def test_admin_can_delete_notes(self):
        admin = make_user("meeting-admin@example.com", Role.ADMIN)
        draft = MeetingDraft.objects.create(title="Admin notes", created_by=self.officer)
        self.client.force_login(admin)
        response = self.client.post(reverse("meetings:delete", args=[draft.pk]))
        self.assertRedirects(response, reverse("meetings:list"))
        self.assertFalse(MeetingDraft.objects.filter(pk=draft.pk).exists())

    def test_review_page_has_full_width_notes_and_read_only_transcript(self):
        draft = MeetingDraft.objects.create(
            title="Review layout",
            notes="Officer notes",
            transcript="Transcript text",
            summary="AI summary",
            created_by=self.officer,
        )

        response = self.client.get(reverse("meetings:detail", args=[draft.pk]))

        self.assertContains(response, 'class="transcript-display"')
        self.assertContains(response, 'class="meeting-review-form"')
        self.assertNotContains(response, "Save notes")
        self.assertContains(response, "Add action items (one per line)")
        self.assertContains(response, "class=\"action-item-list\"")
        self.assertContains(response, "meeting-summary-scroll")
        self.assertContains(response, "meeting-review-actions")
        self.assertContains(response, "transcript-display")

    def test_notes_layout_uses_equal_review_cards_and_full_width_fields(self):
        response = self.client.get(reverse("meetings:detail", args=[MeetingDraft.objects.create(
            title="Layout notes",
            notes="Officer notes",
            summary="AI summary",
            created_by=self.officer,
        ).pk]))

        self.assertContains(response, "meeting-review-columns")

    @patch("meetings.models.summarize_meeting")
    def test_submit_persists_transcript_notes_summary_and_actions(self, summarize):
        summarize.return_value = MeetingSummary("AI summary", ["Action: Follow up"])

        response = self.client.post(
            reverse("meetings:create"),
            {
                "title": "Recorded meeting",
                "transcript": "Deepgram transcript",
                "notes": "Officer notes",
            },
        )

        self.assertEqual(response.status_code, 302)
        draft = MeetingDraft.objects.get()
        self.assertEqual(draft.transcript, "Deepgram transcript")
        self.assertEqual(draft.notes, "Officer notes")
        self.assertEqual(draft.summary, "AI summary")
        self.assertEqual(list(draft.current_action_items.values_list("description", flat=True)), ["Action: Follow up"])

    def test_transcribe_endpoint_accepts_chunks_and_finalizes_recording(self):
        class FakeTranscriber:
            def add_pcm(self, audio):
                self.audio = audio
                return "partial transcript"

            def current_result(self):
                return "partial transcript"

            def finish(self):
                return "final transcript"

            def discard(self):
                pass

        transcriber = FakeTranscriber()
        with patch("meetings.views.DeepgramTranscriber", return_value=transcriber):
            chunk = self.client.post(
                reverse("meetings:transcribe"),
                data=b"pcm",
                content_type="application/octet-stream",
                HTTP_X_RECORDING_ID="flow-test",
            )
            final = self.client.post(
                reverse("meetings:transcribe"),
                data=b"",
                content_type="application/octet-stream",
                HTTP_X_RECORDING_ID="flow-test",
                HTTP_X_RECORDING_FINAL="true",
            )

        self.assertEqual(chunk.json(), {"transcript": "partial transcript"})
        self.assertEqual(final.json(), {"transcript": "final transcript"})

    def test_transcribe_timeout_discards_recording_and_returns_retryable_error(self):
        class FailingTranscriber:
            def add_pcm(self, audio):
                raise TimeoutError("Deepgram timed out")

            def discard(self):
                self.discarded = True

        transcriber = FailingTranscriber()
        with patch("meetings.views.DeepgramTranscriber", return_value=transcriber):
            response = self.client.post(
                reverse("meetings:transcribe"),
                data=b"pcm",
                content_type="application/octet-stream",
                HTTP_X_RECORDING_ID="timeout-test",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "Deepgram timed out")

    def test_empty_processing_result_warns_that_no_audio_was_found(self):
        self.client.post(
            reverse("meetings:processing_start"),
            {"title": "No audio", "transcript": "temporary", "notes": ""},
        )
        session = self.client.session
        session["meeting_processing"]["transcript"] = ""
        session.save()
        response = self.client.post(reverse("meetings:process"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"],
            "No audio was found. Record audio or add officer notes before submitting.",
        )
