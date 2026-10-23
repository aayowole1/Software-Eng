import re
from pathlib import Path

import jiwer
from django.test import SimpleTestCase

from meetings.stt import transcribe_wav


TESTDATA_DIR = Path(__file__).resolve().parents[1] / "testdata"


def normalize(text: str) -> str:
    """Normalize text consistently before comparing transcripts."""
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()

class SttAudioTests(SimpleTestCase):
    def test_single_speaker_audio_matches_expected_transcription(self):
        audio_path = TESTDATA_DIR / "single_speaker.wav"
        expected_path = TESTDATA_DIR / "single_speaker.txt"

        hypothesis = normalize(transcribe_wav(audio_path))
        reference = normalize(expected_path.read_text(encoding="utf-8").strip())

        max_wer = 0.10  # 10%
        max_cer = 0.10  # 10%   # TODO: a bit lax, but can tighten later

        result = jiwer.process_words(reference, hypothesis)
        cer = jiwer.cer(reference, hypothesis)

        self.assertLessEqual(
            result.wer,
            max_wer,
            msg=f"WER {result.wer:.2%} exceeds {max_wer:.0%}",
        )

        self.assertLessEqual(
            cer,
            max_cer,
            msg=f"CER {cer:.2%} exceeds {max_cer:.0%}",
        )

