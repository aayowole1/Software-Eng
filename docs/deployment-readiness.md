# November 1 deployment check record

> **October 28 follow-up:** [SCRUM-16 closeout and new committee update flows](chau-closeout-20261028.md).
> Earlier dates, counts and receipts below retain their original checkpoints.
> The new 23 focused tests passed; current full/coverage/CI results and human or
> owner acceptance are not inferred from the older runs.

Checked October 25, 2026, America/Chicago. Scope: Chau's Accounts and Tasks,
approved meeting-to-task integration, and the deployment path supporting them.
The user confirmed the existing team Docker/VM as the target and explicitly left
live-provider checks pending for their owners. The intended team target remains
November 1; the reported course deadline is November 10.

**The production container checks passed for both branches. The actual team VM
has not been verified or deployed by this check.** The CI host is a disposable
Linux environment using synthetic accounts/data and a trusted private test
certificate. It does not establish public TLS, real SMTP delivery, live AI/STT
quality or whole-project acceptance.

## Executed checks

| Check | Chau branch | Combined preview |
|---|---|---|
| Full local regression, current deployment source | 419 passed, 61.299 s, at `4fe67d7` | 432 collected; 430 passed and 2 live Deepgram skips, 67.808 s, at `5e9ae5c` |
| Production configuration and readiness guards | 15 passed, included above | 15 passed, included above |
| Fresh Linux image build and declared dependencies | Passed | Passed |
| Explicit migrations and static collection; deployment security check | Passed, no warnings in disposable CI policy | Passed, no warnings in disposable CI policy |
| Non-root process, immutable source, image excludes private environment/key files | Passed | Passed |
| HTTPS using verified private test CA; secure session/CSRF cookies; static assets | Passed | Passed |
| Real HTTP member claim/status, CSRF rejection, officer-only create, committee isolation | Passed | Passed |
| Approved accepted-action import, repeat import creates no duplicate | Passed | Passed |
| Password reset over SMTP to internal capture, HTTPS token link, CSRF reset, new password accepted/old denied | Passed; no external delivery | Passed; no external delivery |
| Database stopped: liveness 200, readiness 503 | Passed | Passed |
| Fresh dump, disposable DB drop/restore, app restart, state/version/history/import/account checks | Passed; full recovery smoke 11 s | Passed; full recovery smoke 11 s |
| Bounded read smoke, 25 requests with 5 simultaneous readers | p95 0.1213 s before / 0.1233 s after restore | p95 0.1750 s before / 0.1840 s after restore |

Named source receipts: [Chau CI run 40267089001](https://github.com/aayowole1/Software-Eng/actions/runs/40267089001)
at `4fe67d71c1433a5ffd54acd90e655fc52ac3d44d` and
[combined CI run 40267025158](https://github.com/aayowole1/Software-Eng/actions/runs/40267025158)
at `5e9ae5c3485d7ccaac7ed413ef1704d6ad11560f`. Both complete workflows passed.
Their `deployment-smoke-evidence` artifacts retain the sanitized HTTPS, SMTP,
readiness, image-safety and recovery receipts. Full local logs and downloaded
artifacts are preserved in the deployment evidence packet. The later CI-harness
isolation hardening forces the internal DB, clears SMTP credentials, ignores
local environment files and uses a unique disposable project/image tag; final
published-head CI receipts are also retained with that packet.

This small synthetic recovery test used a backup made seconds earlier. It does
not prove backup scheduling, off-host retention, 24-hour freshness or restoration
of the team's real data. The read smoke is not the proposed 10-minute,
25-concurrent-user benchmark with 500 members, 100 events and 1,000 tasks.

## Changes made for deployment

The existing development startup remains available. A separate production path
uses explicit secret/host/database settings, DEBUG off, HTTPS redirects, secure
cookies, bounded readiness and manifest static serving. Production refuses
incomplete SMTP configuration unless delivery is explicitly disabled. It uses
one synchronous Gunicorn worker, an unprivileged user, read-only source and no
published MongoDB port. Migrations/static collection run as one explicit release
step with writers stopped. Real environment files and test keys are excluded
from Git and the image context.

Use the [deployment and recovery runbook](deployment-runbook.md). The security
settings follow the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
and [WhiteNoise's Django integration](https://whitenoise.readthedocs.io/en/stable/django.html).
The new configuration received independent Codex-agent review; the earlier
Claude static review covered its recorded source snapshot and is not described
as a review of these later deployment files.

## October 28 compatibility follow-up and current CI

The previous latest-head CI attempts failed before application tests because
MongoDB 8.0 aborted on the newer Ubuntu 26.04 runner with the recorded
Linux-kernel compatibility error (SERVER-121912). Both workflow jobs now use a
temporary **Ubuntu 22.04** pin. This avoids relying on a moving
`ubuntu-latest` environment; it is not a database downgrade, an application
test result, or a guarantee about every kernel on the team's VM. The successful
CI receipts below identify their runner image; the exact running kernel was not
recorded.

The Ubuntu 24.04 intermediate attempt was mixed (one job passed, one MongoDB
startup failure); the retained successful configuration is Ubuntu 22.04 image
`20261025.340.1` with MongoDB `8.0.34`. Its exact running kernel was unobserved,
so a particular uname version is not claimed. Re-evaluate the temporary pin
before April 2027; this tested CI compatibility is not a team VM certification.

Main now includes Ayomide's Events app. The primary production image therefore
copies `events/` as well, matching its installed-app registration. Earlier
Events-free primary packaging notes describe the older source only. The latest
committee update source is primary `0641a63` / preview `b3c6dad`; its 23
focused tests passed in 11.881 seconds. Current primary CI passed 661/661 tests in
219.247 seconds and deployment smoke ([run 40713730179](https://github.com/aayowole1/Software-Eng/actions/runs/40713730179));
preview CI passed 638 of 640 collected tests with two live Deepgram skips in
166.342 seconds and deployment smoke ([run 40713734468](https://github.com/aayowole1/Software-Eng/actions/runs/40713734468)).
Primary local regression/committee-task coverage is in the closeout; preview
local coverage remains pending its own receipt. These are separate from the
October 25 table above and do not establish actual team VM or live services.

See the [six-subtask closeout](chau-closeout-20261028.md). Public TLS, real
provider/SMTP delivery, actual VM release, host benchmarks, human rehearsal,
peer review and policy acceptance remain open.

## Remaining November 1 gates

| Owner/environment | Exact remaining check |
|---|---|
| Team VM operator | Confirm current VM address/access and Docker Compose >=2.24. The inherited `192.168.228.128` address timed out on app port 8000 and SSH 22 from this Windows machine. That is an access result, not proof that the intended VM is down. Docker CLI/Desktop is absent here and WSL is not installed. No VM/service/system changes were made. |
| Team VM operator | Run the tested release path with private real settings, an exact host and a valid HTTPS certificate/proxy; verify browser login/Tasks/import/static behavior at that origin. Keep an image digest and matching backup, rehearse restore on a separate database, and establish the actual backup schedule/retention. |
| Google configuration owner | The earlier October 13 genuine local login evidence is preserved. Google public endpoints/certificates are reachable now; this is connectivity only. Verify the current client ID and exact scheme/host/port in Google's private origin allowlist, then first/returning login and membership access at the intended origin. The public client ID in the original checkout is not copied to a new deployment automatically. |
| AI/STT owners | Add private provider settings and install declared requirements on the target, then run explicitly authorized synthetic checks and the agreed quality evaluation. No paid requests or audio uploads occurred here. The combined preview includes a bounded opt-in checker and [owner runbook in the combined preview](https://github.com/aayowole1/Software-Eng/blob/chau/integration-preview/docs/live-service-checks.md); the Chau branch retains its rule-based summarizer. |
| SMTP owner | Verify a secure real SMTP service, sender and delivered usable HTTPS reset link using an owned test mailbox. Internal capture proves application delivery mechanics only. The user chose to leave this check pending. |
| Meeting owner / combined preview | In the combined preview, recordings remain process-local and temporary. Do not add workers/threads/replicas; worker restart loses an active recording and abandoned-session cleanup is not durable. Its provider request/retry limits do not establish the proposed 30-second end-to-end AI failure requirement. |
| Team/course acceptance | Run the agreed performance and human usability/demonstration checks on the demo host; resolve recorded policy requirements, obtain owner acceptance, preserve actual Jira records before trial expiry, and complete the shared submission. No hours, reviews, demonstrations or approvals are invented by these checks. |

The prior [Claude review ledger](chau-claude-review.md) and [AI-use record](tasks-ai-use.md)
retain their historical results. This record supplements their previously open
container/security/recovery gates without replacing provider or human evidence.
