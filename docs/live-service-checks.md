# Live-service prerequisites and owner checks

Current checkpoint: **pending owner configuration**, 2026-10-25 (America/Chicago). The user chose to leave live-provider checks pending for their owners. No paid provider request, member-data upload, Google login, or real email delivery was performed by this check.

This checker belongs to the **combined integration preview only** (`OrgFlow-Integration-Preview`), whose meeting summarizer uses OpenAI. The primary task branch retains a rule-based summarizer; running this checker there would not establish its application's OpenAI integration. Run from the combined preview repository root with the application's Python environment:

```powershell
python deploy/check_live_services.py --output ..\tmp\orgflow_deployment_20261025\provider-prerequisites.json
```

The default is a diagnostic, not a deployment acceptance test. It reads process settings and the repository's private `.env` when `python-dotenv` is installed; process settings take precedence. It emits configuration **presence booleans only**, checks dependency availability, and performs certificate-verified TLS handshakes to fixed OpenAI, Deepgram, and Google hosts. It does not import Django settings, access a database, authenticate, send email, or transmit notes/audio. `--no-network` skips those TLS handshakes. Exit code 0 means the diagnostic report was generated; individual `blocked` states remain blocked.

The report generated for this checkpoint records:

| Check | Actual result | Remaining owner input |
|---|---|---|
| OpenAI | Blocked: no key; `openai` unavailable in the checked app environment | Private `OPENAI_API_KEY`, funded/model-enabled account, install declared requirements, authorize one synthetic probe |
| Deepgram | Blocked: no key; `websocket` unavailable | Private `DEEPGRAM_API_KEY`, funded account, install declared requirements, new confirmed synthetic WAV |
| Google | Blocked: no client ID or browser origin supplied in this preview | Web client ID and exact authorized JavaScript origin; complete browser login with the intended test account |
| SMTP | Blocked: real-delivery settings absent | SMTP policy/backend, host, valid port, TLS or SSL, user/password, sender and an owned test mailbox |
| Network | Verified TLS 1.3 handshakes succeeded for all five fixed hosts | Authentication, quota, delivery and application behavior remain unverified |

The checked hosts are `api.openai.com`, `api.deepgram.com`, `accounts.google.com`, `oauth2.googleapis.com`, and `www.googleapis.com`. Successful TLS proves reachability and server-certificate validation. It does not establish API access, token verification, billing, DNS configuration of the deployment, or an OAuth allowlist match. Keep private values in the deployment's secret settings; never paste them into a report or commit `.env`.

## Optional synthetic provider probes

These are prepared for an owner to run later. **Do not run them as part of the ordinary suite.** Both `--live` and the explicit process environment value below are required. A missing prerequisite prevents all selected provider probes before any call is made. `--service` defaults to `both`; choose a single provider to configure and check independently.

```powershell
# Set privately supplied provider credentials outside this example.
$env:ORGFLOW_ALLOW_LIVE_CHECKS = 'synthetic-only'
python deploy/check_live_services.py --live --service openai --output ..\tmp\orgflow_deployment_20261025\openai-synthetic.json
python deploy/check_live_services.py --live --service deepgram --audio C:\private-test-audio\new-synthetic-check.wav --synthetic-audio-confirmed --output ..\tmp\orgflow_deployment_20261025\deepgram-synthetic.json
Remove-Item Env:ORGFLOW_ALLOW_LIVE_CHECKS
```

The OpenAI probe uses a built-in fictional note of fewer than 100 words containing two explicit actions. It invokes the current `meetings.ai.summarize_meeting` prompt/parser with a **temporary child-process client wrapper**: one SDK invocation, automatic retries disabled, 250 maximum output tokens, and a 20-second client timeout. It checks the parsed summary and two known actions. It does not change the application's provider implementation. The parent stops the child after 30 seconds. Only status, counts and elapsed time are recorded; no key, provider response text or transcript is printed. The token limits bound usage, not a guaranteed currency amount. A timeout may still have been billed: inspect the provider account before considering a manual retry.

The Deepgram probe requires an operator-confirmed **new synthetic** WAV: uncompressed signed 16-bit PCM, mono, 16 kHz, nonempty and at most 20 seconds (640,000 PCM bytes). The file must be at most 1 MB. The checker refuses repository `meetings/testdata` audio, whose provenance is not documented. Generate speech locally with an offline voice tool and an invented sentence; do not substitute a member recording. A confirmation flag is an operator assertion, not an automated rights/consent determination. The checker calls the current adapter once, records nonempty final text and temporary-file cleanup, and applies the same 30-second child wall limit. It makes no automatic retry. Its scratch directory is removed by the parent even after a killed child. A nonempty transcript establishes one provider round trip; it does **not** establish word accuracy, diarization, browser microphone behavior, or end-to-end meeting approval/import.

No live result exists for this checkpoint. Do not replace `blocked`/`pending` with `passed` until an actual sanitized owner receipt is retained. Live mode exits 2 for a missing gate, failed probe or timeout.

## Google and SMTP completion

For Google, supply the intended browser origin, for example `--origin https://orgflow.example.edu` or local `--origin http://localhost:8000`. The checker validates an origin with no path, trailing slash, user information, query or fragment; HTTPS is required except HTTP localhost development. Google Cloud must contain the **exact scheme, host and port** in the web client's Authorized JavaScript origins. For local development Google instructs adding both `http://localhost` and `http://localhost:<port>`. The script cannot inspect that private allowlist. A valid origin string or public-certificate handshake is not a successful sign-in. The owner must complete and record the intended browser/account flow and the project's strict verified-email policy. [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).

For SMTP, select production `DJANGO_EMAIL_POLICY=smtp` (production settings choose the backend), or explicitly select `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` when no production policy is supplied. An explicit disabled/invalid policy does not count as SMTP even if the backend variable is present. Configure `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL`. The authenticated secure route this checker recognizes requires exactly one of `EMAIL_USE_TLS=true` or `EMAIL_USE_SSL=true`; both on or both off are blocked. Defaults match production: TLS true, SSL false, port 587 (465 for SSL). For implicit SSL, explicitly set `EMAIL_USE_TLS=false` and `EMAIL_USE_SSL=true`. An explicit `EMAIL_PORT` must be valid. Presence booleans include policy, backend, TLS and SSL; no values are echoed.

A relay without paired credentials or with a different security policy needs a separate owner assessment. Console email and the disposable CI capture service do not prove external delivery. This script never sends email, including in live mode. An owner must request a password reset for an owned synthetic test account/mailbox and verify delivery and usable HTTPS links without retaining reset tokens in evidence.

## Timing and deployment limits

The application and the bounded checker have different limits:

| Path | Current source behavior | Interpretation |
|---|---|---|
| `meetings/ai.py` | SDK timeout 30 seconds, `max_retries=2`, no output-token cap | Up to three attempts plus backoff; SDK phase/inactivity timeouts are not an overall deadline. No 30-second end-to-end guarantee. |
| `meetings/stt.py` | 10-second connection timeout; 60-second receive deadline starts after audio send | Connect, file-send and processing time are additional. No 30-second end-to-end guarantee. |
| Optional checker | One adapter invocation per selected provider; 30-second child wall cutoff | Bounded smoke only. Killing a client does not prove provider cancellation or zero billing. |

The current transcription adapter buffers PCM locally and calls Deepgram after Stop; requested interim results do not establish live incremental browser text. Active recordings live in the process-local `meetings.views._active_recordings` dictionary. Demonstrate this path with **one application worker**; multiworker routing, worker restart, abandoned-file cleanup, load and continuous transcription require separate owner work/evidence. The configured `nova-3` raw-audio parameters match Deepgram's documented linear16/sample-rate requirements. [Deepgram encoding](https://developers.deepgram.com/docs/encoding/).

The OpenAI default is `gpt-4o-mini` via Chat Completions JSON mode. JSON mode provides parseable JSON, not schema adherence; the application performs its own field validation. OpenAI lists the GPT-4o mini snapshot for shutdown on **January 14, 2027**. Record model migration as future maintenance and retest the replacement's parameters/output; this is not evidence that the November 1 team target is unsupported, and no model migration was made here. [Model compatibility](https://developers.openai.com/api/docs/models/gpt-4o-mini), [JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat), [deprecation schedule](https://developers.openai.com/api/docs/deprecations).

Existing Deepgram quality tests automatically run when a nonempty key is present at import time. Keep both provider keys unset in ordinary/offline suites. The two recordings total 165.664 seconds and use WER ≤35% / CER ≤25%; speaker labels are removed, so they do not validate diarization. Do not upload those recordings without documented rights/provenance. The optional synthetic smoke also does not replace these quality goals, the project benchmark, accessibility/usability evaluation, the final human demonstration, or production deployment acceptance.
