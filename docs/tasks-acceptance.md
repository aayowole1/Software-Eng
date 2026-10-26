# Tasks 1.6 acceptance and local demo guide

Owner: Chau Minh Viet Nguyen. Prepared October 25, 2026.
Base: merged main `26b5177`; branch: `chau/tasks-integration`.
Team target: November 1, 2026. Reported submission deadline: November 10, 2026.
No actual-hours claim is made by this guide.

## Current evidence

The main baseline passed **170 tests in 268.454 seconds**. After adding Tasks,
the targeted command passed **54 tests in 9.100 seconds**: 27 service/form checks,
20 HTTP checks and seven shared integration checks. Syntax and migration-drift
checks also passed. These are automated observations, not a claim that Chau has
personally completed the browser walkthrough below.

The root execution retained baseline/targeted output outside the repository in
the local `../tmp/orgflow_tasks_runtime/` review cache. The final expanded suite,
current source revision and any additional evidence should be recorded in
`docs/tasks-verification.txt` after the remaining UI/integration changes finish.
Additional account/membership safeguards and a task recovery-state test were
added after the 54-test run; use the final verification summary for their results
rather than attributing them to that earlier run.

## Reproduce checks

Use an isolated development MongoDB instance. The verified task testbench is
**standalone MongoDB**, `127.0.0.1:27029`, database name `orgflow_tasks_dev`.
Django creates/removes `test_orgflow_tasks_dev` for database tests. Do not direct
these commands at an unrelated team or production database.

Run from the repository root in PowerShell, with the project's dependencies
installed in an available virtual environment:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27029'
$env:MONGODB_NAME = 'orgflow_tasks_dev'
$env:TIME_ZONE = 'America/Chicago'
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tasks core.test_tasks_integration --verbosity 2
python manage.py test --verbosity 2
git diff --check
```

In the verified local setup, `python` was the existing
`OrgFlow-Chau/.venv/Scripts/python.exe` interpreter. A fresh clone can use its own
environment installed from `requirements.txt`. Database tests for Tasks use a
fast test-only password hasher; application password settings remain unchanged.

For a local demo, use a separate development database, run `python manage.py
migrate`, and start `python manage.py runserver 127.0.0.1:8000`. Supply synthetic
accounts with the roles below through the existing registration/approval and
admin workflows. Avoid real private meeting notes or account details in saved
screenshots. Docker remains an alternative documented in README, but these task
results were obtained with the standalone local testbench.

## Automated acceptance coverage

| Area | Observed checks | Source |
| --- | --- | --- |
| Create/delegate | Officer creates task with member, committee, date, priority and audit; member/applicant cannot create; invalid roles, states and assignments rejected | `tasks/tests/test_services.py`, `tasks/tests/test_views.py` |
| Account integration | Current inactive/suspended state rejected even with previously loaded objects; membership approval then committee assignment enables task completion | `tasks/tests/test_services.py`, `tasks/tests/test_views.py`, `core/test_tasks_integration.py` |
| Visibility | Member sees only joined committee tasks and own general assignments; departure removes access; hidden IDs return 404 | `tasks/tests/test_services.py`, `tasks/tests/test_views.py` |
| Progress | Assignee updates status; cannot edit task details or another member's progress; audit records actor and before/after state | `tasks/tests/test_services.py`, `tasks/tests/test_views.py` |
| Claiming | Current committee member claims unfinished unassigned task; missing/stale version and outsider claims rejected; another claim does not overwrite assignment | `tasks/tests/test_services.py`, `tasks/tests/test_views.py` |
| Conflicting edits | Stale update preserves newer state/history; conditional-write failure reports conflict; no-op produces no duplicate audit | `tasks/tests/test_services.py`, `tasks/tests/test_views.py` |
| Dates/counts | Due-today, future, missing and Done tasks excluded from overdue; list/dashboard/committee counts retain user scope | `tasks/tests/test_services.py`, `tasks/tests/test_views.py`, `core/test_tasks_integration.py` |
| Meeting conversion | Approved/accepted only; GET preview does not mutate; POST is idempotent; full description preserved; interrupted batch retries safely; deleted source leaves task provenance | `tasks/tests/test_services.py`, `tasks/tests/test_views.py`, `core/test_tasks_integration.py` |
| Retention/security | Protected committee deletion retains roster/history; empty committees still delete; CSRF, POST-only claims, invalid IDs/filters and escaped task/audit text checked | `tasks/tests/test_services.py`, `tasks/tests/test_views.py`, `core/test_tasks_integration.py` |

The later recovery-state acceptance case constructs an active Member with a
reviewed application whose `access_update_pending` flag is still true. It checks
that task visibility, update/claim authority and new assignments are withheld,
then verifies that finalizing the recorded account update restores normal access,
claiming and assignment. Its execution result is pending the final integration run.

## Browser walkthrough to record

Use one officer, two active members of a test committee, one member outside that
committee and one applicant. The role model is Applicant < Member < Officer <
Admin. Committee chair is a separate role and does not imply officer authority.

1. Sign in as the officer. Open Tasks and create a committee task assigned to the
   first member, with priority High and a future date. Confirm the saved details
   and Created audit entry. Save an additional unfinished committee task with no
   assignee. Record the task IDs and expected counts.
2. Sign in as the first member. Confirm both committee tasks appear, the assigned
   task can move to In progress/Done, and task-detail editing is unavailable.
   Confirm the audit names the member and shows the status change.
3. Sign in as the second committee member and claim the unassigned task. Confirm
   assignment and Claimed history. A different member's status cannot be changed.
4. Open one task for editing in two officer tabs. Save a change in the first tab,
   then submit the older form in the second. Confirm conflict feedback and the
   first change/audit remain intact. Reload before editing again.
5. Try search and committee/status/priority/own/overdue filters. Confirm counts
   reflect the complete visible scope, while the table follows the filters. A
   task due today is not overdue; Done tasks never count as overdue. Confirm the
   configured timezone used for the date boundary.
6. Sign in as the outside member. Confirm another committee's task IDs and counts
   are unavailable. Remove a test member from the committee and confirm even
   their formerly assigned committee task becomes inaccessible.
7. Confirm an applicant has no Tasks navigation/access. Suspend a test account
   through the existing admin workflow and confirm task access/assignment is
   blocked. Do not treat pending membership approval as a suspension.
8. As an officer, create meeting notes with one accepted and one unaccepted action.
   Confirm a pending draft cannot create tasks. Approve the draft, open Create
   tasks, review its accepted actions and confirm assignment defaults. Verify only
   the accepted action appears as a task, then repeat conversion and verify no
   duplicate and no overwritten task progress. Members should see the resulting
   task without seeing the officer's raw meeting notes.
9. Verify the personal dashboard's task counts/open assignments and the committee
   task links. As admin, try deleting a committee with tasks and confirm a helpful
   message preserves the roster/history. Move or clear task committee assignments
   before deleting a committee that must be removed.
10. Use the keyboard to navigate/filter/create/update/claim tasks. Check labels,
    focus, feedback, readable tables and a narrow browser window. Record actual
    observations and any accessibility-tool result separately; automated HTTP
    tests alone do not establish accessibility compliance.

Record date, tested revision, expected/actual behavior and evidence filename for
each manual observation. Keep browser screenshots free of private account or
meeting data. Chau should be able to explain permission scope, version conflict
handling, embedded history and approved-action idempotency before marking his
demonstration complete.

## Integration review before team merge

Confirm Task app registration, `/tasks/` routes, navigation, personal dashboard,
committee links/deletion protection and the approved-draft conversion link remain
present when Jack's meeting work and Ayomide's event work merge. Preserve the
existing `MeetingDraft`/`ActionItem` interface; provider output must not bypass
officer approval. Re-run the full suite after resolving shared-file conflicts.

Same-task state/history changes are atomic on standalone MongoDB. A batch import
is intentionally retryable rather than globally atomic, and account/committee
eligibility checks span separate documents. No production, live-provider quality,
performance, complete accessibility or Docker claim should be added without its
own observed evidence. Team review, final submission packaging and individual
explanation are distinct from the automated checks recorded here.

During an interrupted membership access update, an active Member role alone is
insufficient: any `access_update_pending` marker blocks task access/assignment
until the membership recovery workflow finishes. This is a bounded recovery
safeguard, not a transaction across all application records. Tasks must not clear
the marker to work around an incomplete membership update.
