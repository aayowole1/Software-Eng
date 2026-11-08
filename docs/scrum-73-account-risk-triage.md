# SCRUM-73: account risk R-03 triage — November 4, 2026

## Disposition

R-03 was the Google membership application-save failure that could return an
unhandled 500 after account provisioning. The existing merged mitigation is
present at application revision `4dcc933`. A new focused run passed all **82
tests in 12.980 seconds**, with no failures or skips. No new account-code change
was needed for this triage task.

The triage is complete: the known failure is handled, ownership and dates are
recorded below, and the operator-recovery limit is explicit. This does not certify
live Google OAuth configuration, complete database outage handling, or the entire
Accounts feature/release.

## Owner and date record

| Action | Owner / provenance | Date and disposition |
|---|---|---|
| Signup recovery implementation | Chau Nguyen, existing commits `638123e`, `ad03a87`, `812d9e6` on the merged main history | Implemented October 25, 2026; retained unchanged |
| R-03 triage and current validation | Tasin Nur Jawad, existing SCRUM-73 assignee, with Codex assistance | Completed November 4, 2026 |
| Required new fix assignment | None identified by this targeted regression | No new code defect or outstanding fix deadline found for the documented R-03 scope |
| Future interrupted signup | Deployment operator, coordinated by the account/integration owner | Follow the recorded-attempt procedure below if the recovery alert occurs; no blanket automatic cleanup |

This table records existing authorship and completed triage, not a new commitment
assigned to another teammate.

## Confirmed behavior and evidence

- `accounts/google_auth.py`: application provisioning database errors become
  `GoogleSignupRetryError`; `google_apply()` returns a controlled **503** with
  form feedback and the entered statement, retaining the verified signup session.
  Internal database details are not shown to the user.
- Account provisioning starts inactive. The recovery path does not sign the
  applicant in or grant Member/Officer authority.
- `accounts/signup_attempts.py` and `accounts/provisioning.py`: a durable signup
  attempt reserves the user/application identity before provisioning. Once an
  application insertion may have been visible, cleanup preserves it rather than
  deleting a potentially reviewed application on an uncertain acknowledgement.
- Recovery is restricted to the exact reserved, never-used inactive account.
  It refuses elevated, suspended, previously used or changed identities and
  preserves existing Google links, application decisions and unrelated accounts.
- The journal stores no password or provider token. Unconfirmed cleanup emits
  an opaque operator-recovery alert rather than claiming rollback.

Relevant executed cases include:

- `GoogleSignupRecoveryTests.test_application_database_failure_preserves_statement_and_exact_google_identity_for_repair`
- `GoogleSignupRecoveryTests.test_cleanup_failure_logs_safe_recovery_alert_and_does_not_sign_in`
- Identity/user/profile/precheck database failures and successful retry handling.
- `SignupAttemptRecoveryTests.test_google_orphan_restores_only_recorded_verified_subject_and_pending_application`
- Process-exit/lost-acknowledgement, identity-conflict, concurrent-repair and
  already-reviewed application preservation regressions.
- Google token audience/nonce/CSRF and account-state regressions.

## Validation execution

Executed labels:

```text
accounts.test_provisioning_recovery.GoogleSignupRecoveryTests
accounts.test_signup_attempt_recovery
accounts.test_google_auth
```

The run used Python 3.12.14, the declared dependencies, standalone MongoDB
8.0.16 on localhost:27029 and a disposable synthetic test database. System and
migration checks were clean. Private dotenv loading was disabled; live provider
keys were cleared. Google verification was mocked where needed; no live OAuth
requests or provider credentials were used. A fast password hasher was scoped
to the test process; application authentication settings were unchanged.

The 82-test scope includes related signup safety checks; it is not a new
whole-project test count or coverage claim. Source/application code was
unchanged during the run.

## Operator recovery and residual risk

1. Use the opaque `SignupAttempt` ID from the recovery alert, never an email or
   an arbitrary account selected by similarity.
2. Inspect using `python manage.py repair_signup <attempt-id>` (read-only).
3. Stop registration writers before an authorized repair, then use
   `python manage.py repair_signup <attempt-id> --apply --workers-stopped`.
4. Check the original pending application and inactive account state. If the
   command refuses, investigate rather than bypassing its identity/access checks.

Recovery spans multiple MongoDB documents without transaction-style rollback.
Simultaneous total database/session unavailability is outside this injected
application-save failure result. Real-origin Google OAuth and deployment checks
remain separate acceptance work.
