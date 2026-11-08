# Meeting benchmark

Run from the repository root:

```bash
python -m meetings.benchmark.run_benchmark --mode summarization
python -m meetings.benchmark.run_benchmark --mode stt --audio-dir meetings/benchmark_data/audio
python -m meetings.benchmark.run_benchmark --mode e2e --audio-dir meetings/benchmark_data/audio
```

The script reads `meetings/benchmark_data/student_org_meeting_benchmark.json`
by default, writes complete timestamped JSON results to
`meetings/benchmark/results/`, and prints only aggregate results to the screen.
Use `--test-id ORG001` or `--limit 1` for a smaller run. Change the output
directory with `--output-dir`.

STT reports WER, CER, and token precision/recall/F1. Summarization uses a
second LLM call as a 1–5 judge: `5` means the summary and action items are
faithful, complete, and precise; `1` means they are unusable. The result
records both the summarization model (`OPENROUTER_MODEL`) and judge model
(`OPENROUTER_JUDGE_MODEL`, defaulting to the summarization model), along with
the average judge score and item-level precision/recall/F1 for action items under
`action_item_metrics`. The summarizer is required to return both a `summary`
and an `action_items` array. Each saved case includes:

```json
{
  "prediction": {
    "summary": "...",
    "action_items": ["Action: ..."]
  },
  "ground_truth": {
    "summary": "...",
    "action_items": [{"owner": "...", "task": "...", "due": "...", "priority": "..."}]
  },
  "action_item_metrics": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0
  }
}
```

This makes the generated action items and their ground truth available for
manual verification of both extraction quality and judge decisions. The shared
summarization and judge prompt builders live in `meetings/ai.py`; the benchmark
uses the same judge instructions as the application rather than duplicating
prompt text.

STT and end-to-end modes decode audio through `pydub` and require FFmpeg for
compressed files, as well as `DEEPGRAM_API_KEY`. Summarization and end-to-end
modes require `OPENROUTER_API_KEY`.
