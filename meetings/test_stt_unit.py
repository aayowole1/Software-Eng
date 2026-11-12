"""Unit tests for meetings/stt.py — DeepgramTranscriber without a live API key.

The WebSocket client is replaced with a fake, so these run offline and without
any cost.  They cover every public method and the private helpers.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from meetings.stt import DeepgramTranscriber, DEEPGRAM_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result_message(transcript, *, is_final=True, words=None):
    """Build a minimal Deepgram 'Results' message payload."""
    alternative = {"transcript": transcript}
    if words is not None:
        alternative["words"] = words
    return json.dumps({
        "type": "Results",
        "is_final": is_final,
        "channel": {"alternatives": [alternative]},
    })


def _make_error_message(description="something went wrong"):
    return json.dumps({"type": "Error", "description": description})


def _fake_socket(messages):
    """Return a mock WebSocket that yields `messages` from recv(), then ''."""
    socket = MagicMock()
    socket.recv.side_effect = [*messages, ""]
    return socket


def _make_transcriber():
    """Create a DeepgramTranscriber with the env-var set."""
    with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test-dg-key"}):
        return DeepgramTranscriber()


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class InitTests(SimpleTestCase):
    """DeepgramTranscriber.__init__ guards against a missing API key."""

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": ""}):
            with self.assertRaisesMessage(RuntimeError, "DEEPGRAM_API_KEY is not configured"):
                DeepgramTranscriber()

    def test_whitespace_only_api_key_raises(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "   "}):
            with self.assertRaisesMessage(RuntimeError, "DEEPGRAM_API_KEY is not configured"):
                DeepgramTranscriber()

    def test_valid_api_key_succeeds(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "real-key"}):
            t = DeepgramTranscriber()
        self.assertEqual(t.api_key, "real-key")
        self.assertFalse(t.finished)
        self.assertEqual(t.transcript, "")
        t.discard()

    def test_temp_file_created_on_disk(self):
        t = _make_transcriber()
        try:
            self.assertTrue(t.audio_path.exists())
        finally:
            t.discard()

    def test_temp_file_has_expected_suffix(self):
        t = _make_transcriber()
        try:
            self.assertTrue(t.audio_path.name.endswith(".pcm"))
        finally:
            t.discard()

    def test_temp_file_has_expected_prefix(self):
        t = _make_transcriber()
        try:
            self.assertTrue(t.audio_path.name.startswith("orgflow-meeting-"))
        finally:
            t.discard()


# ---------------------------------------------------------------------------
# add_pcm
# ---------------------------------------------------------------------------

class AddPcmTests(SimpleTestCase):
    """add_pcm validates chunks and writes them to the temp file."""

    def setUp(self):
        self.t = _make_transcriber()

    def tearDown(self):
        self.t.discard()

    def test_even_length_chunk_is_accepted(self):
        # Should not raise.
        self.t.add_pcm(b"\x00\x01")

    def test_odd_length_chunk_raises(self):
        with self.assertRaisesMessage(ValueError, "complete 16-bit PCM samples"):
            self.t.add_pcm(b"\x00\x01\x02")

    def test_zero_length_chunk_is_accepted(self):
        # An empty chunk is even-length (0 % 2 == 0) and is valid.
        result = self.t.add_pcm(b"")
        self.assertEqual(result, "")

    def test_add_pcm_returns_current_transcript(self):
        # Before any transcription the transcript is empty.
        result = self.t.add_pcm(b"\xAA\xBB")
        self.assertEqual(result, "")

    def test_add_pcm_writes_bytes_to_file(self):
        audio = b"\x01\x02\x03\x04"
        self.t.add_pcm(audio)
        self.t.audio_file.flush()
        content = self.t.audio_path.read_bytes()
        self.assertEqual(content, audio)

    def test_add_pcm_appends_multiple_chunks(self):
        self.t.add_pcm(b"\x01\x02")
        self.t.add_pcm(b"\x03\x04")
        content = self.t.audio_path.read_bytes()
        self.assertEqual(content, b"\x01\x02\x03\x04")

    def test_add_pcm_after_finish_raises(self):
        socket = _fake_socket([_make_result_message("hello")])
        with patch("websocket.create_connection", return_value=socket):
            self.t.finish()
        with self.assertRaisesMessage(RuntimeError, "already been finalized"):
            self.t.add_pcm(b"\x00\x00")


# ---------------------------------------------------------------------------
# current_result
# ---------------------------------------------------------------------------

class CurrentResultTests(SimpleTestCase):
    """current_result always returns the most recent transcript string."""

    def test_initial_result_is_empty(self):
        t = _make_transcriber()
        try:
            self.assertEqual(t.current_result(), "")
        finally:
            t.discard()

    def test_result_after_finish_matches_transcript(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("test transcript")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        self.assertEqual(t.current_result(), "test transcript")


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------

@patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test-dg-key"})
class FinishTests(SimpleTestCase):
    """finish() transcribes audio, stores the result, then deletes the file."""

    def test_finish_returns_transcript(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("board meeting notes")])
        with patch("websocket.create_connection", return_value=socket):
            result = t.finish()
        self.assertEqual(result, "board meeting notes")

    def test_finish_stores_transcript_on_instance(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("stored result")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        self.assertEqual(t.transcript, "stored result")

    def test_finish_deletes_temp_file(self):
        t = _make_transcriber()
        audio_path = t.audio_path
        socket = _fake_socket([_make_result_message("text")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        self.assertFalse(audio_path.exists())

    def test_finish_idempotent_does_not_re_transcribe(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("first call")])
        with patch("websocket.create_connection", return_value=socket) as mock_cc:
            t.finish()
            second = t.finish()
        # create_connection called only once; transcript unchanged.
        mock_cc.assert_called_once()
        self.assertEqual(second, "first call")

    def test_finish_marks_instance_as_finished(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("text")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        self.assertTrue(t.finished)

    def test_finish_concatenates_multiple_final_results(self):
        t = _make_transcriber()
        messages = [
            _make_result_message("first segment"),
            _make_result_message("second segment"),
        ]
        socket = _fake_socket(messages)
        with patch("websocket.create_connection", return_value=socket):
            result = t.finish()
        self.assertIn("first segment", result)
        self.assertIn("second segment", result)

    def test_finish_skips_non_final_results(self):
        t = _make_transcriber()
        interim = json.dumps({
            "type": "Results",
            "is_final": False,
            "channel": {"alternatives": [{"transcript": "interim text"}]},
        })
        final = _make_result_message("final text")
        socket = _fake_socket([interim, final])
        with patch("websocket.create_connection", return_value=socket):
            result = t.finish()
        self.assertEqual(result, "final text")

    def test_finish_skips_blank_transcripts(self):
        t = _make_transcriber()
        blank = _make_result_message("   ")
        filled = _make_result_message("real words")
        socket = _fake_socket([blank, filled])
        with patch("websocket.create_connection", return_value=socket):
            result = t.finish()
        self.assertEqual(result, "real words")

    def test_finish_returns_empty_string_when_no_final_results(self):
        t = _make_transcriber()
        socket = _fake_socket([])
        with patch("websocket.create_connection", return_value=socket):
            result = t.finish()
        self.assertEqual(result, "")

    def test_finish_sends_close_stream_message(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("ok")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        close_calls = [
            c for c in socket.send.call_args_list
            if c.args and '"CloseStream"' in c.args[0]
        ]
        self.assertTrue(close_calls, "CloseStream was never sent to the socket")

    def test_finish_closes_websocket(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("ok")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        socket.close.assert_called_once()

    def test_finish_passes_api_key_as_auth_header(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("ok")])
        with patch("websocket.create_connection", return_value=socket) as mock_cc:
            t.finish()
        _, kwargs = mock_cc.call_args
        headers = kwargs.get("header", [])
        self.assertTrue(
            any("test-dg-key" in h for h in headers),
            "API key not found in WebSocket auth header",
        )

    def test_finish_connects_to_deepgram_url(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("ok")])
        with patch("websocket.create_connection", return_value=socket) as mock_cc:
            t.finish()
        url = mock_cc.call_args.args[0]
        self.assertEqual(url, DEEPGRAM_URL)

    def test_finish_wraps_transcription_error_as_runtime_error(self):
        t = _make_transcriber()
        with patch("websocket.create_connection", side_effect=OSError("refused")):
            with self.assertRaisesMessage(RuntimeError, "Deepgram transcription failed"):
                t.finish()
        # File must still be cleaned up even when transcription raises.
        self.assertFalse(t.audio_path.exists())

    def test_finish_raises_on_deepgram_error_message(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_error_message("Invalid credentials")])
        with patch("websocket.create_connection", return_value=socket):
            with self.assertRaisesMessage(RuntimeError, "Deepgram transcription failed"):
                t.finish()

    def test_finish_raises_on_non_json_websocket_message(self):
        t = _make_transcriber()
        socket = _fake_socket(["this is not json"])
        with patch("websocket.create_connection", return_value=socket):
            with self.assertRaisesMessage(RuntimeError, "Deepgram transcription failed"):
                t.finish()


# ---------------------------------------------------------------------------
# discard
# ---------------------------------------------------------------------------

class DiscardTests(SimpleTestCase):
    """discard() closes and removes the temp file without transcribing."""

    def test_discard_deletes_temp_file(self):
        t = _make_transcriber()
        path = t.audio_path
        t.discard()
        self.assertFalse(path.exists())

    def test_discard_marks_finished(self):
        t = _make_transcriber()
        t.discard()
        self.assertTrue(t.finished)

    def test_discard_twice_is_safe(self):
        t = _make_transcriber()
        t.discard()
        # Should not raise.
        t.discard()

    def test_discard_does_not_call_transcription(self):
        t = _make_transcriber()
        with patch("websocket.create_connection") as mock_cc:
            t.discard()
        mock_cc.assert_not_called()

    def test_discard_after_finish_is_safe(self):
        t = _make_transcriber()
        socket = _fake_socket([_make_result_message("text")])
        with patch("websocket.create_connection", return_value=socket):
            t.finish()
        # Should not raise even though the file is already gone.
        t.discard()


# ---------------------------------------------------------------------------
# _delete_audio_file
# ---------------------------------------------------------------------------

class DeleteAudioFileTests(SimpleTestCase):
    """_delete_audio_file silently handles already-missing files."""

    def test_delete_removes_existing_file(self):
        t = _make_transcriber()
        path = t.audio_path
        t.audio_file.close()
        t.finished = True
        t._delete_audio_file()
        self.assertFalse(path.exists())

    def test_delete_missing_file_does_not_raise(self):
        t = _make_transcriber()
        t.discard()
        # File is already gone; calling again must not raise.
        t._delete_audio_file()

    def test_delete_suppresses_oserror(self):
        t = _make_transcriber()
        t.audio_file.close()
        t.finished = True
        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            # Should not propagate.
            t._delete_audio_file()


# ---------------------------------------------------------------------------
# _format_speakers  (pure static method — no mocking needed)
# ---------------------------------------------------------------------------

class FormatSpeakersTests(SimpleTestCase):
    """_format_speakers groups words by speaker and formats the output."""

    @staticmethod
    def fmt(alternative, text):
        return DeepgramTranscriber._format_speakers(alternative, text)

    def _word(self, text, speaker=None, punctuated=None):
        entry = {"word": text}
        if punctuated is not None:
            entry["punctuated_word"] = punctuated
        if speaker is not None:
            entry["speaker"] = speaker
        return entry

    # --- No speaker information ---

    def test_no_words_returns_text_unchanged(self):
        result = self.fmt({"words": []}, "hello world")
        self.assertEqual(result, "hello world")

    def test_words_without_speaker_field_returns_text_unchanged(self):
        words = [self._word("hello"), self._word("world")]
        result = self.fmt({"words": words}, "hello world")
        self.assertEqual(result, "hello world")

    def test_missing_words_key_returns_text_unchanged(self):
        result = self.fmt({}, "just the text")
        self.assertEqual(result, "just the text")

    # --- Single speaker ---

    def test_single_speaker_all_words(self):
        words = [
            self._word("Hello", speaker=0),
            self._word("world", speaker=0),
        ]
        result = self.fmt({"words": words}, "Hello world")
        self.assertEqual(result, "Speaker 0: Hello world")

    def test_single_speaker_uses_punctuated_word_when_present(self):
        words = [
            self._word("hello", speaker=0, punctuated="Hello,"),
            self._word("world", speaker=0, punctuated="world."),
        ]
        result = self.fmt({"words": words}, "Hello, world.")
        self.assertEqual(result, "Speaker 0: Hello, world.")

    # --- Multiple speakers ---

    def test_two_speakers_produce_two_lines(self):
        words = [
            self._word("Good", speaker=0),
            self._word("morning", speaker=0),
            self._word("Hi", speaker=1),
            self._word("there", speaker=1),
        ]
        result = self.fmt({"words": words}, "Good morning Hi there")
        lines = result.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("Speaker 0", lines[0])
        self.assertIn("Good morning", lines[0])
        self.assertIn("Speaker 1", lines[1])
        self.assertIn("Hi there", lines[1])

    def test_speaker_change_mid_sequence(self):
        words = [
            self._word("I", speaker=0),
            self._word("agree", speaker=0),
            self._word("Really", speaker=1),
            self._word("Back", speaker=0),
        ]
        result = self.fmt({"words": words}, "I agree Really Back")
        lines = result.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("Speaker 0:"))
        self.assertTrue(lines[1].startswith("Speaker 1:"))
        self.assertTrue(lines[2].startswith("Speaker 0:"))

    def test_three_distinct_speakers(self):
        words = [
            self._word("A", speaker=0),
            self._word("B", speaker=1),
            self._word("C", speaker=2),
        ]
        result = self.fmt({"words": words}, "A B C")
        lines = result.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Speaker 0", lines[0])
        self.assertIn("Speaker 1", lines[1])
        self.assertIn("Speaker 2", lines[2])

    def test_fallback_word_key_used_when_no_punctuated_word(self):
        words = [self._word("hello", speaker=0)]
        result = self.fmt({"words": words}, "hello")
        self.assertIn("hello", result)

    def test_missing_speaker_on_later_word_inherits_current(self):
        # A word without a 'speaker' key mid-stream inherits the current speaker.
        words = [
            self._word("start", speaker=0),
            {"word": "middle"},  # no 'speaker' key
            self._word("end", speaker=1),
        ]
        result = self.fmt({"words": words}, "start middle end")
        # 'start' and 'middle' should be grouped under Speaker 0.
        lines = result.splitlines()
        self.assertTrue(any("start middle" in line for line in lines))
