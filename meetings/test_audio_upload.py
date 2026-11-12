"""FR-7.1 / SCRUM-54: officers can upload a meeting recording for transcription."""

import io
import json
import os
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user

from .ai import MeetingSummary
from .models import DraftStatus, MeetingDraft
from .stt import DEEPGRAM_FILE_URL, transcribe_uploaded_audio

DEEPGRAM_RESPONSE = {
    "results": {"channels": [{"alternatives": [{
        "transcript": "We booked the hall. I'll pay the deposit.",
        "words": [
            {"word": "we", "punctuated_word": "We", "speaker": 0},
            {"word": "booked", "punctuated_word": "booked", "speaker": 0},
            {"word": "the", "punctuated_word": "the", "speaker": 0},
            {"word": "hall", "punctuated_word": "hall.", "speaker": 0},
            {"word": "i'll", "punctuated_word": "I'll", "speaker": 1},
            {"word": "pay", "punctuated_word": "pay", "speaker": 1},
            {"word": "the", "punctuated_word": "the", "speaker": 1},
            {"word": "deposit", "punctuated_word": "deposit.", "speaker": 1},
        ],
    }]}]},
}


def recording(name="meeting.mp3", content=b"ID3 fake audio", content_type="audio/mpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test-key"})
class TranscribeUploadedAudioTests(SimpleTestCase):
    def test_sends_the_file_and_formats_speakers(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(DEEPGRAM_RESPONSE).encode())) as urlopen:
            text = transcribe_uploaded_audio(recording())
        self.assertEqual(text, "Speaker 0: We booked the hall.\nSpeaker 1: I'll pay the deposit.")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, DEEPGRAM_FILE_URL)
        self.assertEqual(request.data, b"ID3 fake audio")
        self.assertEqual(request.get_header("Authorization"), "Token test-key")
        self.assertEqual(request.get_header("Content-type"), "audio/mpeg")
        self.assertLess(urlopen.call_args.kwargs["timeout"], 120)

    def test_unreadable_audio_is_a_value_error(self):
        error = HTTPError(DEEPGRAM_FILE_URL, 400, "Bad Request", {}, io.BytesIO(b"{}"))
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(ValueError):
            transcribe_uploaded_audio(recording())

    def test_provider_and_network_failures_are_runtime_errors(self):
        for failure in (HTTPError(DEEPGRAM_FILE_URL, 503, "Down", {}, io.BytesIO(b"")), URLError("offline"), TimeoutError()):
            with self.subTest(failure=type(failure).__name__):
                with patch("urllib.request.urlopen", side_effect=failure), self.assertRaises(RuntimeError) as raised:
                    transcribe_uploaded_audio(recording())
                self.assertNotIn("test-key", str(raised.exception))

    def test_missing_key_is_a_runtime_error(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": ""}), self.assertRaises(RuntimeError):
            transcribe_uploaded_audio(recording())

    def test_no_speech_returns_empty_text(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(b'{"results": {"channels": [{"alternatives": [{"transcript": ""}]}]}}')):
            self.assertEqual(transcribe_uploaded_audio(recording()), "")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MeetingUploadViewTests(TestCase):
    def setUp(self):
        self.officer = make_user("upload-officer@example.com", Role.OFFICER)
        self.client.force_login(self.officer)
        self.summary = MeetingSummary("Summary", ["Action: task=Pay the deposit"])

    def start(self, upload=None, **data):
        payload = {"title": "Spring planning", "transcript": "", "notes": "", **data}
        if upload is not None:
            payload["recording"] = upload
        return self.client.post(reverse("meetings:processing_start"), payload)

    def process(self, start_response):
        submission_id = parse_qs(urlparse(start_response.url).query)["submission_id"][0]
        with patch("meetings.models.summarize_meeting", return_value=self.summary):
            return self.client.post(f'{reverse("meetings:process")}?submission_id={submission_id}')

    def test_upload_only_submission_creates_a_draft_with_the_transcript(self):
        with patch("meetings.views.transcribe_uploaded_audio", return_value="Speaker 0: We booked the hall.") as stt:
            start = self.start(recording())
        stt.assert_called_once()
        self.assertEqual(start.status_code, 302)
        response = self.process(start)
        draft = MeetingDraft.objects.get()
        self.assertEqual(response.json()["redirect"], reverse("meetings:detail", args=[draft.pk]))
        self.assertEqual(draft.transcript, "Speaker 0: We booked the hall.")
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)

    def test_upload_is_added_after_a_live_transcript_and_notes_are_kept(self):
        with patch("meetings.views.transcribe_uploaded_audio", return_value="Speaker 0: Second part."):
            start = self.start(recording(), transcript="Speaker 0: First part.", notes="Officer context")
        self.process(start)
        draft = MeetingDraft.objects.get()
        self.assertEqual(draft.transcript, "Speaker 0: First part.\n\nSpeaker 0: Second part.")
        self.assertEqual(draft.notes, "Officer context")

    def test_wrong_file_type_is_rejected_without_transcribing(self):
        with patch("meetings.views.transcribe_uploaded_audio") as stt:
            response = self.start(recording("notes.pdf", b"%PDF", "application/pdf"))
        stt.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertIn("recording", response.context["form"].errors)

    def test_oversized_file_is_rejected_without_transcribing(self):
        with patch("meetings.views.UPLOAD_MAX_BYTES", 4), patch("meetings.views.transcribe_uploaded_audio") as stt:
            response = self.start(recording(content=b"too long"))
        stt.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertIn("25 MB", str(response.context["form"].errors["recording"]))

    def test_transcription_outage_keeps_notes_and_explains(self):
        with patch("meetings.views.transcribe_uploaded_audio", side_effect=RuntimeError("provider detail")):
            response = self.start(recording(), notes="Keep these notes")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "could not be transcribed right now", status_code=503)
        self.assertNotContains(response, "provider detail", status_code=503)
        self.assertEqual(response.context["form"]["notes"].value(), "Keep these notes")
        self.assertNotIn("meeting_processing_submissions", self.client.session)

    def test_unreadable_audio_and_silence_are_reported(self):
        for side_effect, message in ((ValueError("bad"), "could not be read as audio"), (None, "No speech was found")):
            with self.subTest(message=message):
                kwargs = {"side_effect": side_effect} if side_effect else {"return_value": "  "}
                with patch("meetings.views.transcribe_uploaded_audio", **kwargs):
                    response = self.start(recording())
                self.assertContains(response, message, status_code=400)

    def test_plain_create_form_also_accepts_uploads(self):
        with patch("meetings.views.transcribe_uploaded_audio", return_value="Speaker 0: Hello."), \
                patch("meetings.models.summarize_meeting", return_value=self.summary):
            response = self.client.post(reverse("meetings:create"), {"title": "Direct", "notes": "", "recording": recording()})
        draft = MeetingDraft.objects.get()
        self.assertRedirects(response, reverse("meetings:detail", args=[draft.pk]))
        self.assertEqual(draft.transcript, "Speaker 0: Hello.")

    def test_revision_can_add_a_recording(self):
        with patch("meetings.models.summarize_meeting", return_value=self.summary):
            self.client.post(reverse("meetings:create"), {"title": "Revise me", "notes": "First notes"})
        draft = MeetingDraft.objects.get()
        draft.review(self.officer, DraftStatus.REVISION_REQUESTED)
        draft.refresh_from_db()
        with patch("meetings.views.transcribe_uploaded_audio", return_value="Speaker 0: Added later."), \
                patch("meetings.models.summarize_meeting", return_value=self.summary):
            response = self.client.post(reverse("meetings:revise", args=[draft.pk]), {
                "title": "Revise me", "notes": "First notes", "recording": recording(),
                "expected_generation": draft.generation_token,
            })
        self.assertRedirects(response, reverse("meetings:detail", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertEqual(draft.transcript, "Speaker 0: Added later.")

    def test_form_page_shows_the_upload_field(self):
        response = self.client.get(reverse("meetings:create"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="recording"')
        self.assertContains(response, "Upload a recording")
