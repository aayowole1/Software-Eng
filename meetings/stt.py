"""Deepgram speech-to-text helpers used by the meetings app."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
import time


DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16&sample_rate=16000&channels=1"
    "&model=nova-3&language=en-US&interim_results=true"
    "&smart_format=true&diarize=true&endpointing=500"
)


class DeepgramTranscriber:
    """Save temporary PCM audio, transcribe it once, then delete the file."""

    def __init__(self):
        api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")

        self.api_key = api_key
        self.lock = Lock()
        self.audio_file = NamedTemporaryFile(
            mode="wb",
            suffix=".pcm",
            prefix="orgflow-meeting-",
            delete=False,
        )
        self.audio_path = Path(self.audio_file.name)
        self.transcript = ""
        self.finished = False

    def add_pcm(self, audio: bytes) -> str:
        if len(audio) % 2:
            raise ValueError("Audio chunks must contain complete 16-bit PCM samples.")

        with self.lock:
            if self.finished:
                raise RuntimeError("This recording has already been finalized.")
            self.audio_file.write(audio)
            self.audio_file.flush()
        return self.transcript

    def finish(self) -> str:
        with self.lock:
            if self.finished:
                return self.transcript
            self.finished = True
            self.audio_file.close()

        try:
            self.transcript = self._transcribe_file()
            return self.transcript
        finally:
            self._delete_audio_file()

    def current_result(self) -> str:
        return self.transcript

    def discard(self) -> None:
        with self.lock:
            if not self.audio_file.closed:
                self.audio_file.close()
            self.finished = True
        self._delete_audio_file()

    def _transcribe_file(self) -> str:
        try:
            import websocket

            socket = websocket.create_connection(
                DEEPGRAM_URL,
                header=[f"Authorization: Token {self.api_key}"],
                timeout=10,
            )
            results = []
            with self.audio_path.open("rb") as audio:
                while chunk := audio.read(64 * 1024):
                    socket.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
            socket.send(json.dumps({"type": "CloseStream"}))

            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                socket.settimeout(max(1, deadline - time.monotonic()))
                raw_message = socket.recv()
                if raw_message == "":
                    break
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        f"Deepgram returned a non-JSON message: {raw_message!r}"
                    ) from error
                if message.get("type") == "Error":
                    raise RuntimeError(message.get("description", "Deepgram error"))
                if message.get("type") != "Results" or not message.get("is_final"):
                    continue
                alternatives = message.get("channel", {}).get("alternatives", [])
                if alternatives:
                    alternative = alternatives[0]
                    text = alternative.get("transcript", "").strip()
                    if text:
                        results.append(self._format_speakers(alternative, text))
            socket.close()
            return "\n".join(results).strip()
        except Exception as error:
            raise RuntimeError(f"Deepgram transcription failed: {error}") from error

    def _delete_audio_file(self) -> None:
        try:
            self.audio_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _format_speakers(alternative: dict, text: str) -> str:
        words = alternative.get("words", [])
        if not words or "speaker" not in words[0]:
            return text

        grouped = []
        current_speaker = words[0].get("speaker")
        current_words = []
        for word in words:
            speaker = word.get("speaker", current_speaker)
            if speaker != current_speaker and current_words:
                grouped.append(f"Speaker {current_speaker}: {' '.join(current_words)}")
                current_speaker = speaker
                current_words = []
            current_words.append(word.get("punctuated_word", word.get("word", "")))
        if current_words:
            grouped.append(f"Speaker {current_speaker}: {' '.join(current_words)}")
        return "\n".join(grouped) or text
