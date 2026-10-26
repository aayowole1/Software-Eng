# Accounts role changes and membership access

This October 25, 2026 contribution implements the role-change audit producer
planned for Accounts WBS 1.3. It supplements the earlier Accounts checkpoint;
it does not replace that historical evidence or implement the team's broader
organization-wide audit/reporting module.

## Recorded changes

`accounts.models.set_role(user, role, actor=None, ...)` writes the role,
`Profile.role_version`, and an appended `Profile.role_history` entry in **one
conditional MongoDB document update**. Each entry stores `actor_id`, the actor's
username snapshot (`actor`), an aware ISO timestamp (`at`), `old_role`, `new_role`,
and `source`. Older internal calls without an actor explicitly record `System`;
they do not attribute an action to an invented person. Initial roles and existing
roles at migration time are not presented as historical changes.

Callers authorize their workflow before invoking this internal API. The Admin
**Users and Roles** route passes its authenticated actor and the form's hidden
version. A conflicting update raises `RoleChangeConflict` and preserves the
winning role/history. A repeated request for the already stored role makes no
new entry. A failed or unconfirmed database write is not announced as successful;
reload before retrying. A lost acknowledgement followed by the same requested
role does not duplicate the stored event. The service retains the compatible
optional `expected_version` argument for existing internal callers.

Only Admins can open **Users and Roles** and its expandable role history. Actor
names and source labels are escaped. Registered Django Profile admin pages are
read-only: they cannot add, change, or delete a Profile, bypass the role writer,
or edit history. Normal account code must also use the role writer for changes.
Saved superusers remain Admins; the service rechecks saved superuser authority.

Migration `accounts.0005_profile_role_audit` initializes existing documents with
version `0` and empty history while preserving their actual roles. Tests exercise
the real backend's migration defaults and conditional upgrade of a legacy
document without either new field.

## Membership policy and recovery

An ordinary role change is refused while **any** application for the target is
Pending or has `access_update_pending=True`. A source string cannot bypass this
rule. Approved review completion passes the internal `membership_review` object;
the service verifies its persisted Approved decision, unfinished access, target,
original reviewer, and lack of another conflicting application. It permits only
that workflow's conditional, unsuspended Applicant-to-Member promotion. The audit
source is `membership_review:<application id>`, attributed to its recorded
reviewer. A retry preserves the decision and the single role event. A newer
Officer/Admin assignment is preserved rather than demoted by approval.

A legacy elevated account that is rejected stays unfinished and cannot gain
working account access from that rejection. An officer cannot demote an
Officer/Admin through review. Recovery uses the existing Admin route:

1. An Admin selects **Applicant** for the affected nonself, nonsuperuser account
   in **Users and Roles** and saves the current form.
2. The service permits this exception only when every blocking record is already
   Rejected with unfinished access. It rechecks the acting Admin's saved, active,
   unsuspended state and records `rejected_membership_reconciliation` in history.
   Application status, reviewer, note, date, and unfinished flag are preserved.
3. An officer uses **Finish account access** for that reviewed application. Its
   original rejection completes with Applicant access; the flag is cleared last.

Other Pending or Approved unfinished applications cannot be bypassed by that
repair. Self-demotion, superuser demotion, and promotion through the repair are
refused. Conflicting duplicate application states require operator investigation;
the UI does not choose an application or decision to discard.

## Verification and limits

The standalone MongoDB test bench uses `127.0.0.1:27029` and the separate
`MONGODB_NAME=orgflow_role_audit_review` (`test_orgflow_role_audit_review` during
tests), with no transactions or production data. This command passed **43 tests
in 12.493 seconds** on the final role-audit implementation:

```text
python manage.py test accounts.test_role_audit membership.test_review_recovery --verbosity 2 --noinput
```

Named cases cover actor/time/from-to persistence, System attribution, no-op and
lost-acknowledgement retry, stale and interleaved writes, database failure,
admin-only audience, escaped history, superuser safety, actual legacy migration,
pending/unfinished HTTP promotion denial, approved-review contract, and audited
Admin repair of an elevated rejected account. An additional **37 tests passed in
133.869 seconds** after the policy correction:

```text
python manage.py test accounts.tests.AdminRoleManagementTests membership.tests core.test_tasks_integration --verbosity 1 --noinput
```

System checks and migration drift checks also passed. The compact record is
[accounts-role-audit-tests.txt](evidence/accounts-role-audit-tests.txt).
The broader Accounts, membership,
and shared-task set also passed 193 tests in 217.829 seconds **before** the added
membership-policy guard; that result is not a final full-suite claim for this
correction. Subsequent complete regression/CI evidence should retain its own
exact revision and measured result.

Role and history are atomic within their Profile document. Membership decisions,
User activation, suspension, and Profile state remain separate documents; these
checks do not create a cross-document transaction or eliminate every race with
operator writes. Durable unfinished-review flags keep partial review access
blocked and allow bounded retry. History is application evidence, not an external
tamper-proof or permanent compliance log: raw database writes can bypass it, and
account/collection removal is outside this history's retention contract. The
organization-wide audit browser, exports, and wider module audit producers remain
team scope. No effort hours or new live-provider verification are claimed here.
