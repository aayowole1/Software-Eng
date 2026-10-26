# Chau contribution: Claude review and resolution

Prepared October 25, 2026 (America/Chicago). **Frozen-source local regression and
Accounts/Tasks coverage passed; current CI, final Claude response and applicable
human/team acceptance remain separate.** Scope is Chau's
Accounts WBS 1.3, Tasks WBS 1.6, test/architecture foundation, and the shared
connections needed for those contributions. This is not whole-project acceptance,
a student demonstration, or human peer approval.

The independently reviewable contribution is [PR #12](https://github.com/aayowole1/Software-Eng/pull/12).
[PR #13](https://github.com/aayowole1/Software-Eng/pull/13) is the combined preview
with teammates' features. Work began from merged main `26b5177`; later shared
fixes retain TJ's membership/roster/suspension ownership, Jack's meeting/provider
ownership, and Ayomide's events/report responsibilities. The team target is
November 1, 2026; the reported course deadline is November 10. No actual hours,
contribution percentage, Jira mutation, or submission is inferred.

Application source under final validation is primary `8c58a07` and combined
preview `812d9e6`. Primary `bf6ad6d` updates only old meeting HTTP test fixtures
to send the required generation token and inspect the current generation; it
does not change application behavior. Earlier documentation heads (`069ee24`
primary, `8a7563e` preview) are evidence updates rather than new application
revisions. Current diagrams were refreshed at preview `0b83f74` from `812d9e6`,
with an architecture wording correction at documentation-only `4da4ada`.

## Actual review and source snapshots

An actual Claude desktop conversation received a scrubbed source packet for
combined revision `cbf67e5`. The observed model was **Claude Opus 5.5, Medium**.
Claude explicitly described its work as a static review and said it ran nothing.
The [actual conversation](https://claude.ai/chat/b5ed74cb-09ef-479c-a573-7346b4972227)
is linked for provenance; access depends on the account that owns it. Initial
findings were independently checked by Codex before implementing corrections.
Codex test results below are not tests executed by Claude.

The original local evidence is retained under the workspace review cache
`../tmp/orgflow_claude_review_20261025/` relative to the repository root:

- `claude-initial-review.txt`: captured initial Claude findings for `cbf67e5`.
- `claude-followup-review.txt`: captured second static response to the supplied
  context/fixes; it is not acknowledgement of the later final code.
- `OrgFlow_Chau_Review_Packet.txt`: initial supplied packet.
- `OrgFlow_Claude_Review_Context_and_Fixes.txt`: additional redacted settings,
  workflows and fix context prepared for follow-up.
- `requirements-audit.txt`: independent pre-fix requirement audit.
- `review-resolution-scaffold.md`: earlier working scaffold, preserved as dated input.

The [initial Claude capture](evidence/claude-initial-review.txt) and
[second response](evidence/claude-followup-review.txt) are also retained in this
repository for a fresh clone. Original source packets, scaffold and diagnostic
cache files remain local unless separately packaged. Their old GAP or pending
labels describe their snapshots; this record tracks subsequent
resolution. The original October 13 Accounts checkpoint and October 25
contribution DOCX/PDF remain historical supplements. A new current addendum must
identify its final revisions rather than rewrite those earlier reports.

In the second response, Claude closed its conditional backend finding, accepted
the competing-review intent design subject to executed tests, and recognized the
existing membership recovery workflow and exception-path signup compensation.
It corrected its overly broad age/no-application sweeper advice and preferred
the saved activation-snapshot approach to blanket reinstatement activation.
That response remained static and introduced further findings below; it was not
a final code approval.

## Initial findings and bounded disposition

“Fix committed” below means the stated source correction exists with relevant
targeted evidence. Frozen-source regression and current coverage are recorded
below; current CI and Claude's response to the final packet remain separate gates.

| Claude finding | Independently checked disposition | Source and named regression evidence |
|---|---|---|
| 1. Concurrent meeting reviews can change the approved accepted set used by Tasks | **Confirmed; shared fix committed.** Primary `f05c49b`, `c8b42b9`, `ff5a8a5` record one conditional review decision plus durable accepted-item intent. Conversion waits for review completion and uses that recorded source. Preview equivalents: `d5ae50f`, `395fb13`, `47d1eee`. | `meetings/models.py`, `meetings/views.py`, `tasks/services.py`; `MeetingReviewSafetyTests.test_actual_competing_reviews_record_exactly_one_decision`; `meetings/test_review_recovery.py`. Included in the final local regression below. |
| 2. Another authentication backend might bypass partial-suspension/session enforcement | **Conditional assumption absent; Claude explicitly closed it after seeing settings.** `AUTHENTICATION_BACKENDS` contains only `accounts.backends.EmailOrUsernameBackend`; Google explicitly logs in through it. Its inherited session lookup calls the overridden current-state check. | `orgflow_project/settings.py`, `accounts/backends.py`, `accounts/google_auth.py`; `test_existing_session_loses_access_when_only_suspension_flag_is_written`, `test_unfinished_membership_access_update_blocks_password_and_existing_session`. Recheck this boundary if another backend is added. |
| 3. Password/Google provisioning can strand an inactive reserved identity | **Confirmed; bounded correction committed.** Request-time recovery began with primary `c99ce06` (preview `83bc51b`). Primary `b0b4510` adds durable journal/operator repair; `8c58a07` corrects the independently reproduced compensation cases below. The suggested age-based inactive-user sweeper is not adopted. | `accounts/test_password_signup_recovery.py`, `accounts/test_provisioning_recovery.py`; [signup recovery contract](accounts-signup-recovery.md). Exact reserved IDs, dry run, explicit maintenance operation and refusal checks replace ownership guesses or automatic deletion. |
| 4. Reinstatement strands purged/no-application accounts and leaves recorded access work unfinished | **Confirmed with four failing HTTP reproductions; fixed in primary `f81dd3e`.** Snapshot/restore intent preserves genuine prior inactivity, completes recorded review access with its original reviewer, and keeps access blocked until confirmation. This deliberately avoids blanket activation of all accounts without applications. | [Lifecycle contract and results](accounts-suspension-recovery.md); `SuspensionLifecycleTests`, including `test_rejected_application_purge_does_not_erase_previous_activation`, `test_completed_review_activation_intent_survives_failed_lifecycle_final_stamp`, and review/lifecycle interleaving cases. |
| 5. Missing role audit, stale role writes, and pending applicant elevated before rejection | **Confirmed; fixed in primary `8cf8cd0` (preview `27bbc91`).** Role, version and embedded history update together; actor/time/from-to/source are recorded. Pending/unfinished review blocks ordinary promotion. A legacy elevated rejection stays unfinished until a bounded audited Admin correction restores Applicant. | [Role audit contract](accounts-role-audit.md); `RoleAuditTests.test_interleaving_role_writer_keeps_only_the_winning_history`, `test_pending_application_cannot_be_promoted_by_admin_http`, `test_rejected_elevated_account_stays_blocked_until_audited_admin_repair`. Global audit/reporting remains separate. |
| 6. Canonical username/nonblank-email uniqueness lacks a database guarantee | **Confirmed; primary `9c64657` adds MongoDB unique indexes with case-insensitive collation.** Legacy conflicts stop migration without revealing identifiers or deleting/deduplicating accounts automatically. | `accounts/migrations/0006_canonical_account_identifiers.py`, `accounts/test_identifier_uniqueness.py`. Index collation and nonblank-email scope are explicit; this is not a claim that historical conflicting data has been manually reconciled everywhere. |
| 7. Description history can grow to MongoDB's document limit | **Confirmed; bounded in primary `773e726` (preview `5dff37b`).** Description input is limited to 5,000 characters; long history values use preview/count/SHA-256; an 8 MiB history guard rejects before a state/version/history write. Capacity has safe form feedback rather than silent history loss. | [Task limits](../tasks/README.md); `TaskReviewBoundsTests.test_long_current_description_retained_but_audit_is_compact`, `test_history_capacity_rejects_before_state_version_or_history_write`, `test_capacity_error_uses_safe_http_feedback`. Abbreviated old text cannot be reconstructed from history. |
| 8. A committee deletion race can leave a dangling task reference | **Confirmed shared boundary; defensive recovery committed in `773e726`.** Normal PROTECT remains; if a race/operator change leaves a missing committee, pages show it safely and require an officer to select an existing committee or Organization before mutation. | `test_dangling_committee_displays_and_reassignment_recovers_without_500`, `test_dangling_committee_does_not_expose_task_to_unrelated_member`. This does not introduce a cross-document foreign-key lock or broaden member access. |
| 9. A task with an invalid current assignee cannot be edited until reassigned | **Intentional behavior retained and documented.** An officer must clear or reassign an inactive/suspended/departed/access-pending delegate before any update, including status. Allowing a priority/status change to retain invalid delegation is not the chosen mutation policy. | [Task assignment contract](../tasks/README.md); domain eligibility and task mutation tests. This is a recorded product tradeoff, not a claim that Claude endorsed it or that a team policy conflict was silently resolved. |
| 10. Task page wrapper does not use effective current access | **Confirmed; fixed in `773e726`.** The wrapper uses `active_role`, including fresh membership/lifecycle pending state; the service and assignee paths retain their own checks. | `TaskReviewBoundsTests.test_decorator_rechecks_pending_access_even_for_loaded_user`; lifecycle password/Google/task denial and restoration tests. |
| 11. Committee add-member choices offer unavailable accounts | **Confirmed shared integration; fixed in `773e726`.** Choices and POST validation use the current eligible-assignee rule. | `TaskReviewBoundsTests.test_committee_add_choices_and_posts_exclude_unavailable_members`; `committees/views.py`. This preserves committee ownership and does not change who may create a committee. |
| 12. Floating comment/dead docstring | **Cosmetic correction only.** The unreachable suspension docstring was removed when the lifecycle view was rewritten; the role-view comment is historical formatting, not an access or correctness gate. | `accounts/views.py`, primary `f81dd3e`. No test count or security claim is assigned to cosmetic cleanup. |

Jack's inherited meeting-create failures also affect the integration. Primary
`329bb9e` (preview `ea05fe3`) reserves a new draft ID, avoids assuming MongoDB
transaction rollback, compensates only that new attempt, retains safe failure
feedback, and redirects successful POST to GET. `MeetingCreationRecoveryTests`
covers provider failure, insert/partial-item failure, reserved-ID collision,
cleanup failure and retry. It does not repair every historical orphan or make
existing-draft regeneration transactional. Process-local recordings and live
provider/deployment behavior retain the limits below.

The second response identified these separate follow-ups. Confirmed corrections
and remaining owner dispositions are distinguished here:

| Follow-up | Current assignment and acceptance boundary |
|---|---|
| A. Create/revise can expose incomplete or mixed meeting generations | **Fixed in primary `ed1298b` / preview `0699419`.** Items stage under a fresh generation before publication; conditional revision/review selects one complete generation. Django admin is view-only for these mutations. 105 targeted meeting/Tasks/shared checks passed in 52.368s, including generation publication, concurrent revision, failure and current-generation tests. Jack retains provider/module ownership. |
| B. Import confirmation can show live items while conversion uses recorded accepted intent | **Fixed in the same generation/preview correction.** Preview and conversion share the approved source. `MeetingGenerationSafetyTests.test_import_preview_and_conversion_use_the_same_approved_snapshot` checks deliberate live-item divergence. Included in the 105-check result. |
| C. Failed compensation/process exit needs exact owned-attempt recovery | **Fixed within the bounded journal contract by `b0b4510` plus `8c58a07`.** The latter preserves User/relations once application insertion is attempted and validates untouched state before early compensation. 220 Accounts tests and eight independent cases passed. Never infer orphan ownership from age, inactivity, no application or matching email alone. |
| D. Username-race feedback loses its specific message | **Fixed with the signup corrections.** Real username/email unique-index race tests distinguish identity conflict from transient profile/application/database errors. Included in the 220 Accounts result at `8c58a07`. |
| E/F. Reapplication double submit, roster policy, missing-profile committee link, unused import | Additional low/shared observations require independent verification and owner disposition. They are not silently marked fixed or assigned to Chau's whole-project ownership by this document. |

The final follow-up packet was sent with the frozen primary/preview source,
Google sign-in script, membership recovery/CSRF context, meeting writers/admin
boundary, current diagrams and explicit final 404/417 test counts. The final
completed results supersede the partial primary log available during capture.
Claude's third response is still awaiting its external receipt; packet delivery
and the second response do not establish final acknowledgement or approval.

A further independent Codex probe of `b0b4510` confirmed this exact interruption:
the completion stamp is saved but its acknowledgement fails; compensation
deletes the application then fails before deleting User. The journal remains
Completed, so inspection/repair return a completed no-op for an inactive User
with no application. The narrow correction is committed as `8c58a07`, with
Accounts regression and exact independent rechecks below. Raw proof is
`independent-journal-lostack-reproducer.txt` in the local review cache. This was
not a new Claude claim, and the earlier passing signup tests do not close it.
The same independent review also reproduced valid officer approval between the
completion stamp and its lost-acknowledgement error: compensation then deleted
the now-active Member and recorded review. The narrow correction must preserve
an application/account that has progressed, not rely only on ownership of its
reserved ID. Its proof is `independent-journal-reviewed-compensation-reproducer.txt`
in the same cache. Both failures were reproduced before the correction below.
The phase-aware correction was subsequently rechecked independently in
eight isolated scenarios: password and Google each preserve completed relations
after lost acknowledgement, preserve a valid intervening approval, and recover
both absent and inserted-but-unacknowledged applications at the exact reserved
key. All eight passed; post-application deletion was never called, repaired
accounts stayed inactive, and reviewed accounts/decisions survived. Evidence is
[independent-journal-final-probes.txt](evidence/independent-journal-final-probes.txt).
The final scoped Accounts run passed 220
tests in 59.242s at `8c58a07`; contract/evidence update `069ee24` preserves that
result. These checks do not substitute for final shared regression or CI.

## Measured targeted evidence received

These are source-specific local results, not the final all-project verdict.
Unless a row says otherwise, they use standalone MongoDB on `127.0.0.1:27029`
with a separate disposable test database. Fast test hashers are fixture-only;
they do not change application password settings or benchmark password security.

| Source correction | Observed targeted result | Evidence boundary |
|---|---|---|
| `c99ce06` password recovery | Root-reported 10 checks passed in 2.195s; related registration/Google/recovery set 76 passed in 11.708s | Original request-time evidence predates the subsequently committed journal repair; final shared regression is separate. |
| `8cf8cd0` role audit/policy | 43 audit/review-recovery tests passed in 12.493s; 37 existing role/membership/task checks passed in 133.869s | [Retained record](evidence/accounts-role-audit-tests.txt). Older 193-test result predates the policy guard. |
| `9c64657` identity indexes | 167 Accounts tests passed in 38.746s, with process-only MD5 override | Predates lifecycle and durable signup changes; not current final Accounts coverage. |
| `f81dd3e` lifecycle/review handshake | 105 tests passed in 33.062s, including all 26 new lifecycle cases | [Retained contract/result](accounts-suspension-recovery.md); process-only MD5 override. Earlier 287-test run predates the final token coordination. |
| Meeting review/intent stage, preview `395fb13` | Root-reported 80 targeted checks passed in 27.936s, then full combined 298 collected / 296 passed / 2 live skips in 96.899s | `combined-review-recovery-tests.txt` in the local runtime cache. Predates later generation/journal fixes. |
| Truthful meeting recovery feedback, preview `47d1eee` | 11 recovery checks passed in 4.494s | Targeted result, not a new final combined run. |
| Task bounds/effective access, preview `5dff37b` / primary `773e726` | 63 targeted Task checks passed in 20.168s; combined 340 collected / 338 passed / 2 live skips in 122.604s | `combined-review-bounds-tests.txt` in `../tmp/orgflow_tasks_runtime/`. Predates lifecycle, generation and journal integration. |
| `ed1298b` / preview `0699419` generation and exact import preview | 105 targeted meeting/Tasks/shared checks passed in 52.368s | Generation/approval/preview acceptance; final complete regression is separate. |
| `8c58a07` final Accounts/signup correction | 220 Accounts tests passed in 59.242s, plus eight independent password/Google interruption and approval scenarios | [Retained record](evidence/accounts-signup-recovery-tests.txt). Earlier 45-check/212-check results predate the final compensation guards. |

The meeting/task intermediate combined runs used a process-only MD5 hasher,
explicitly empty OpenAI/Deepgram credentials, and separate local test databases.
The two skips are live-provider checks, not unexplained missing tests.

## Current owned requirement matrix

This matrix reconciles the earlier R01–R19 scaffold with implemented scope and
observed evidence. “Scoped checks” refers to the measured runs above; complete
freeze-wide results are recorded separately below. Policy, human and deployment
criteria are not converted into code passes by an automated result.

| Assigned requirement | Current implementation/evidence | Remaining acceptance boundary |
|---|---|---|
| Accounts 1.3: password/Google sign-in, role order and superuser safeguards (R01/R02) | Custom current-state backend; verified Google subject/nonce; role hierarchy and saved superuser guards. Accounts 220-check regression; original October 13 live Google evidence preserved. | No fresh live provider/deployment proof is inferred; strict local mailbox policy remains open. |
| Accounts: failure recovery and identity uniqueness (R03) | Durable exact-attempt journal, canonical database indexes, dry-run-first operator repair, safe conflict/outage messages, non-destructive application-stage failure handling. 220 checks plus eight independent scenarios. | Legacy unmarked/conflicting data and maintenance/retention policy require an authorized owner; no deletion heuristic. |
| Accounts: role-change audit (R04) | Actor/ID/time/from-to/source and role commit in one versioned Profile update; Admin-only history UI and read-only Profile admin. | Scoped role producer is complete within its contract; global audit/reporting scope remains team work. |
| Shared membership/suspension lifecycle (R05) | Recorded review decisions/reviewer survive retry; original activation snapshot and durable restore intent; access blocked during unfinished work; explicit Admin repair for legacy elevated rejection. | Single-document CAS does not imply a transaction across User/Profile/application; conflicting legacy state needs investigation. |
| Tasks 1.6: create, delegate, due date, priority, progress and claim (R06/R07) | Authorized services and HTTP workflows, current committee/assignee eligibility and revocation. Domain/view tests, targeted Tasks 63 and shared generation 105 checks; observed member claim. | Invalid delegation must be cleared/reassigned before any mutation; this intentional rule remains documented. |
| Tasks: search/filter/counts/local-calendar overdue (R08) | Scoped list/dashboard/committee counts, search and filters, Chicago default timezone and due-today boundary. Existing task/core regression. | Final freeze-wide result below; no measured response-time target is inferred. |
| Tasks: actor history and stale writes (R09) | Single-document state/version/history CAS, safe repeated claims/edits, bounded descriptions/history and safe capacity feedback. | Abbreviated old descriptions are not reconstructible; local activity is not a permanent external audit log. |
| Shared approved meeting conversion/review/generation (R10–R12) | One review intent, complete generation publication, exact preview/source agreement, unique task origin key and retryable batch. `ed1298b`/`0699419` 105 checks; observed create-once/repeat import. | Jack retains live AI/transcription quality and provider operations; batch is retryable, not all-or-nothing. |
| Architecture/test foundation and current supplement (R16) | Source contracts, independent review/fix traceability, test workflow, preserved historical report, current three Mermaid/PNG diagrams at preview `0b83f74` based on `812d9e6` (architecture wording corrected at `4da4ada`). | Current CI must use the frozen revisions below; the contribution supplement is not the completed course final report. |
| Assigned package branch criterion (R15 coverage gate) | Current Accounts 230/260 = 88.46% and Tasks 146/154 = 94.81% branches; each exceeds 80% in the measured implementation scope below. | Do not extend a two-package percentage to membership/RSVP/AI or the entire project. |
| Task UI accessibility/usability (R17) | Actual axe/keyboard/claim/import observations and incomplete checks recorded below. | Complete agreed human/pilot/screen-reader criteria and any unperformed form/error/loading flows remain separate. |
| Conflicting committee/email policy (R13/R14) | Current Officer-or-higher committee creation and local password-plus-officer-review behavior are explicit. | Team must accept/reconcile President mapping and strict verified-local-email wording. |
| Release/human completion (R18/R19) | PRs and local engineering evidence exist; actual Claude input is captured. | Deployment/performance/recovery, fresh CI/final Claude response, Chau demonstration, human peer/team acceptance, actual hours/board evidence and final submission remain their own gates. |

The diagrams include architecture, task domain/storage, and authorized mutation/
conflict sequence, with adjacent editable Mermaid and visually checked PNGs.
Their README identifies source files, publication/recovery contracts, and limits.
Versioned suspension recovery state is distinguished from the separate appended
role history; an audit history for every suspension change is not claimed.

## Observed task accessibility states

Root operated the rendered preview through the browser using the local audit
harness and **axe-core 4.14.0** at `127.0.0.1:8018`. At preview `b2551d`, desktop
officer list/new/edit and member list/detail each reported **0 violations and 0
incomplete checks**. Later lifecycle `bd9634d` did not change that task layout.
The primary `9a38735` adapts landmark semantics to its retained header navigation;
the preview page-state observations are not relabelled as a separately scanned
primary layout.

At mobile **390 × 844**, member list reported **0 violations and 2 incomplete
checks**, both on the hamburger glyph (contrast and label/name comparison).
Root visually observed a black glyph on white and verified its Open/Close
navigation accessible names. Enter opened the menu and focused Close; Escape
closed it and returned focus to Open, with `inert=true` and
`aria-expanded=false`. On desktop, the first Tab focused Skip to Content and
Enter focused `main#main`; Tab reached Save Status on the status flow.

Raw `officer-list-after.json`, `officer-new-after.json`, `officer-edit-after.json`,
`member-list-after.json`, `member-detail-after.json` and `member-mobile-after.json`
are retained in [the page-state evidence folder](evidence/axe-20261025/), with
the original local harness copies. Mobile proof is workspace
`output/OrgFlow_Claude_Review_Mobile_20261025.png`. These are bounded rendered
page/state checks, not WCAG certification, a screen-reader evaluation, complete
keyboard coverage of every form, or a five-user usability result. Human/course
acceptance criteria below remain separate.

After preview `0699419` plus `ad03a87`, root restarted the server and migrated the
synthetic demonstration database, then observed two additional flows:

- Member unassigned-task claim page: axe **0 violations / 0 incomplete**;
  Enter on Assign to Me saved the member assignee and a Claimed history entry.
- Officer import page: axe **0/0**; choosing Outreach refreshed the assignee
  choices to the expected member/officer, a November 1 due date was accepted,
  and Enter on Confirm created one task. Repeating Confirm created zero and
  reported one existing task.

Raw results are [member-claim-after.json](evidence/axe-20261025/member-claim-after.json)
and [officer-import-after.json](evidence/axe-20261025/officer-import-after.json),
also retained in the harness cache. Workspace proof images are
`output/OrgFlow_Claude_Review_Claim_20261025.png` and
`output/OrgFlow_Claude_Review_Import_20261025.png`. Subsequent Accounts-only work
does not change the rendered task markup; the broader human acceptance limits
still apply.

## Final local validation and external gates

| Gate | Required final evidence | Current status |
|---|---|---|
| Primary complete regression | Test revision `bf6ad6d`, application source `8c58a07`; 404 passed, no skips, 112.265s; system and migration checks clean | PASSED locally; [raw result](evidence/final-primary-tests.txt) |
| Combined complete regression | Application source `812d9e6`; 417 collected, 415 passed, 2 live Deepgram skips, 207.778s; system and migration checks clean | PASSED offline with explicit live skips; [raw result](evidence/final-combined-tests.txt) |
| Current Accounts/Tasks coverage | Coverage.py 7.17.0 at `812d9e6`; detailed scope/numerators below | Measured 90.82% combined branches; both assigned packages exceed 80% |
| Primary and combined GitHub CI | Final run URLs and results for final heads | PENDING external receipt; follow live PRs #12/#13; no current run result invented here |
| Browser/keyboard/axe observations | States and limits recorded above; repeat affected states if later markup changes | Observed preview evidence recorded; broader human/usability acceptance remains pending |
| Claude final follow-up | Actual final packet/revisions supplied and captured reviewer response | PENDING; two static responses are not final acknowledgement or approval |
| Human acceptance | Chau explanation/demo, affected owners' peer review and team submission agreement | PENDING; AI/tool results do not supply human signoff |

The first primary freeze-wide attempt found 404 tests and failed four old
meeting HTTP fixtures (154.187s): they omitted the now-required generation token
or asserted all historical action rows. `bf6ad6d` updates those fixtures to the
new contract without changing application code. The diagnostic is retained as
`primary-generation-fixture-diagnostic.txt`; the complete 404-test rerun passed
at `bf6ad6d` as recorded above. The generation guard was retained.

The local final runner executed system checks, migration drift checks and the
complete Django suite against separate disposable databases on standalone
MongoDB `127.0.0.1:27029`: `test_orgflow_final_claude_primary` and
`test_orgflow_final_claude_combined`. OpenAI/Deepgram keys and Google client ID
were explicitly empty. A process-only MD5 fixture hasher was used; application
settings and shared dependencies were not changed. The exact runner/commands are
retained in local `run_final_validation.py` beside the result files.

Current coverage instruments **Accounts and Tasks Python implementation**,
including custom admin and management commands. It excludes tests, migrations,
initializers, app configuration and testing helpers. It was collected during
the complete combined run, not only the new targeted cases. The
[source-equivalence record](evidence/source-equivalence.txt) confirms all 19
measured Python files match between primary `8c58a07` and combined `812d9e6`
after UTF-8/newline normalization. This is a combined measurement of those
shared sources, not a separately executed primary coverage run:

| Measured package | Statements covered/total | Statement percentage | Branches covered/total | Branch percentage |
|---|---:|---:|---:|---:|
| Accounts | 813/855 | 95.09% | 230/260 | 88.46% |
| Tasks | 500/522 | 95.79% | 146/154 | 94.81% |
| Accounts + Tasks | 1313/1377 | 95.35% | 376/414 | 90.82% |

The complete primary/combined results are linked above. The
[coverage summary](evidence/final-coverage-summary.txt) and
[exact coverage totals](evidence/final-coverage-totals.json) are retained in the
repository; detailed `final-coverage.json` remains in the local review cache.
These results satisfy the measured two-package branch
criterion; the broader historical whole-project coverage gate is not inferred.
Final CI and the third/final Claude response belong to a subsequent external
receipt and the live PRs, rather than being represented as completed here.

Historical primary implementation `638123e` passed **254 full / 84 targeted**
checks, including the safeguards added after the earlier 54-test run. See the
[original verification record](tasks-verification.txt). Historical combined
`8e2f734` collected 267 tests (265 passed, two live Deepgram skips) and measured
Accounts 109/124 = 87.90%, Tasks 117/136 = 86.03%, combined 226/260 = 86.92%
branch coverage and 910/962 = 94.59% statement coverage in its filtered package
scope. Historical `cbf67e5` CI run `40253804751` passed. These results remain
valid evidence for those earlier snapshots; they do not validate subsequent
fixes or the whole older NFR scope, which also names membership/RSVP/AI approval.

## Explicit policy, human and deployment gates

- **Committee creation authority:** the current role enum is Applicant, Member,
  Officer, Admin, and committee creation permits Officer-or-higher. Earlier
  planning text also says President-created committees. The team must record
  the accepted President/Admin/Officer mapping. Existing tests prove the current
  behavior, not acceptance of a changed policy; no unilateral restriction is
  introduced from one conflicting draft.
- **Verified local email:** Google requires a verified provider email/subject.
  Local registration supports password credentials plus officer membership
  review; it does not prove mailbox possession. The team must reconcile older
  strict verified-email wording and either accept the current local workflow or
  explicitly assign mailbox verification. Membership approval is not an email
  verification claim.
- **Audit scope/operations:** scoped Accounts role history and task-local activity
  do not complete the broader admin-only global audit/report/export requirement.
  Record its owner and the accepted local-activity visibility boundary. Signup
  journal retention and the authorized repair/maintenance owner also need policy.
- **Human/course acceptance:** Chau must explain and demonstrate his submitted
  work; affected owners must review shared integration. Preserve actual board
  exports and actual effort records before trial access ends. Complete the
  agreed rehearsal, pilot/screen-reader/usability criteria, course final report
  and team submission. No actual hours, messages, approvals or board edits are
  fabricated from automated work.
- **Live/provider/deployment limits:** October 13 Google proof is prior local
  evidence, not a new live test of these fixes or all deployments. Live AI and
  transcription quality, error/manual recovery and provider credentials remain
  with their owners. `_active_recordings` is process-local: multiworker routing,
  abandoned-session cleanup and restart durability remain deployment limitations.
  Intended hosting, Docker startup, restart/backup/restore, release security and
  performance targets require their own executed environment checks. An offline
  pass or a skipped live test does not complete those gates.

The [AI assistance record](tasks-ai-use.md), [historical checkpoint](tasks-checkpoint.md),
[acceptance guide](tasks-acceptance.md), and scoped Accounts recovery contracts
should be read with this current record. Local evidence is tied to the frozen
revisions above; later external receipts must identify their actual run and
reviewed revisions.
