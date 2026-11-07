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
from datetime import datetime, timezone
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from tqdm.auto import tqdm

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


def judge_summary(reference: dict[str, Any], result: MeetingSummary) -> dict[str, Any]:
    """Ask an LLM whether the generated summary accurately covers the meeting."""
    model = os.getenv("OPENROUTER_JUDGE_MODEL", os.getenv(
        "OPENROUTER_MODEL", "openai/gpt-4o-mini"
    ))
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    reference_actions = json.dumps(
        reference.get("reference_action_items", []), ensure_ascii=False
    )
    prompt = (
        "Evaluate the candidate meeting summary against the reference summary and "
        "reference action items. Return JSON with exactly one field, "
        '"score": 1 if the candidate is accurate, covers the material decisions '
        "and constraints, and does not invent material facts; otherwise return "
        '"score": 0. Treat wording differences as acceptable. The action items '
        "must also be materially consistent with the reference.\n\n"
        f"Reference summary:\n{reference['reference_summary']}\n\n"
        f"Reference action items:\n{reference_actions}\n\n"
        f"Candidate summary:\n{result.summary}\n\n"
        f"Candidate action items:\n{json.dumps(result.action_items, ensure_ascii=False)}"
    )
    try:
        from openai import OpenAI, OpenAIError

        response = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "OrgFlow"),
            },
            timeout=30.0,
            max_retries=2,
        ).chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict binary evaluator of meeting summaries.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
    except ImportError as error:
        raise RuntimeError(f"LLM judging is unavailable: {error}") from error
    except (OpenAIError, OSError, TimeoutError) as error:
        raise RuntimeError(f"LLM judging failed: {error}") from error

    try:
        payload = json.loads(content or "")
        score = payload["score"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError("LLM judge returned invalid JSON.") from error
    if isinstance(score, bool) or not isinstance(score, int) or score not in (0, 1):
        raise RuntimeError("LLM judge returned a score other than 0 or 1.")
    return {"score": score, "model": model}


def summarize_scores(
    reference: dict[str, Any], result: MeetingSummary
) -> dict[str, Any]:
    return {
        "judge": judge_summary(reference, result),
        "action_items": action_item_scores(
            reference.get("reference_action_items", []), result.action_items
        ),
    }


def build_averages(results: list[dict[str, Any]]) -> dict[str, float]:
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
    return averages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("stt", "summarization", "e2e"), default="e2e")
    parser.add_argument("--dataset", type=Path, default=DATA_PATH)
    parser.add_argument("--audio-dir", type=Path, default=DATA_PATH.parent / "audio")
    parser.add_argument("--audio-manifest", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="Directory for timestamped JSON benchmark results.",
    )
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

    for test in tqdm(tests, desc="Benchmarking"):
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
                result["summarization_model"] = os.getenv(
                    "OPENROUTER_MODEL", "openai/gpt-4o-mini"
                )
                summary = summarize_meeting(transcript)
                result["summarization"] = summarize_scores(test["version_b"], summary)
            result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        except (KeyError, FileNotFoundError, RuntimeError, ValueError) as error:
            result["error"] = str(error)
        results.append(result)

    completed = [result for result in results if "error" not in result]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output_dir / f"benchmark_{args.mode}_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": args.mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "averages": build_averages(results),
        "completed_cases": len(completed),
        "total_cases": len(results),
        "cases": results,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "mode": args.mode,
                "overall_score": payload["averages"],
                "completed_cases": len(completed),
                "total_cases": len(results),
                "results_file": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
