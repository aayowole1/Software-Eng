# Proposed Chair task permissions and task choices

This change implements Ayo's November 3 Teams proposal for review. Team agreement,
the SRS update and acceptance remain pending. It does not mark Jira work Done.

## Behavior

| Actor | Task authority |
|---|---|
| Officer / Admin | Existing organization-wide task management |
| Current committee Chair | Create, edit and assign tasks in committees where they are a Chair |
| Ordinary committee member | Existing claim and own-progress actions |
| President | Existing Admin account role; no new role is introduced |

A Chair's committee choices and assignee endpoint are scoped to committees they
manage. Moving a task requires authority over both its source and destination;
Chairs cannot create or move Organization tasks. Current account state,
suspension, membership and Chair status are checked again after validation.
Version checks still reject stale task updates. Task changes retain their actor
and field history. These checks do not claim an atomic transaction across account,
committee membership and task documents.

Chair task authority does not allow committee editing, roster management or
meeting generation/review/approved-action import. Existing Officer/Admin guards
remain on those operations.

Urgent is an additional priority. Under Review is an additional progress status,
with existing status permissions. An authorized assignee can move directly from
Under Review to Done; no new approval rule or approver role is introduced. The
model choices feed create/edit/progress/filter forms and history labels.

Migration `tasks.0003_task_priority_and_status_options` changes field choices;
existing task values remain valid. Chair authority uses existing committee roles.

## Validation

- Seven option regressions passed on the option commit, including saved values,
  labels/history, filters, invalid/stale updates and no additional approval gate.
- Eighteen Chair permission regressions passed on the Chair commit, including
  source/destination boundaries, forged assignments, removal/demotion/suspension,
  validation-time revocation, CSRF, stale edits and Officer-only meeting import.
- All 27 combined regressions passed, including two additional tests for the
  combined Chair/Urgent/Under Review behavior. System and migration checks passed;
  the choices migration was applied to the isolated test database.
- The separate Chair checkpoint passed 111 tests: 18 new permission tests plus
  existing Tasks, committee-update and task-integration tests. This predates the
  combined option commit and is not a full-project count.
- Existing negative validation tests now use an actually invalid priority value
  rather than Urgent, which is an accepted choice. Positive coverage verifies
  that Urgent is accepted and persisted.
- Full-workflow results are shown on the PR's Checks tab. They do not establish
  live-provider or actual target-VM acceptance.

Receipts: [combined checks and source hashes](evidence/chau-task-chair-options-20261103/combined-checks.json)
and [earlier Chair checkpoint](evidence/chau-task-chair-options-20261103/chair-checkpoint.json).

The 27 combined functional checks use an isolated MongoDB test database and a fast
test-only password hasher. Production password settings are unchanged. Provider
credentials are blank and no live provider call is made. CI uses the repository's
normal test configuration.

## Tracking and review

Keep SCRUM-23 through SCRUM-28 In Review. Proposed new tracking items are:

1. Chair task permissions, blocking SCRUM-26 until accepted.
2. Urgent task priority.
3. Under Review progress status.
4. SRS role/choice update, offered by Ayo (FR4.2 and the status wording in FR4.3).

No Jira ticket IDs, dates, hours, dependency links or teammate approvals are
inferred. The four items remain drafts until created in Jira and agreed by the
team. The separate SRS file shared in Teams is owned by Ayo and is not rewritten
by this code change.

Real Google/OpenAI/Deepgram/SMTP checks and actual team VM/public TLS validation
remain with their owners. This proposal is not a live deployment or completed
course submission.
