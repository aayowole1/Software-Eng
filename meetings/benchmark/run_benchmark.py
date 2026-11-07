#!/usr/bin/env python3
"""Benchmark the meeting STT, summarization, and end-to-end pipelines.

Examples:
    python -m meetings.benchmark.run_benchmark --mode stt \
        --audio-dir meetings/benchmark_data/audio
    python -m meetings.benchmark.run_benchmark --mode summarization
    python -m meetings.benchmark.run_benchmark --mode e2e \
        --audio-dir meetings/benchmark_data/audio

STT and end-to-end modes require DEEPGRAM_API_KEY. Summarization and
end-to-end modes require OPENROUTER_API_KEY. The default audio directory is
the ``audio`` subdirectory of the benchmark data directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

try:
    from ..ai import MeetingSummary, summarize_meeting
    from ..stt import DeepgramTranscriber
except ImportError:  # Allows running this file directly from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from meetings.ai import MeetingSummary, summarize_meeting
    from meetings.stt import DeepgramTranscriber


DATA_PATH = Path(__file__).resolve().parents[1] / "benchmark_data" / (
    "student_org_meeting_benchmark.json"
)
AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)


def normalize_text(text: str) -> str:
    """Normalize case and punctuation without removing meaningful words/numbers."""
    return " ".join(TOKEN_PATTERN.findall(text.casefold()))


def tokens(text: str) -> list[str]:
    return normalize_text(text).split()


def overlap_scores(reference: str, candidate: str) -> dict[str, float]:
    """Return multiset token precision, recall, and F1."""
    reference_counts = Counter(tokens(reference))
    candidate_counts = Counter(tokens(candidate))
    matches = sum((reference_counts & candidate_counts).values())
    precision = matches / sum(candidate_counts.values()) if candidate_counts else 0.0
    recall = matches / sum(reference_counts.values()) if reference_counts else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _lcs_length(first: list[str], second: list[str]) -> int:
    previous = [0] * (len(second) + 1)
    for first_token in first:
        current = [0]
        for index, second_token in enumerate(second, start=1):
            current.append(
                previous[index - 1] + 1
                if first_token == second_token
                else max(previous[index], current[index - 1])
            )
        previous = current
    return previous[-1]


def rouge_scores(reference: str, candidate: str) -> dict[str, float]:
    """Calculate ROUGE-1, ROUGE-2, and ROUGE-L F1 scores."""
    reference_tokens = tokens(reference)
    candidate_tokens = tokens(candidate)
    scores: dict[str, float] = {}
    for name, size in (("rouge1", 1), ("rouge2", 2)):
        reference_ngrams = Counter(
            tuple(reference_tokens[index : index + size])
            for index in range(len(reference_tokens) - size + 1)
        )
        candidate_ngrams = Counter(
            tuple(candidate_tokens[index : index + size])
            for index in range(len(candidate_tokens) - size + 1)
        )
        matches = sum((reference_ngrams & candidate_ngrams).values())
        precision = matches / sum(candidate_ngrams.values()) if candidate_ngrams else 0.0
        recall = matches / sum(reference_ngrams.values()) if reference_ngrams else 0.0
        scores[name] = _f1(precision, recall)

    lcs = _lcs_length(reference_tokens, candidate_tokens)
    precision = lcs / len(candidate_tokens) if candidate_tokens else 0.0
    recall = lcs / len(reference_tokens) if reference_tokens else 0.0
    scores["rougeL"] = _f1(precision, recall)
    return scores


def meteor_score(reference: str, candidate: str) -> float:
    """Calculate a dependency-free unigram METEOR approximation.

    This uses exact normalized-token matches and the standard METEOR
    harmonic-mean and chunk penalty. It intentionally does not claim synonym
    matching, which would require a language resource or model.
    """
    reference_tokens = tokens(reference)
    candidate_tokens = tokens(candidate)
    remaining = Counter(reference_tokens)
    matched_candidate_indices: list[int] = []
    for index, token in enumerate(candidate_tokens):
        if remaining[token]:
            remaining[token] -= 1
            matched_candidate_indices.append(index)
    matches = len(matched_candidate_indices)
    if not matches or not reference_tokens or not candidate_tokens:
        return 0.0

    precision = matches / len(candidate_tokens)
    recall = matches / len(reference_tokens)
    harmonic = (10 * precision * recall) / (recall + 9 * precision)
    chunks = 1
    for previous, current in zip(matched_candidate_indices, matched_candidate_indices[1:]):
        if current != previous + 1:
            chunks += 1
    return harmonic * (1 - 0.5 * (chunks / matches) ** 3)


def action_item_scores(
    reference_items: Iterable[dict[str, Any]], candidate_items: Iterable[str]
) -> dict[str, float]:
    """Score action-item retrieval using greedy item-level token-F1 matching."""
    references = [
        " ".join(
            str(item.get(field, ""))
            for field in ("owner", "task", "due", "priority")
        )
        for item in reference_items
    ]
    candidates = [re.sub(r"^(Action:|TODO:|- \[ \])\s*", "", item).strip() for item in candidate_items]
    unmatched = set(range(len(references)))
    matches = 0
    for candidate in candidates:
        best_index = None
        best_score = 0.0
        for index in unmatched:
            score = overlap_scores(references[index], candidate)["f1"]
            if score > best_score:
                best_index, best_score = index, score
        if best_index is not None and best_score >= 0.5:
            unmatched.remove(best_index)
            matches += 1
    precision = matches / len(candidates) if candidates else 0.0
    recall = matches / len(references) if references else 0.0
    return {"precision": precision, "recall": recall, "f1": _f1(precision, recall)}


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    tests = payload.get("tests") if isinstance(payload, dict) else payload
    if not isinstance(tests, list):
        raise ValueError(f"{path} does not contain a list of benchmark tests.")
    return tests


def load_audio_manifest(path: Path) -> dict[str, Path]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["test_id"]: path.parent / item["audio_file"]
        for item in payload.get("tests", [])
        if item.get("test_id") and item.get("audio_file")
    }


def find_audio(test_id: str, audio_dir: Path, manifest: dict[str, Path]) -> Path:
    if test_id in manifest:
        return manifest[test_id]
    for extension in AUDIO_EXTENSIONS:
        candidate = audio_dir / f"{test_id}{extension}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No audio found for {test_id}. Generate audio or provide --audio-dir."
    )


def transcribe(audio_path: Path) -> str:
    try:
        from pydub import AudioSegment
    except ImportError as error:
        raise RuntimeError(
            "Audio decoding requires pydub; install the project requirements "
            "and ensure FFmpeg is available for compressed audio."
        ) from error

    audio = AudioSegment.from_file(audio_path).set_frame_rate(16000).set_channels(1).set_sample_width(2)
    transcriber = DeepgramTranscriber()
    try:
        transcriber.add_pcm(audio.raw_data)
        return transcriber.finish()
    except Exception:
        transcriber.discard()
        raise


def stt_scores(reference: str, candidate: str) -> dict[str, float]:
    try:
        from jiwer import cer, wer
    except ImportError as error:
        raise RuntimeError("STT scoring requires jiwer from requirements.txt.") from error
    scores = overlap_scores(reference, candidate)
    scores["wer"] = wer(reference, candidate)
    scores["cer"] = cer(reference, candidate)
    return scores


def summarize_scores(reference: dict[str, Any], result: MeetingSummary) -> dict[str, Any]:
    summary_reference = reference["reference_summary"]
    return {
        "summary": {
            **overlap_scores(summary_reference, result.summary),
            **rouge_scores(summary_reference, result.summary),
            "meteor": meteor_score(summary_reference, result.summary),
        },
        "action_items": action_item_scores(
            reference.get("reference_action_items", []), result.action_items
        ),
    }


def print_results(mode: str, results: list[dict[str, Any]]) -> None:
    completed = [result for result in results if "error" not in result]
    numeric_values: dict[str, list[float]] = {}

    def collect(value: Any, prefix: str = "") -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            numeric_values.setdefault(prefix, []).append(float(value))
        elif isinstance(value, dict):
            for key, nested in value.items():
                collect(nested, f"{prefix}.{key}" if prefix else key)

    for result in completed:
        collect(result)
    averages = {
        key: round(sum(values) / len(values), 4)
        for key, values in numeric_values.items()
        if key != "elapsed_seconds"
    }
    print(
        json.dumps(
            {"mode": mode, "averages": averages, "cases": results},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nCompleted {len(completed)}/{len(results)} benchmark cases.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("stt", "summarization", "e2e"), default="e2e")
    parser.add_argument("--dataset", type=Path, default=DATA_PATH)
    parser.add_argument("--audio-dir", type=Path, default=DATA_PATH.parent / "audio")
    parser.add_argument("--audio-manifest", type=Path)
    parser.add_argument("--test-id", action="append", dest="test_ids")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    tests = load_dataset(args.dataset)
    if args.test_ids:
        tests = [test for test in tests if test.get("test_id") in args.test_ids]
    if args.limit:
        tests = tests[: args.limit]
    manifest_path = args.audio_manifest or args.audio_dir / "audio_manifest.json"
    manifest = load_audio_manifest(manifest_path)
    results = []

    for test in tests:
        test_id = test.get("test_id", "<unknown>")
        started = time.perf_counter()
        result: dict[str, Any] = {"test_id": test_id, "topic": test.get("topic")}
        try:
            reference_transcript = test["version_a"]["reference_transcript"]
            transcript = reference_transcript
            if args.mode in ("stt", "e2e"):
                transcript = transcribe(find_audio(test_id, args.audio_dir, manifest))
                result["stt"] = stt_scores(reference_transcript, transcript)
            if args.mode in ("summarization", "e2e"):
                summary = summarize_meeting(transcript)
                result["summarization"] = summarize_scores(test["version_b"], summary)
            result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        except (KeyError, FileNotFoundError, RuntimeError, ValueError) as error:
            result["error"] = str(error)
        results.append(result)
        print(f"Completed {test_id}.", file=sys.stderr)

    print_results(args.mode, results)


if __name__ == "__main__":
    main()
