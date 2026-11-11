# Student Organization Officers Meeting Benchmark

## Contents
- `student_org_meeting_benchmark.json`: Full dataset with metadata and schema notes.
- `student_org_meeting_benchmark.jsonl`: One JSON record per test, suitable for streaming and batch evaluation.

## Evaluation modes
1. **STT only**: Feed the recording for a `test_id` to the speech recognizer. Compare its output with `version_a.reference_transcript`. Speaker turns are also available in `version_a.speaker_turns`.
2. **Summarizer only**: Feed `version_a.reference_transcript` to the summarizer. Compare the result with `version_b.reference_summary` and `version_b.reference_action_items`.
3. **End-to-end**: Feed the recording to STT, then pass the STT output directly to the summarizer. Score the intermediate transcript against Version A and the final summary/action items against Version B.

## Generating Audio
By default, the audio files are missing. To generate the audio files, run `generate_audio.py` using the command below. The script relies on Microsoft Edge's TTS service --- and is free to use without needing an API key! It takes ~7 minutes to complete.
```bash
docker exec -it orgflow_web python \
  ./meetings/benchmark_data/generate_audio.py \
  --input ./meetings/benchmark_data/student_org_meeting_benchmark.json \
  --output ./meetings/benchmark_data/audio
```

## Suggested scoring
- **STT**: Word Error Rate (WER), Character Error Rate (CER), and optional speaker-attribution accuracy.
- **Summarization**: factuality, coverage of decisions/constraints, and action-item precision/recall.
- **Action items**: compare owner, task, due date, and priority separately. Do not penalize a system for leaving a deadline unspecified when the meeting did not establish one.
- Normalize harmless punctuation/case differences before computing text metrics. Do not normalize away names, numbers, dates, amounts, or negation.

## Dataset limitations
The dialogue is synthetic and designed for benchmarking. It includes conversational turns, decisions, constraints, explicit and relative deadlines, conditional actions, and occasional unresolved items. It is not a substitute for a naturally sampled production evaluation set.
