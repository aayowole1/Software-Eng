#!/usr/bin/env python3
"""
Generate one multi-speaker MP3 per meeting in the student-org benchmark.

Input:
  student_org_meeting_benchmark.json

Install:
  python -m pip install edge-tts pydub
  Install FFmpeg and make sure `ffmpeg` is on PATH.

Run:
  python generate_audio.py \
    --input student_org_meeting_benchmark.json \
    --output audio

The script uses Microsoft Edge's online neural voices through edge-tts.
It is free to use without an API key, but requires an internet connection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import shutil
import tempfile
from pathlib import Path

import edge_tts
from pydub import AudioSegment


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


async def get_english_voices():
    voices = await edge_tts.list_voices()
    # Keep neural English voices. Edge's voice list includes locale and gender.
    candidates = [
        v for v in voices
        if str(v.get("Locale", "")).startswith("en-")
        and "Neural" in str(v.get("Name", ""))
    ]
    if not candidates:
        raise RuntimeError("No English neural voices were returned by edge-tts.")
    return candidates


def assign_voices(speakers, voice_pool, rng):
    """
    Pick distinct voices within each test. Rotate/shuffle the pool across tests
    so the same speaker label does not always get the same voice.
    """
    pool = list(voice_pool)
    rng.shuffle(pool)
    if len(pool) < len(speakers):
        raise RuntimeError(
            f"Only {len(pool)} English voices available for "
            f"{len(speakers)} speakers in one test."
        )
    return {
        speaker: pool[i]["Name"]
        for i, speaker in enumerate(speakers)
    }


async def synthesize_turn(text, voice, destination, rate, volume):
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        volume=volume,
    )
    await communicate.save(str(destination))


async def build_test_audio(test, voice_pool, output_dir, rng, rate, volume, pause_ms):
    test_id = test["test_id"]
    turns = test.get("version_a", {}).get("speaker_turns")
    if not turns:
        raise ValueError(f"{test_id}: missing version_a.speaker_turns")

    speakers = list(dict.fromkeys(turn["speaker"] for turn in turns))
    voice_map = assign_voices(speakers, voice_pool, rng)

    # Render each turn separately, then join with a short natural pause.
    combined = AudioSegment.empty()
    turn_manifest = []

    with tempfile.TemporaryDirectory(prefix=f"{safe_name(test_id)}_") as tmp:
        tmp_dir = Path(tmp)

        for index, turn in enumerate(turns, start=1):
            speaker = turn["speaker"]
            text = turn["text"].strip()
            if not text:
                continue

            clip_path = tmp_dir / f"turn_{index:03d}.mp3"
            await synthesize_turn(
                text=text,
                voice=voice_map[speaker],
                destination=clip_path,
                rate=rate,
                volume=volume,
            )

            clip = AudioSegment.from_file(clip_path, format="mp3")
            combined += clip
            if index != len(turns):
                combined += AudioSegment.silent(duration=pause_ms)

            turn_manifest.append({
                "turn": index,
                "speaker": speaker,
                "voice": voice_map[speaker],
                "text_characters": len(text),
            })

    combined = combined.set_frame_rate(24000).set_channels(1)
    destination = output_dir / f"{safe_name(test_id)}.mp3"
    combined.export(
        destination,
        format="mp3",
        bitrate="128k",
        parameters=["-write_xing", "0"],
    )

    return {
        "test_id": test_id,
        "topic": test.get("topic"),
        "audio_file": destination.name,
        "duration_seconds": round(len(combined) / 1000, 2),
        "speaker_voices": voice_map,
        "turns": turn_manifest,
    }


async def main():
    parser = argparse.ArgumentParser(description="Generate benchmark meeting audio.")
    parser.add_argument("--input", required=True, help="Benchmark JSON file")
    parser.add_argument("--output", default="audio", help="Output directory")
    parser.add_argument("--seed", type=int, default=2026, help="Voice assignment seed")
    parser.add_argument("--rate", default="+0%", help="Speech rate, e.g. -5%% or +3%%")
    parser.add_argument("--volume", default="+0%", help="Voice volume, e.g. +0%%")
    parser.add_argument("--pause-ms", type=int, default=450, help="Pause between turns")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit; 0 means all tests")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg and ensure `ffmpeg` is on PATH."
        )

    data = json.loads(input_path.read_text(encoding="utf-8"))
    tests = data["tests"]
    if args.limit:
        tests = tests[:args.limit]

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching available English neural voices...")
    voices = await get_english_voices()
    print(f"Found {len(voices)} English neural voices.")

    rng = random.Random(args.seed)
    manifest = {
        "dataset_name": data.get("dataset_name", "student_org_meeting_benchmark"),
        "tts_engine": "Microsoft Edge Neural TTS via edge-tts",
        "voice_assignment_seed": args.seed,
        "audio_format": "MP3, mono, 24 kHz, 128 kbps",
        "pause_between_turns_ms": args.pause_ms,
        "tests": [],
    }

    for i, test in enumerate(tests, start=1):
        print(f"[{i}/{len(tests)}] Generating {test['test_id']} — {test.get('topic', '')}")
        result = await build_test_audio(
            test=test,
            voice_pool=voices,
            output_dir=output_dir,
            rng=rng,
            rate=args.rate,
            volume=args.volume,
            pause_ms=args.pause_ms,
        )
        manifest["tests"].append(result)
        print(f"    Saved {result['audio_file']} ({result['duration_seconds']} sec)")

    manifest_path = output_dir / "audio_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nDone. Audio and manifest saved in: {output_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
