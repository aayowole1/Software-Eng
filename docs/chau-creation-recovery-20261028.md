# Committee creation recovery — October 28, 2026

This follow-up resolves the review finding in SCRUM-23: previously, a failed
creator-roster insertion returned 500 after the committee was already saved.
Submitting the original form again then produced a duplicate-name error.

## Resulting behavior

- A new browser form carries an actor-bound signed creation ticket with a
  reserved committee ID. A retry checks that exact record before name validation.
  It never adopts a committee merely because its name matches.
- A confirmed new committee insert attempts its creator's Chair membership.
  Lost database acknowledgements are reconciled through bounded reads of the
  exact committee and creator pair. An observed Chair confirms success.
- Unconfirmed outcomes return truthful 503 feedback with the entered values and
  ticket retained. Saved records are not deleted or silently rewritten.
- If the committee exists but its creator is absent, replay shows a recovery
  page instead of automatically restoring membership. The officer reviews the
  current roster and checks an initially unchecked confirmation box before
  adding themselves as Chair.
- Recovery uses fresh Officer/Admin access, CSRF and a signed current-value
  snapshot. It rejects stale metadata, foreign/invalid/expired tickets and
  ineligible actors. Existing Member roles are preserved, rather than promoted.
- Recovery never creates a missing committee. Normal role changes and roster
  management continue through their existing screens.
- Error/recovery templates do not run database-backed template context
  processors while reporting a database failure.

Older form clients that omit the creation ticket remain supported: the server
issues an identity for that request, and returned retry feedback includes it.
Clients must retain the returned ticket to continue the same attempt. An
explicitly supplied invalid ticket never falls back to a new identity.

This is bounded reconciliation and explicit recovery across two database
documents. It is not a transaction, a durable creation ledger, or an
exactly-once guarantee across deletion of an initial creation identity.
No models or migrations were changed. Existing case-insensitive form validation
still does not provide cross-record, case-insensitive database uniqueness.

## Verification

| Check | Source | Observed result |
|---|---|---|
| New focused recovery regressions | Source hashes in focused receipt | 21 passed; no skips, failures or errors |
| Primary full local regression | `00000da` | 682 collected: 682 passed, 0 skipped; 167.521 seconds; system/migration checks clean |
| Primary committees/tasks branch coverage | Same local run; implementation/admin included | 218/230 (94.78%); statements 835/871 (95.87%) |
| Combined preview full local regression | `de676e2` | 661 collected: 659 passed, 2 skipped; 166.932 seconds; system/migration checks clean |
| Combined preview committees/tasks branch coverage | Same local run; implementation/admin included | 218/230 (94.78%); statements 835/871 (95.87%) |

The two preview skips are the owner-run live Deepgram checks. Tests used separate
synthetic databases, blank provider credentials and no private environment file.
Local timing uses a process-only test password hasher; it is not a host benchmark.
Coverage excludes tests, migrations, initializers, app configuration and test helpers;
it is not whole-project coverage. Local/focused/CI executions overlap and must
not be added as unique or personally authored test counts.

[Focused receipt](evidence/chau-creation-recovery-20261028/focused-receipt.json),
[primary receipt](evidence/chau-creation-recovery-20261028/primary-receipt.json),
[preview receipt](evidence/chau-creation-recovery-20261028/preview-receipt.json),
[primary coverage](evidence/chau-creation-recovery-20261028/primary-coverage-summary.txt) and
[preview coverage](evidence/chau-creation-recovery-20261028/preview-coverage-summary.txt) retain the exact scope.
The [original failing diagnostic](evidence/chau-creation-recovery-20261028/pre-fix-diagnostic.json)
is a dated pre-fix observation, not a passing feature test.

Published full CI and production-container checks are available on the
[PR #12 checks](https://github.com/aayowole1/Software-Eng/pull/12/checks) and
[PR #13 checks](https://github.com/aayowole1/Software-Eng/pull/13/checks).
Earlier 661 / 638-plus-two-skips results and the 95.31% branch measurement in the
[earlier closeout](chau-closeout-20261028.md) belong to their recorded source
checkpoints; they are not a measurement of this later recovery change.

## Demo and acceptance

Use synthetic data. A prepared interrupted-setup fixture can show the saved
committee, current roster, unchecked confirmation and successful continuation.
Opening or machine-checking that fixture is preparation, not Chau's personal
rehearsal or a teammate's approval.

The related [contribution report](chau-contribution-report.md),
[demo script](chau-demo-script.md) and [completion checklist](chau-completion-checklist.md)
retain individual ownership and historical evidence. Officer/President/committee-
lead policy, personal rehearsal, affected-owner review, actual VM/public TLS,
host acceptance and live Google/OpenAI/Deepgram/SMTP checks remain separate
pending gates. No merge, real deployment, provider call or completed submission
is claimed by this fix.
