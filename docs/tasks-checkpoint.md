# Chau's Tasks 1.6 and shared integration checkpoint

Prepared October 25, 2026, with Codex assistance. Owner: Chau Minh Viet Nguyen.
This implements Chau's SCRUM-16 / WBS 1.6 task work and the shared connections
needed to use it with existing Accounts, Membership, Committees and Meetings.

This is the original implementation checkpoint, verified at `638123e` and
reviewed through PR #12. Later October 25 Claude-review fixes, final local
regression/coverage, named CI and static-review receipts, and remaining
human/team/provider gates are tracked in
[the current review resolution](chau-claude-review.md).
The branch/base and integration contract below describe this original snapshot.

The working branch is `chau/tasks-integration`, based on merged team main
`26b5177`. That base includes TJ's membership integration, roster/profile and
suspension changes (PRs #10 and #11). Those teammate features are inherited work,
not newly implemented by Chau here. Jack's meeting-provider/transcription branch
and Ayomide's events branch are not merged into this checkpoint. The integration
uses their existing model interfaces and keeps their feature ownership intact.

The latest reported team target is **November 1, 2026**; the reported submission
deadline is **November 10, 2026**. These are targets, not claims that all team
deliverables are complete. No actual working hours have been inferred or logged.

## Implemented behavior

Officers and admins create and delegate tasks with a title, description,
optional committee, optional assignee, optional due date, priority and progress
status. Priorities are Low, Medium and High. Statuses are To do, In progress and
Done. An authorized assignee can change progress, including reopening a completed
task. Only officers/admins edit task details or delegate to someone else.

For committee tasks, the assignee must be a current member of that committee.
For tasks without a committee, the assignee must be an organization roster member.
In both cases the account must be active and its profile unsuspended. Current
integration also withholds access during an unfinished suspension update; see
[lifecycle recovery](accounts-suspension-recovery.md). An
unfinished, unassigned committee task can be claimed by a current committee
member. Organization role determines management authority: a committee chair does
not gain officer rights merely by being a chair.

| Current user | Visibility | Allowed changes |
| --- | --- | --- |
| Signed out or Applicant | No task access | None |
| Inactive or suspended account | No task access | None |
| Active Member | Tasks in joined committees; their own assigned tasks without a committee | Progress on their own accessible assignments; claim an unfinished unassigned task in a joined committee |
| Active Officer or Admin | All tasks | Create, edit, delegate, change progress and import approved meeting actions |

Committee access is checked against current membership. Removing a member from a
committee removes access even when a committee task is still assigned to that
person. Account status and suspension are re-read by task services rather than
trusting a cached profile from an earlier session. Officers can reassign or clear
an assignment that has become ineligible.

Membership review also retains an `access_update_pending` marker while a saved
decision is being applied to account activation and role. Task access, claims,
updates and assignment eligibility remain blocked if any application for that
account has an unfinished marker, even if the account is already active and has
the Member role. Access becomes available after membership recovery finishes and
clears the marker; task code does not clear it or bypass the review decision.

The task list supports title/description search and filters for committee,
status, priority, own assignments and overdue work, with 25 records per page.
Counts show the user's complete visible task scope before optional list filters.
The personal dashboard shows counts and open work for the user's accessible
assignments. Committee pages show task totals and links only to committee
members and officers/admins. Public and applicant dashboards do not expose tasks.

A due date is a calendar date. A task is overdue when its due date is before
today and its status is not Done; a task due today is not yet overdue. The
project timezone defaults to `America/Chicago` and can be configured with
`TIME_ZONE`. A missing due date is allowed.

## Audit and conflicting edits

Each task retains a JSON history in the same MongoDB document as its current
state. Entries record action, timestamp, actor ID, actor username and changed
fields with previous/new values. Creation, edits, claims and meeting imports are
recorded. Member input and audit text are escaped when displayed.

Every task begins at version `0`. Changes use a conditional database update on
the task ID and expected version. State, next version and the appended audit
entry are written together in one document. A stale update or second stale claim
cannot overwrite the first change; the web page returns conflict feedback
(HTTP 409). Invalid/missing versions are rejected. A change that makes no actual
field difference adds no history entry and does not advance the version.

Task services reload stored state before applying changes. They do not trust a
`ModelForm` instance that form validation may already have modified. A task's
committee uses `PROTECT`; attempting to delete a committee that still has tasks
keeps both its roster and tasks intact and displays guidance to move the tasks.
Task deletion is not exposed as a workflow. Removing a user or source action
nulls its optional foreign key; existing history and copied task text remain.

## Contract for Jack's meeting integration

At this original checkpoint, the shared interface was `MeetingDraft`, `DraftStatus.APPROVED` and
`ActionItem(draft, description, accepted, position)`. The summarizer may change
provider or transcription implementation without changing task conversion.
This checkpoint does not invoke a live AI provider or claim provider evaluation.

An officer/admin explicitly opens the conversion link on an approved draft,
reviews the accepted actions and confirms assignment defaults. GET only previews;
the CSRF-protected POST performs conversion. Pending, rejected and
revision-requested drafts are rejected by both the page and the service.
Only `accepted=True` nonempty actions become tasks. Unaccepted items and raw
meeting notes are not copied into task pages.

Each new task keeps the full action description and a title limited to 200
characters, begins To do, and records its source action. The unique nonnullable
`origin_key` is `meeting:<action item ID>`. Manual tasks use independent
`manual:<UUID>` keys, avoiding MongoDB's nullable-unique-index behavior.
Retrying conversion returns existing tasks without changing their progress,
assignment or officer edits. If a batch stops after some tasks were created,
retrying imports only missing items. A deleted source action nulls the reference
but leaves its origin key and imported text intact.

Use the authorized service API rather than `Task.save()` or `TaskForm.save()`:

```python
from tasks.services import (
    create_task, update_task, claim_task, import_action_items, TaskConflict,
)

task = create_task(
    officer,
    title="Prepare the demonstration",
    description="Confirm the room and equipment.",
    committee=committee,       # Committee instance, or None
    assignee=member,           # User instance, or None
    due_date=due_date,         # datetime.date, or None
    priority="high",          # low / medium / high; default medium
)
task = update_task(member, task, {"status": "in_progress"}, expected_version=task.version)
task = claim_task(member, unassigned_task, expected_version=unassigned_task.version)
result = import_action_items(
    officer, approved_draft,
    committee=committee, assignee=member, due_date=due_date, priority="medium",
)
# result == {"created": [Task, ...], "existing": [Task, ...]}
```

`create_task()` accepts title, description, committee, assignee, due_date,
priority and status. `update_task()` accepts the same change fields; members can
change only status on their own accessible assignments. `import_action_items()`
accepts only committee, assignee, due_date and priority as batch defaults.
Use `PermissionDenied` for authorization failures, `ValidationError` for invalid
input and `TaskConflict` for stale writes. Helpers are `can_manage_tasks(user)`,
`can_update_task(user, task)`, `can_claim_task(user, task)` and
`Task.objects.visible_to(user)`; `task.is_overdue` exposes calendar-date overdue
behavior. Forms return model instances and date values in `cleaned_data`.

The original task app depended on existing committee/meeting models and the Accounts
suspension migration, without requiring meeting model changes. Subsequent review
added durable meeting approval/recovery safeguards; see the
[current resolution and source revisions](chau-claude-review.md). Future merges
should preserve the Tasks navigation link, app registration, URL include,
dashboard/committee links and approved-draft conversion link. Jack and Ayomide
also edit some of these shared files, so these integration points require review
when those branches merge.

## Verification and remaining review

The isolated testbench uses standalone MongoDB at `127.0.0.1:27029`, with
`MONGODB_NAME=orgflow_tasks_dev`; Django's test database is
`test_orgflow_tasks_dev`. This is separate from the earlier Accounts demo and
the team's deployment data. No replica set or multi-document transaction is
required by the task implementation.

Recorded execution results for this checkpoint:

- Merged-main baseline before Tasks registration: **170 tests passed**, 268.454 seconds.
- Tasks plus shared task integration: **54 tests passed**, 9.100 seconds
  (27 domain/form, 20 HTTP, 7 cross-app acceptance tests).
- Task-source syntax compilation passed.
- Migration drift check passed: no model changes detected beyond the checked-in migration.

The baseline/targeted raw logs are retained in the local review cache
`../tmp/orgflow_tasks_runtime/baseline-tests.txt` and
`../tmp/orgflow_tasks_runtime/task-acceptance-tests.txt` relative to the working
checkout. These are local paths, not promised files in a fresh clone. For original
implementation revision `638123e0fa60178e3d57c0f32f3d18bae92c5e50`, the full suite
passed **254 tests in 267.225 seconds** and targeted integration passed **84 tests
in 13.081 seconds**. The retained summary, tested revision and browser evidence
are in [tasks-verification.txt](tasks-verification.txt).

Account/membership safeguards added after the 54-test run were included in those
254/84 results at `638123e`: task access/assignment exclusion during incomplete
membership access updates and restored access after finalization were tested.
The 54-test result remains the earlier targeted checkpoint. Later Claude-review
fixes have separate revisions and evidence in [the current review](chau-claude-review.md);
neither the historical 254/84 nor combined 267 figures are reused as their final
validation.

The compare-and-set guarantee covers one task document. Account, committee and
meeting records are separate documents: their current eligibility is checked,
but this checkpoint does not claim a global transaction across those records.
Meeting conversion is a retryable batch, not an all-or-nothing batch. The
embedded audit is application history, not a tamper-proof external audit system.
Membership's unfinished-access marker bounds recovery by withholding access until
the recorded account update completes. It does not create a transaction across
membership, account and task documents, and task services do not repair those
documents themselves. A persistent interruption still requires the membership
recovery workflow before task access can resume.

Codex also verified officer delegation, committee assignee refresh, member
visibility, claiming and progress in a browser using synthetic data. The screenshot
and observed counts are in the verification summary. These observations do not
establish Chau's personal demonstration, accessibility-tool results, performance
targets, Docker startup, production deployment or live AI quality. Chau's code
explanation, team review and shared final deliverables remain separate.
Use [the acceptance guide](tasks-acceptance.md) to record those observations.
