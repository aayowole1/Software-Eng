import json
import os
import re
import struct
import wave
from pathlib import Path
from unittest import skipUnless

import jiwer
from django.test import SimpleTestCase

from meetings.stt import DeepgramTranscriber


TESTDATA_DIR = Path(__file__).resolve().parents[1] / "testdata"
HAS_DEEPGRAM_KEY = bool(os.getenv("DEEPGRAM_API_KEY"))


def normalize(text: str) -> str:
    text = re.sub(r"\bSpeaker\s+\d+:\s*", "", text, flags=re.IGNORECASE)
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def multi_speaker_reference() -> str:
    entries = [
        json.loads(line)
        for line in (TESTDATA_DIR / "multi_speakers.jsonl").read_text().splitlines()
    ]
    return " ".join(entry["text"] for entry in entries)


def transcribe_wav(path: Path) -> str:
    transcriber = DeepgramTranscriber()
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.readframes(audio.getnframes())
            pcm = to_mono_16khz(
                frames,
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
            )
            for offset in range(0, len(pcm), 16_000 * 2):
                transcriber.add_pcm(pcm[offset : offset + 16_000 * 2])
        return transcriber.finish()
    finally:
        transcriber.discard()


def to_mono_16khz(
    frames: bytes,
    channels: int,
    sample_width: int,
    sample_rate: int,
) -> bytes:
    """Convert fixture PCM to the format expected by Deepgram."""
    if channels < 1 or sample_width not in (1, 2, 3, 4):
        raise ValueError("Unsupported WAV format.")
    frame_width = channels * sample_width
    frame_count = len(frames) // frame_width
    mono = []
    for frame_start in range(0, len(frames), frame_width):
        channel_values = []
        for channel in range(channels):
            start = frame_start + channel * sample_width
            raw = frames[start : start + sample_width]
            if sample_width == 1:
                value = (raw[0] - 128) * 256
            elif sample_width == 2:
                value = struct.unpack_from("<h", raw)[0]
            elif sample_width == 3:
                value = int.from_bytes(raw, "little", signed=True) >> 8
            else:
                value = struct.unpack_from("<i", raw)[0] >> 16
            channel_values.append(value)
        mono.append(sum(channel_values) // len(channel_values))

    if sample_rate == 16_000:
        return b"".join(struct.pack("<h", max(-32768, min(32767, value))) for value in mono)

    output_count = round(frame_count * 16_000 / sample_rate)
    output = bytearray()
    for index in range(output_count):
        source_position = index * (frame_count - 1) / max(output_count - 1, 1)
        left = int(source_position)
        right = min(left + 1, frame_count - 1)
        fraction = source_position - left
        value = round(mono[left] + (mono[right] - mono[left]) * fraction)
        output.extend(struct.pack("<h", max(-32768, min(32767, value))))
    return bytes(output)


@skipUnless(HAS_DEEPGRAM_KEY, "Set DEEPGRAM_API_KEY to run Deepgram STT integration tests.")
class DeepgramSttTests(SimpleTestCase):
    def assert_transcription_quality(self, audio_path: Path, reference: str, label: str):

        hypothesis_raw = transcribe_wav(audio_path)
        # print(f"\n{label} RAW TRANSCRIPT:")
        # print(hypothesis_raw)
        # print()

        hypothesis = normalize(hypothesis_raw)

        reference = normalize(reference)
        result = jiwer.process_words(reference, hypothesis)
        cer = jiwer.cer(reference, hypothesis)
        print(f"{label}: WER={result.wer:.2%}, CER={cer:.2%}")
        self.assertLessEqual(result.wer, 0.35, f"{label} WER {result.wer:.2%} exceeds 35%")
        self.assertLessEqual(cer, 0.25, f"{label} CER {cer:.2%} exceeds 25%")

    def test_single_speaker_audio_quality(self):
        self.assert_transcription_quality(
            TESTDATA_DIR / "single_speaker.wav",
            (TESTDATA_DIR / "single_speaker.txt").read_text(encoding="utf-8"),
            "single-speaker",
        )

    def test_multi_speaker_audio_quality(self):
        self.assert_transcription_quality(
            TESTDATA_DIR / "multi_speakers.wav",
            multi_speaker_reference(),
            "multi-speaker",
        )
