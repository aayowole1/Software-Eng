"""Speech-to-text helpers used by the meetings app."""

from functools import lru_cache
from pathlib import Path
import wave


MODEL_DIR = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "asr"
    / "sherpa-onnx-streaming-zipformer-bn-vosk-2026-02-09"
)
SAMPLE_RATE = 16_000
FEATURE_DIM = 80


@lru_cache(maxsize=1)
def get_recognizer():
    """Load and cache the meeting transcription recognizer."""
    import sherpa_onnx

    required_files = ("tokens.txt", "encoder.onnx", "decoder.onnx", "joiner.onnx")
    missing_files = [name for name in required_files if not (MODEL_DIR / name).is_file()]
    if missing_files:
        missing = ", ".join(missing_files)
        raise FileNotFoundError(f"Missing STT model files in {MODEL_DIR}: {missing}")

    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(MODEL_DIR / "tokens.txt"),
        encoder=str(MODEL_DIR / "encoder.onnx"),
        decoder=str(MODEL_DIR / "decoder.onnx"),
        joiner=str(MODEL_DIR / "joiner.onnx"),
        num_threads=2,
        sample_rate=SAMPLE_RATE,
        feature_dim=FEATURE_DIM,
        decoding_method="greedy_search",
    )


def transcribe_wav(audio_path: str | Path) -> str:
    """Transcribe a mono, 16-bit PCM WAV file used by a meeting."""
    recognizer = get_recognizer()
    stream = recognizer.create_stream()

    with wave.open(str(audio_path), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError("Meeting audio must be a mono, 16-bit PCM WAV file.")
        if audio.getframerate() != SAMPLE_RATE:
            raise ValueError(f"Meeting audio must use a {SAMPLE_RATE} Hz sample rate.")

        while frames := audio.readframes(4096):
            samples = [
                sample / 32768.0
                for sample in memoryview(frames).cast("h")
            ]
            stream.accept_waveform(SAMPLE_RATE, samples)
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)

    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)

    return recognizer.get_result(stream).strip()
