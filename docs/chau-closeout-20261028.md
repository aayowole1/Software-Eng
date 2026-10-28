# Chau SCRUM-16 closeout addendum — October 28, 2026

Scope: Chau's Accounts/Tasks contribution and the shared committee/task connections.
Team target: November 1; reported course deadline: November 10. This is a dated
follow-up to the October 25 reports, not whole-project acceptance or a personal
demonstration record.

The Jira parent SCRUM-16 is due October 28. This implementation/preparation
closeout does not mark that parent or its subtasks human-approved Done; the
recorded team target and remaining owner gates are separate.

Current application checkpoints: primary `0641a63`, combined preview `b3c6dad`.
These include the missing normal committee-edit and existing-member role-update
flows. The new focused regression passed **23 tests in 11.881 seconds**, with a
clean Django system check. Current exact-head CI and primary local coverage are
recorded below. The final preview local regression and coverage also passed
after repairing its isolated test dependency. Older 419/432 and 404/417 runs remain evidence for their named earlier
revisions, not these new changes.

## Current verification receipts

| Execution | Observed result | Source/evidence |
|---|---|---|
| Primary exact-head CI | 661 of 661 tests passed in 219.247 seconds; deployment smoke passed | `0641a63`, [run 40713730179](https://github.com/aayowole1/Software-Eng/actions/runs/40713730179) |
| Combined exact-head CI | 640 collected: 638 passed, two live Deepgram skips, 166.342 seconds; deployment smoke passed | `b3c6dad`, [run 40713734468](https://github.com/aayowole1/Software-Eng/actions/runs/40713734468) |
| Primary local full regression | 661 passed in 199.165 seconds | Frozen source `0641a63`; isolated offline runner |
| Primary committee/task coverage | 718/744 statements (96.51%); 183/192 branches (95.31%). Committee package alone: 37/38 branches (97.37%) | Collected in that primary local full run; implementation/admin included; tests, migrations, initializers, app configuration and testing helpers excluded |
| Preview local regression/coverage | 640 collected: 638 passed, two live Deepgram skips, 195.960 seconds; 718/744 statements (96.51%); 183/192 branches (95.31%) | Frozen source `b3c6dad`; same committee/task measurement scope as primary; system/migration checks clean |

The measured primary committee/task core-logic branch result exceeds the 80%
target in this scope. It is not whole-project coverage, a new Accounts-package
measurement or proof of human acceptance. Local and CI cases overlap; do not add
their counts as unique tests or personally authored tests. Live skips and all
provider/VM/human limits below remain explicit.

Sanitized receipts: [CI](evidence/chau-closeout-20261028/ci-application-heads.json), [primary local](evidence/chau-closeout-20261028/primary-receipt.json), [preview local](evidence/chau-closeout-20261028/preview-receipt.json), [primary coverage](evidence/chau-closeout-20261028/primary-coverage-summary.txt) and [preview coverage](evidence/chau-closeout-20261028/preview-coverage-summary.txt).

The first local preview run could not import its declared OpenAI SDK and discovered only 630 tests with one import error. That [failed environment receipt](evidence/chau-closeout-20261028/preview-initial-environment-failure-receipt.json) is retained. Installing the declared `openai>=1.0,<2.0` dependency only in isolated test storage restored discovery: [11 mocked OpenAI tests](evidence/chau-closeout-20261028/preview-openai-focused-receipt.json) and then the full 640-test preview run passed. No provider key or live API call was used.

The October 25 Word report/script remain dated exports. Use this addendum and the updated repository demo script for the October 28 additions.

## Six-subtask evidence map

| SCRUM-16 subtask | Implemented evidence and current limit | Review disposition |
|---|---|---|
| SCRUM-23 — Committee data model/API; create, read, update and delete committees/members | Existing Committee/CommitteeMember models and C/R/D/roster flows are preserved. New committee name/description editing and existing member Chair/Member role updates close the identified application update gap. These are session/CSRF-protected Django form endpoints, not a JSON REST API. | Implementation and current CI available for review; affected-owner acceptance pending. |
| SCRUM-24 — Task create, assign and complete endpoints | Officers/Admins create and delegate to eligible members or committee scope; assignees update accessible task progress. POST endpoints, current-state authorization, version conflicts and state/history persistence have named regression coverage. | Ready to review the functional HTTP/form contract; peer approval remains pending. |
| SCRUM-25 — Committee/task frontend | Committee list/detail/create/delete and roster controls now include normal Edit committee and per-member Save role forms. Task create/edit, claiming, progress, filters/counts and history remain present. New forms have HTTP regressions; earlier axe/browser evidence is not a new rendered scan of these forms. | Update UI and current CI available for review; human walkthrough and approval pending. |
| SCRUM-26 — Role-based committee/task permissions | Current Officer-or-higher management and Admin-only deletion remain. A committee Chair never gains organization Officer/Admin rights. New mutations recheck effective account/access state and role-target eligibility. | Current rules tested; Officer/President/committee-lead interpretation still needs team policy acceptance. |
| SCRUM-27 — Unit/integration tests; 80% core-logic branch target | New `committees/test_updates.py` covers 23 permission, validation, stale/no-op, CSRF, conflict and uncertain-write cases. Existing committee/task/shared tests are preserved, including Ayo's generated tests. Current primary committee/task branch coverage is 95.31%; older Accounts/Tasks coverage is a separate scope. | Current CI passed and primary measured core-logic target met; matching preview local coverage recorded; peer acceptance remains pending. |
| SCRUM-28 — Documentation and demo preparation | Contribution report, source/evidence links, this addendum and the updated demo script are prepared. The committee edit/role/stale-form steps below are expected outcomes for rehearsal, not an assertion that Chau performed them. | Preparation available for review; personal rehearsal, explanation and team acceptance remain pending. |

Verified tracking status on October 28: SCRUM-16 and all six SCRUM-23–28 subtasks
are **In Review**. This is a review stage, not human-approved Done status. The
table preserves the separate verification, policy and owner gates; this document
does not itself change Jira.

## New committee update contract

- `GET/POST /committees/<id>/edit/`: Officer/Admin edits name/description.
  An unchanged name is permitted; case-insensitive duplicate-name validation
  excludes the edited record.
- `POST /committees/<id>/members/<user-id>/role/`: Officer/Admin changes an
  existing eligible member's committee role to Member or Chair. Organization
  Profile role, task authority and account activation are unchanged.
- Signed record/current-value fingerprints and conditional writes reject stale
  submissions with **409**. Invalid/tampered inputs return **400**; malformed route
  IDs or a user outside the selected committee return **404**. Valid no-ops write
  nothing. An uncertain database
  acknowledgement returns safe **503** reload-before-retry feedback without
  deleting data or blindly repeating a write.
- Current inactive/suspended/unfinished-access actors are withheld. Changing a
  committee label does not bypass the target member's current eligibility.

Source: [views](../committees/views.py), [routes](../committees/urls.py),
[edit form](../committees/templates/committees/committee_form.html),
[roster UI](../committees/templates/committees/committee_detail.html) and
[focused regressions](../committees/test_updates.py). No committee model or
migration change was made; the inherited foundations retain their authorship.

**Name-uniqueness limit:** case-insensitive form validation is not a
case-insensitive database uniqueness guarantee. The inherited name index is
case-sensitive: concurrent writes to different committees can still create
case-variant names. Same-record conditional updates do not close that
cross-record race. No canonical-name migration or automatic legacy cleanup is
claimed.

## Runtime follow-up and remaining checks

Both CI jobs are temporarily pinned to **Ubuntu 22.04** after the previous
`ubuntu-latest` runner moved to Ubuntu 26.04 and MongoDB 8.0 aborted at startup
with the recorded Linux-kernel compatibility error (SERVER-121912). This is an
environment compatibility change. The new exact-head CI runs above subsequently
passed; retain their actual runner/kernel receipts rather than generalizing this
result to every team VM kernel.

An intermediate Ubuntu 24.04 attempt had mixed results (one job passed and one
failed at MongoDB startup), so it was not retained as the compatibility fix. The
successful jobs report Ubuntu 22.04 runner image version `20261025.340.1` and
MongoDB `8.0.34`. The exact running kernel was **unobserved**; no specific uname
version is asserted. Re-evaluate this temporary runner pin before April 2027.

Main now includes Ayomide's Events app. The primary production Dockerfile therefore
copies `events/` too, matching app registration; the earlier omission was valid
only for the older Events-free primary snapshot. Jack's provider implementation
remains in the combined preview, while primary retains its rule-based summarizer.

Human rehearsal/explanation, affected-owner peer approval, unresolved role/email/
global-audit/retention policies, actual team VM/public TLS/backup operations,
the required host benchmark and team/course acceptance remain pending.
Google/OpenAI/Deepgram/real-SMTP checks remain with their owners at the user's
direction. No provider call, personal demo, actual effort hours, policy decision,
whole-project completion or completed submission is inferred from these edits.

Read with the [contribution report](chau-contribution-report.md),
[demo script](chau-demo-script.md), [completion checklist](chau-completion-checklist.md),
[deployment record](deployment-readiness.md) and [review ledger](chau-claude-review.md).
