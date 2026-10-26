# Suspension and membership access recovery

This October 25, 2026 correction is bounded Accounts/shared integration around
TJ's suspension and membership-review work. It preserves the existing Admin-only
suspension endpoint and officer review authority; it does not reassign ownership
of the membership module.

Four HTTP regressions confirmed the earlier gap: reinstatement stranded active
accounts after rejection records were purged or when they had no application;
an old completed review could instead activate a deliberately inactive account;
and a recorded unfinished review was not finalized. All four now pass.

## Saved intent and retry

`accounts.lifecycle.apply_suspension(user, suspend, expected_version=...)` is an
internal API whose caller authorizes the Admin action. The existing route still
protects self and superuser accounts. The service rechecks saved superuser state.
Forms include a suspension version, and an outdated opposite action is refused.

Profile stores four independent lifecycle fields:

| Field | Meaning |
|---|---|
| `suspension_was_active` | Saved activation before the first suspension in this cycle; nullable for unknown legacy history or a not-yet-captured reservation. |
| `suspension_restore_active` | Durable activation intent when reinstatement finishes. An explicitly recorded review can supersede the prior inactive state without falsifying the original snapshot. |
| `suspension_version` | Conditional-update token for the current lifecycle action. |
| `suspension_update_pending` | Access effects are unfinished; authentication and task eligibility must remain blocked. |

First suspension reserves its Profile intent before freshly reading User
activation, captures the snapshot, then deactivates User. A retry before capture
can safely capture it; deactivation never precedes capture. Repeated suspension
and partial User-write failures retain the saved snapshot. A new completed cycle
captures the activation that is actually current then. Repeating completed
reinstatement does not undo a later deliberate inactivation.

Reinstatement clears the suspension flag with unfinished lifecycle intent still
set. It completes recorded unfinished membership access with the original stored
decision/reviewer. The matching internal `suspension_version` contract permits
this completion while preventing a separate review from silently finishing in
the middle of lifecycle work. New membership reviews wait until that work ends.
The review's activation intent is persisted before its own flag clears, so a
later lifecycle retry does not undo a successful approval or rejection completion.

Without such a recorded unfinished review, reinstatement restores saved prior
activation. A previously active account works even if its application was purged
or never existed; a deliberately inactive account stays inactive. Pending
applications are not activated. Unknown legacy snapshots preserve the currently
saved activation rather than guessing from old reviews or missing records.

The final lifecycle flag clears only after all effects are confirmed. Failures
show uncertain/pending feedback rather than success. **Users and Roles** exposes
**Finish suspension** or **Finish reinstatement** for retry. Password/session
authentication, returning Google identity checks, task visibility, and task
assignee eligibility deny unfinished lifecycle access, even if User has already
become active. Migration `accounts.0007_suspension_activation_snapshot` preserves
existing role, suspension and User activation; it starts historical snapshots as
unknown rather than inventing their earlier state.

## Concurrency boundary

Lifecycle updates change only their Profile fields. The role/history producer
uses its separate role version and fields, so these conditional updates do not
overwrite each other. Membership decisions and User activation remain separate
MongoDB documents: this is a recoverable intent protocol, not a transaction or
a global lock against raw/operator writes. A detected late User write preserves
the winner's snapshot/state, marks access pending, and requires a fresh completion.
Conflicting duplicate membership states are not silently discarded. Legacy
unknown inactive accounts need an authorized data owner to establish intended
activation; they are not automatically enabled.

## Orphan signup recovery boundary

The safe operator interface is an explicit signup-attempt repair, not an
age-based inactive-user deletion job. See the separate
[signup recovery contract](accounts-signup-recovery.md). Ownership proof must be
an immutable attempt journal with the exact reserved User/application IDs and
expected identity, statement and signup channel, never a password or provider
token. Absence of an application or fifteen minutes of inactivity is not proof
that an account belongs to a failed attempt.

Inspection is dry run by default. Applying a repair requires the exact attempt,
explicit operator action, quiesced workers, revalidated inactive nonstaff,
nonsuperuser Applicant state, matching identity, and no unrelated domain data or
conflicting records. Repair may restore only that attempt's missing Profile,
Google identity and original pending application, using reserved IDs for retry
idempotency. It must not create/delete a User, activate an account, review an
application, change a role, or guess ownership. Missing journals and ambiguous
legacy data require manual data-owner investigation. No deletion heuristic is
implemented by this lifecycle correction.

## Verification

The four original HTTP cases failed against the old view (4 failures in 1.081s)
and passed after replacement. Final focused validation passed **105 tests in
33.062 seconds**, including all 26 new lifecycle cases, TJ's original suspension
tests, role audit, membership, and shared task integration. The test process used
an explicitly selected MD5 hasher for fixture speed; application settings were
not changed. This is functional regression evidence, not password-performance
or production-security benchmarking. The separate standalone MongoDB database
was `test_orgflow_suspension_lifecycle_review` on `127.0.0.1:27029`.

Cases include deliberate inactivity, no application, purged rejection,
unacknowledged reservation, User and final-stamp failures, matching review
completion token, original reviewer, competing first suspension, a review
completed before snapshot capture, new review during reinstatement, late User
writes, retry intent, stale forms, unknown legacy migration, and independent
role-history updates. A second agent reviewed the changed lifecycle and
membership source read-only; both reported race cases were corrected and tested.

System checks and diff whitespace checks passed. Global migration-drift and
full-suite/coverage results should be recorded after the separate signup-attempt
model/import and migration are integrated. Earlier 287-test functional validation
(89.754s) preceded the final review/lifecycle token coordination and is not a
final full-suite claim for this commit. Logs are retained outside the repository
in `../tmp/orgflow_claude_review_20261025/`, including
`suspension-before-tests.txt`, `suspension-final-tests.txt`, and
`suspension-integrated-tests.txt`.
