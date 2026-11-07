# Meeting benchmark

Run from the repository root:

```bash
python -m meetings.benchmark.run_benchmark --mode summarization
python -m meetings.benchmark.run_benchmark --mode stt --audio-dir meetings/benchmark_data/audio
python -m meetings.benchmark.run_benchmark --mode e2e --audio-dir meetings/benchmark_data/audio
```

The script reads `meetings/benchmark_data/student_org_meeting_benchmark.json`
by default and prints JSON results to the screen. Use `--test-id ORG001` or
`--limit 1` for a smaller run.

STT reports WER, CER, and token precision/recall/F1. Summarization reports
summary-text precision/recall/F1, ROUGE-1/2/L, and METEOR, plus item-level
precision/recall/F1 for action items. ROUGE-L is the most useful single
summary metric here because it rewards overlap while preserving sentence
sequence; ROUGE-1/2 and METEOR provide complementary coverage and fluency
signals. METEOR is implemented with normalized exact-token matches and does
not use synonym resources.

STT and end-to-end modes decode audio through `pydub` and require FFmpeg for
compressed files, as well as `DEEPGRAM_API_KEY`. Summarization and end-to-end
modes require `OPENROUTER_API_KEY`.
