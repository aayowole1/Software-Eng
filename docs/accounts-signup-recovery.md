# Interrupted signup recovery

Password and Google signups first save a `SignupAttempt` with reserved User and
MembershipApplication keys, the original statement, signup channel and expected
identity. A Google attempt records the already verified subject, never its token.
No password, password hash, session cookie or provider credential is journaled.
The account is created inactive. A completed application still requires the
ordinary officer review before the person gains membership access.

The journal survives a process exit before the application is saved. Normal
database failures still attempt bounded cleanup of the exact reserved User; a
successful cleanup marks the attempt compensated. Failed cleanup leaves a pending
attempt and logs its opaque attempt ID for operator investigation. No identity
values or raw database exception details are included in that recovery alert.
Successful signup marks the attempt completed only after its application exists.

## Operator procedure

Use an authorized operator terminal with the intended environment explicitly
selected. This is a management command, with no public HTTP recovery endpoint.
Do not run a repair against a production or team database merely to demonstrate
the feature. Use the opaque attempt ID from the application log or an authorized
database inspection; an email address is not ownership evidence.

1. Inspect without changing data:

   ```text
   python manage.py repair_signup <attempt-id>
   ```

2. Investigate any refusal instead of deleting or relinking an account. For an
   eligible attempt, stop registration workers while leaving the database
   available. Prevent concurrent manual account/review changes during recovery.
   This maintenance boundary matters because the standalone MongoDB backend does
   not make signup compensation and reconstruction one transaction.

3. Apply only the reviewed plan while workers remain stopped:

   ```text
   python manage.py repair_signup <attempt-id> --apply --workers-stopped
   ```

4. Repeat the dry run and confirm it reports completed; restart the workers.
   The operator can inspect the restored pending application in Applications.
   The account remains inactive and the original password is unchanged. Complete
   any membership review through its normal officer workflow.

`--apply` without `--workers-stopped` is refused. The flag records an operator
assertion; the command cannot itself prove that every worker has stopped.

## Repair boundary

The command never creates or deletes a User, activates an account, changes its
role, changes a review decision, resets a password, or links an account by email.
It can restore a missing Applicant Profile, restore the original recorded Google
subject link, and create the original pending application at its reserved key.
Existing matching records are retained. Repeating an interrupted repair uses the
same reserved application primary key; it cannot create a second application.
The completion marker is written last.

Repair is refused for an unmarked account or missing reserved User; a compensated
attempt; changed username/email; active/staff/superuser access or any prior login;
elevated role, role history or present/past suspension; group/permission
assignments or other app activity;
an unrelated, conflicting or reviewed application; and a Google identity already
owned by another User. A completed attempt is a read-only no-op. Legacy accounts
without a journal require a separately authorized investigation; inactivity or
an email match alone never authorizes a repair or deletion.

If no User was inserted, normal signup can be submitted again. If a User remains
but its record fails these checks, preserve the records and investigate. Do not
remove a durable marker, review flag or suspension flag to bypass a refusal.
The journal contains personal application data; it is operator-only evidence,
not a new public account directory. Retention/export policy remains a team
decision; no automatic journal purge is introduced here.

## Verification

`accounts.test_signup_attempt_recovery` exercises abrupt exits in local signup
and the Google profile signal, missing relations, each repair failure stage,
lost completion stamping, repeated/parallel repair, dry-run immutability,
ineligible access states, application/identity conflicts, groups/domain data,
and secret-free output. Existing local/Google failure tests remain relevant to
normal compensation. Real MongoDB username and email races exercise conflict
feedback separately from transient database/profile/application retry failures.

The final targeted set passed **45 tests in 14.865 seconds** against standalone
MongoDB at localhost:27029, in the distinct disposable
`test_orgflow_signup_attempt_review` database. It included the 23 new journal/
repair tests, nine local password recovery tests, the existing registration
conflict view test, and 12 canonical identifier tests. System checks reported no
issues and the migration drift check found no changes. The test-process-only
MD5 override and empty provider keys did not change application settings or
contact a live provider. See [the compact record](evidence/accounts-signup-recovery-tests.txt).

An earlier broader Accounts run passed **212 tests in 53.235 seconds** before
the final lost-acknowledgement, conflict-feedback and past-use refusal additions.
It is intermediate regression evidence. A complete final shared suite/CI is
recorded separately by the integration owner; this targeted result does not
claim that wider acceptance.
