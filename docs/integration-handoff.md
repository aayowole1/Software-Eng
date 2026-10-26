# OrgFlow integration handoff

Prepared October 25, 2026, with Codex assistance for Chau Minh Viet Nguyen.
The team target is **November 1, 2026**, ahead of the reported **November 10**
submission deadline and the end of Ayomide's Jira trial. This document records
completed implementation and verification; the remaining dates below are proposed
team checkpoints.

## Included work and ownership

| Component | Source | Status in this preview |
| --- | --- | --- |
| Membership, profiles, committee rosters, suspension | Team main `26b5177`, including TJ's PRs #10 and #11 | Inherited and preserved |
| Accounts | Chau's merged PR #7 and recovery safeguards in PR #12 | Included |
| Tasks and committees, SCRUM-16 / WBS 1.6 | Chau's PR #12, tested code `638123e`; documentation `3509516` | Included |
| Events and attendance | Ayomide's `ayomide/events-attendance`, `88b3116`, PR #9 | Included through merge `cbaf251` |
| Meeting recording, transcription and draft processing | Jack's `jack/meeting-notes`, `06fc88d` | Included through merge `99ef86c` |

The shared integration preserves Tasks, Events and Meetings navigation,
dashboards, membership recovery, account access guards, and the Chicago timezone.
Conflicts were resolved in README, base template, dashboard, settings, root URLs
and sidebar. The only additional test adjustment narrows the task escaping
assertion to unsafe task content, allowing the legitimate shared sidebar script.
Jack's provider, transcription and meeting view code remains as authored.

This branch is `chau/integration-preview`. Chau's independently reviewable work
remains in [PR #12](https://github.com/aayowole1/Software-Eng/pull/12).
Teammates retain ownership of their features and their final reviews.

## Verification completed

- Chau's checkpoint: **254 tests passed** in 267.225 seconds; a focused integration
  run of **84 tests passed** in 13.081 seconds.
- GitHub Actions passed for PR #12 at `3509516`:
  [run 40252003702](https://github.com/aayowole1/Software-Eng/actions/runs/40252003702).
- Combined code revision `9d5cf4365642c745adf64b8453667a74fd5b59db`:
  **267 tests collected, 265 executed successfully and 2 live Deepgram tests
  skipped**, in 34.484 seconds.
- Combined system check: no issues. Migration drift check: no changes detected.
- GitHub Actions also passed on the combined checkpoint `7eac4c6` with the normal
  application password settings:
  [run 40252569595](https://github.com/aayowole1/Software-Eng/actions/runs/40252569595).
- Combined tests used standalone MongoDB 8.0.32 at localhost:27029 and a separate
  disposable test database. A fast password hasher was set only in the test
  process; application password settings were unchanged. Provider keys were
  explicitly empty. No live OpenAI or Deepgram request was made.
- The subsequent merge of `3509516` brought documentation only. This handoff and
  its README link also change documentation only. A subsequent preview-only
  navigation fix makes the closed mobile menu hidden and inert, exposes expanded
  state, and handles Escape and focus return. Seven dependency-free interaction
  tests and actual browser keyboard checks passed; see
  [the quality evidence](tasks-quality-evidence.md). The workflow now runs those
  navigation checks and JavaScript syntax checks alongside the Django suite.
- A full coverage run at `8e2f734` also completed all 267 collected tests
  (265 passed, two live-provider skips) in 59.940 seconds. The measured
  Accounts/Tasks Python scope achieved **94.59% statement coverage** and
  **86.92% branch coverage**. This is not a whole-project coverage claim; the
  quality record lists exclusions and retained summaries.
- The Start a meeting link now follows the endpoint's existing officer/admin
  restriction. Seven cross-app integration tests passed in 2.107 seconds after
  adding navigation assertions, and a synthetic member browser check confirmed
  the link is absent.

The combined run is retained in
[the test transcript](evidence/integration-preview-tests.txt).
Chau's [verification record](tasks-verification.txt) and
[acceptance guide](tasks-acceptance.md) include the task browser observations.
The combined [desktop](evidence/integration-tasks-desktop.jpg) and
[mobile](evidence/integration-tasks-mobile.jpg) images use synthetic local data.

## Remaining team checks for the November 1 target

| Suggested date | Check | Responsibility / evidence needed |
| --- | --- | --- |
| October 26 | Review Tasks and recovery behavior, then review the combined navigation and workflows | Chau and affected feature owners; comments or approval on the draft changes |
| October 27-29 | Run live transcription and AI draft processing with approved project credentials; check useful output and failure handling | Jack with the team; record actual outcomes without publishing credentials |
| October 27-29 | Walk through membership approval/recovery, committee roster, task delegation/claim/progress, events/attendance and meeting-to-task conversion together | Relevant feature owners; use synthetic data and record results |
| October 30 | Verify the agreed merged version in the team's intended startup/deployment environment and resolve remaining failures | Team integration review; record the exact revision and environment |
| By November 1 | Agree on a demonstration version, finish the shared report/evidence, and preserve Jira ticket/status and actual-hours records while the trial is accessible | Team; save an export or agreed snapshot before trial access ends |
| November 2-10 | Retain submission buffer for corrections and the reported November 10 deadline | Team |

Live provider quality, Docker startup, production deployment, performance targets,
and accessibility-tool results have not been established by the offline tests.
The MongoDB backend's lack of multi-document transaction rollback remains relevant
to meeting code using `atomic()` and requires the meeting owner's review.
Chau's personal explanation and demonstration still need to be performed by Chau.
No actual hours, live Jira status changes, team approvals, or completed submission
are asserted here.

The older Accounts plan also mentions role-change audit history. Current task
history covers task mutations; it does not fulfill organization-wide role audit.
The team should reconcile that older Accounts commitment with the current audit
feature owner and backlog before marking the wider audit requirement complete.
