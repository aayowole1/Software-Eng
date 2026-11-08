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

    @patch("meetings.models.summarize_meeting")
    def test_blank_title_gets_date_based_untitled_meeting_title(self, summarize):
        summarize.return_value = MeetingSummary("Summary", [])

        response = self.client.post(
            reverse("meetings:create"),
            {"title": "", "transcript": "", "notes": "Officer notes from the meeting"},
        )

        self.assertEqual(response.status_code, 302)
        draft = MeetingDraft.objects.get()
        self.assertEqual(draft.title, f"{timezone.now():%d %B, %Y} - Untitled Meeting")

    @patch("meetings.models.summarize_meeting")
    def test_submit_requires_notes_or_transcript(self, summarize):
        response = self.client.post(
            reverse("meetings:create"),
            {"title": "", "transcript": "", "notes": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add officer notes or record part of the meeting before submitting.")
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
        self.assertNotContains(response, 'class="meeting-transcript"')

    def test_officer_can_save_notes_from_review_page(self):
        draft = MeetingDraft.objects.create(
            title="Review notes",
            notes="Initial notes",
            summary="AI summary",
            created_by=self.officer,
        )

        response = self.client.post(
            reverse("meetings:save_notes", args=[draft.pk]),
            {"notes": "Officer merged notes"},
        )

        self.assertRedirects(response, reverse("meetings:detail", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertEqual(draft.notes, "Officer merged notes")

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
