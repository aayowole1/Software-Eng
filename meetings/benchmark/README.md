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
second LLM call as a binary judge: `1` means the summary and action items are
accurate and materially complete, while `0` means they are not. The result
records both the summarization model (`OPENROUTER_MODEL`) and judge model
(`OPENROUTER_JUDGE_MODEL`, defaulting to the summarization model), along with
item-level precision/recall/F1 for action items. Each saved case includes the
full summarizer `prediction` and corresponding `ground_truth` summary and
action items so judge decisions can be manually reviewed.

STT and end-to-end modes decode audio through `pydub` and require FFmpeg for
compressed files, as well as `DEEPGRAM_API_KEY`. Summarization and end-to-end
modes require `OPENROUTER_API_KEY`.
