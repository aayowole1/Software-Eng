"""Deepgram streaming speech-to-text helpers used by the meetings app."""

import json
import os
from queue import Queue
from threading import Event, Lock, Thread
import time


DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16&sample_rate=16000&channels=1"
    "&model=nova-3&language=en-US&interim_results=true"
    "&smart_format=true&diarize=true&endpointing=500"
)


class DeepgramTranscriber:
    """Stream browser PCM to Deepgram without exposing the API key."""

    def __init__(self):
        api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")

        self.receiver_done = Event()
        self.socket = None

        self.api_key = api_key
        self.audio_queue = Queue()
        self.ready = Event()
        self.closed = Event()
        self.lock = Lock()
        self.final_segments = []
        self.interim_segment = ""
        self.error = None
        self.worker = Thread(target=self._run, daemon=True)
        self.worker.start()
        if not self.ready.wait(timeout=5):
            self.discard()
            raise RuntimeError("Deepgram connection timed out.")
        if self.error:
            error = self.error
            self.discard()
            raise RuntimeError(f"Deepgram connection failed: {error}")

    def add_pcm(self, audio: bytes) -> str:
        if len(audio) % 2:
            raise ValueError(
                "Audio chunks must contain complete 16-bit PCM samples."
            )

        if self.error:
            raise RuntimeError(
                f"Deepgram transcription failed: {self.error}"
            )

        self.audio_queue.put(audio)
        return self.current_result()

    def finish(self) -> str:
        if self.error:
            raise RuntimeError(
                f"Deepgram transcription failed: {self.error}"
            )

        self.audio_queue.put(None)

        # _run() will send CloseStream and wait for the receiver.
        self.worker.join(timeout=65)

        if self.worker.is_alive():
            raise RuntimeError(
                "Deepgram transcription timed out while finalizing."
            )

        if self.error:
            raise RuntimeError(
                f"Deepgram transcription failed: {self.error}"
            )

        return self.current_result()

    def current_result(self) -> str:
        with self.lock:
            return "\n".join(
                segment
                for segment in (*self.final_segments, self.interim_segment)
                if segment
            ).strip()

    def discard(self) -> None:
        self.closed.set()
        self.audio_queue.put(None)
        if self.worker.is_alive():
            self.worker.join(timeout=2)
        with self.lock:
            self.final_segments.clear()
            self.interim_segment = ""

    def _run(self) -> None:
        try:
            import websocket

            socket = websocket.create_connection(
                DEEPGRAM_URL,
                header=[f"Authorization: Token {self.api_key}"],
                timeout=60,
            )
            self.socket = socket
            self.ready.set()

            receiver = Thread(
                target=self._receive,
                args=(socket,),
                daemon=True,
            )
            receiver.start()

            while not self.closed.is_set():
                audio = self.audio_queue.get()

                if audio is None:
                    # Tell Deepgram that no more audio is coming.
                    socket.send(json.dumps({"type": "CloseStream"}))

                    # Give Deepgram time to send all final Results.
                    self.receiver_done.wait(timeout=60)

                    socket.close()
                    receiver.join(timeout=2)
                    return

                socket.send(
                    audio,
                    opcode=websocket.ABNF.OPCODE_BINARY,
                )

        except Exception as error:
            self.error = error
            self.ready.set()

    def _receive(self, socket) -> None:
        try:
            while not self.closed.is_set():
                raw_message = socket.recv()

                # Normal WebSocket EOF.
                if raw_message == "":
                    return

                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        f"Deepgram returned a non-JSON message: {raw_message!r}"
                    ) from error

                if message.get("type") != "Results":
                    if message.get("type") == "Error":
                        raise RuntimeError(
                            message.get("description", "Deepgram error")
                        )
                    continue

                alternatives = message.get("channel", {}).get(
                    "alternatives", []
                )
                if not alternatives:
                    continue

                alternative = alternatives[0]
                text = alternative.get("transcript", "").strip()

                if not text:
                    continue

                formatted = self._format_speakers(
                    alternative,
                    text,
                )

                with self.lock:
                    if message.get("is_final"):
                        self.final_segments.append(formatted)
                        self.interim_segment = ""
                    else:
                        self.interim_segment = formatted

        except Exception as error:
            if not self.closed.is_set():
                self.error = error

        finally:
            self.receiver_done.set()

    @staticmethod
    def _format_speakers(alternative: dict, text: str) -> str:
        print(alternative, text)
        words = alternative.get("words", [])
        if not words or "speaker" not in words[0]:
            return text

        grouped = []
        current_speaker = words[0].get("speaker")
        current_words = []

        for word in words:
            speaker = word.get("speaker", current_speaker)

            if speaker != current_speaker and current_words:
                grouped.append(
                    f"Speaker {current_speaker}: "
                    f"{' '.join(current_words)}"
                )
                current_speaker = speaker
                current_words = []

            current_words.append(
                word.get("punctuated_word", word.get("word", ""))
            )

        if current_words:
            grouped.append(
                f"Speaker {current_speaker}: "
                f"{' '.join(current_words)}"
            )

        return "\n".join(grouped) or text
