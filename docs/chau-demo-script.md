# OrgFlow Contribution Demo Script

> **October 28 follow-up:** [SCRUM-16 closeout and new committee update flows](chau-closeout-20261028.md).
> Earlier dates, counts and receipts below retain their original checkpoints.
> The new 23 focused tests passed; current full/coverage/CI results and human or
> owner acceptance are not inferred from the older runs.

A Guided Rehearsal for Chau Minh Viet Nguyen

Target length 8 to 10 minutes | Prepared October 25, 2026 | Local synthetic demonstration

## Before you begin

Use the running combined preview at http://127.0.0.1:8017. It contains your Accounts/Tasks work and the teammate integration. Keep one browser origin throughout the demonstration; switching between localhost and 127.0.0.1 changes cookies. Use one account at a time and sign out before changing roles. Tabs on this same origin share the current session.

| Practice role | Synthetic username | Purpose |
| --- | --- | --- |
| Officer | task_demo_officer | Create/delegate, inspect all tasks and review/import a fixture. |
| Outreach member | task_demo_member | Claim and update accessible tasks; prove restricted actions. |
| Finance member | task_demo_finance | Optional committee comparison. |

Shared local practice password: Task-Demo-2026! These are isolated synthetic accounts, not real team or service credentials. Do not change their organization roles/passwords or use this credential for a real deployment. The October 28 step changes only committee-role labels on a dedicated synthetic rehearsal committee.

[Start with the local sign-in page](http://127.0.0.1:8017/accounts/login/)

[Prepared unassigned task named Rehearsal claim task](http://127.0.0.1:8017/tasks/6aded76349a73f0c0c6701f8/)

[Prepared pending meeting named Offline rehearsal meeting fixture](http://127.0.0.1:8017/meetings/6aded76349a73f0c0c6701f9/)

The claim fixture starts unassigned at version 0. The meeting starts Pending review with two proposed actions. Preparation HTTP checks passed, but no personal rehearsal is marked complete. A consumed claim fixture needs a new unassigned task; a consumed meeting needs a newly prepared pending fixture or an honestly labeled approved/retry-only fallback. See If a prepared fixture was already used. Prepare replacements before starting the timer.

## Opening statement
Time 00:00 to 00:40

**Say** My contribution focuses on Accounts, task management and the safeguards connecting them to our team project. I extended the inherited account system and added task delegation, claiming, progress, permissions and history. I also worked on approved meeting-to-task conversion and the test, architecture and deployment evidence. Events, membership administration and meeting transcription retain my teammates' ownership.

**Say** This demonstration uses synthetic local data. Live Google, AI, transcription and outbound email checks remain with their owners. I will show the application behavior and explain how the important safeguards work.

## Accounts and role access
Time 00:40 to 01:30

**Do** Open Sign in and point out Email or username and Forgot your password. Show Create an account and apply to join in a separate tab if time permits, then sign in as task_demo_officer. Do not submit a new registration, reset a password, start a recording or submit new AI notes during this rehearsal.

**Expected** The officer dashboard shows the officer role, Tasks and Meeting drafts. The separate registration form explains the pending membership application. A password-reset entry point is visible; real email delivery is not demonstrated.

**Say** Access comes from the current account state and role. Google identity is verified on the server when configured, but local registration and membership approval are not proof of mailbox ownership. Role changes and recovery safeguards extend the original account system.

## Committee edit and member role — October 28 addition

Allow about 1 to 2 minutes. Trim the optional registration/filter discussion to
keep the original 8 to 10 minute target; the older timestamps below are an
outline, not a measured rehearsal with this addition.

**Prepare** Confirm that the local server serves the current application source
listed in the closeout. The [dedicated October 28 committee](http://127.0.0.1:8017/committees/6ae21491543cc770104b89e9/)
contains the practice officer and member. Six rendered HTTP prerequisites passed
([receipt](evidence/chau-closeout-20261028/demo-update-readiness.json)); this prepares
the scene without performing Chau's personal rehearsal. Use synthetic data and
recheck fixture state if it was already used. The server must be running before
opening the local links.

**Do** As the officer, open the committee and choose Edit committee. Open a second
edit tab before saving. Change the description in the first tab and save. Submit
a different description from the older second tab, without reloading it.

**Expected** The first edit saves. The older submission returns **409** with
reload/conflict feedback and does not replace the first description. An unchanged
name remains valid; another committee's case-insensitive duplicate name is
rejected. This is signed current-value conflict protection, not a new model
version or global case-folded uniqueness guarantee.

**Do** On the roster, change the synthetic member's committee role from Member to
Chair and choose Save role. Sign out, sign in as that member, and revisit the
committee and Tasks. Finish the stale-tab check before switching accounts,
because tabs on the same origin share the active session. Return to the officer
account before continuing the original create/delegate segment.

**Expected** The committee label changes to Chair, but the account remains an
organization Member. Committee management and New task remain unavailable; a
direct unauthorized edit/create request remains **403**. Existing task state,
version/history and roster membership are not recreated by the role change.

**Say** Committee Chair and organization Officer are different roles. The new
forms recheck current access and reject stale writes. Officer/President/lead
policy still needs team acceptance. These are rehearsal expectations supported
by automated HTTP tests; mark personal completion only after actually observing
and explaining this flow.

## Create and delegate
Time 01:30 to 02:40

**Do** Open Tasks > New task. Use a unique title such as Chau rehearsal task 01. Enter a short synthetic description, choose Outreach, assign task_demo_member@example.com, set November 1, 2026, choose High priority and keep To do. Save and note the resulting task URL.

**Expected** Task created appears with committee, member, date and priority. Task history records Created and the synthetic officer. Selecting Outreach removes Finance-only users from the assignment choices.

**Say** A committee limits who can see this work. The assignee must be active, unsuspended and eligible for that committee. Officers can create and delegate, while members can update only their own accessible assignments. The form and the service both enforce these rules.

## Member claim and progress
Time 02:40 to 04:00

**Do** Sign out and sign in as task_demo_member. Open Rehearsal claim task using the prepared link, then choose Assign to me. Change its status to In progress and Save status. Scroll to Task history. You can also open the task just created by the officer.

**Expected** The member becomes the assignee. History shows the claim and status update with actor and old/new values. Edit task/New task management controls are unavailable to this member.

**Say** Claiming turns an unassigned committee task into my assignment. Each change keeps state and history together. Task visibility, assignment and progress are checked against current membership; a role or committee change can remove access even when an older page is still open.

If Assign to me is absent, inspect the assignee/status. A previously consumed fixture is expected to be unclaimable. Ask the demo officer to create a new unfinished Outreach task with Assignee left unassigned; never reassign a completed fixture behind the scenes.

## Show the access boundary
Time 04:00 to 04:40

**Do** While signed in as the Outreach member, open /tasks/new/ directly, then the Finance task link below. Return to Tasks afterward.

[Prepared Finance task outside the Outreach member scope](http://127.0.0.1:8017/tasks/6adea2d3fae3ac638d68e595/)

**Expected** Task creation is denied with 403. The out-of-scope Finance task returns 404. These are expected permission outcomes, not application failures. The officer's raw meeting notes are also unavailable to the member.

**Say** Hiding a button is not sufficient security. The server checks direct requests too. A task outside the member's scope behaves as unavailable, so knowing its identifier does not grant access.

## Explain and show an older form
Time 04:40 to 05:50

**Do** Sign out, then sign back in as the officer. Open the newly created task's Edit task page in two tabs before saving either. In tab A change priority from High to Medium and save. In the still-old tab B change the description and submit. After the conflict, click Cancel to open the saved task detail with a GET; inspect Medium and its history, then reopen Edit task if needed. Do not refresh the stale POST.

**Expected** Tab A succeeds. Tab B receives conflict feedback (409), and the Medium priority and prior history remain intact. Both tabs must have loaded the old form before A saves; opening B afterward does not create a stale form.

**Say** Both forms carried the same task version. The first accepted change advances the version. The second form still expects the old version and cannot overwrite the first writer. The values and history update atomically in one task document; that does not make every project workflow a database transaction.

## Review the offline meeting
Time 05:50 to 06:50

**Do** As officer, open Offline rehearsal meeting fixture. Read its explicitly synthetic notes. Keep Prepare the rehearsal checklist, untick Order unrequested equipment, deliberately choose Approved in Decision, and Submit review. You may show that a pending draft lacks the task-conversion action before approval.

**Expected** The draft becomes Approved. The checklist remains accepted; the equipment proposal is rejected. Create tasks from accepted action items becomes available only after the review has finished.

**Say** This fixture demonstrates the approval boundary without calling an AI provider. Generated or proposed content can be wrong. An officer decides what is accepted, and the task importer uses that recorded accepted snapshot.

## Convert once and retry
Time 06:50 to 07:50

**Do** Choose Create tasks from accepted action items. Check that only Prepare the rehearsal checklist is listed. Choose Outreach and the demo member, a November 1 due date and Medium priority, then Confirm and create tasks. Return to the same meeting and repeat the conversion.

**Expected** First conversion: Created 1 task(s); 0 already existed. Retry: Created 0 task(s); 1 already existed. The rejected equipment suggestion creates no task, and retry does not reset existing task progress.

**Say** The import key identifies the source action. Repeating a request finds its existing task, so retries do not duplicate work. A batch can resume after interruption; it is not all-or-nothing across every task.

## Evidence and close
Time 07:50 to 09:10

**Do** Show the test/CI links and the architecture/domain/mutation diagrams from the contribution report. Keep the explanation short; allow about 30 additional seconds for sign-in and tab switching.

**Say** The verified Chau branch passed 419 tests. The combined preview collected 432, passed 430 and explicitly skipped two live Deepgram checks. The earlier measured Accounts/Tasks snapshot reached 90.82 percent branch coverage; that is not whole-project or later deployment-file coverage.

**Say** The container checks exercised HTTPS with a private test certificate, secure cookies, permissions, task import, internal email capture and backup/restore. The final small recovery tests took 11 seconds for my branch and 10 for the preview. They do not prove the actual VM, real email delivery or the full host benchmark.

**Say** The implementation and recorded checks are ready for team review. The VM release, owner-run live services, unresolved policy wording and required human acceptance remain pending. My next step is to rehearse this explanation and contribute the verified evidence to the team submission.

## If a prepared fixture was already used

For claiming, create another unassigned unfinished Outreach task through the officer UI. For import, an already approved fixture still demonstrates accepted-only conversion and retry protection, but do not promise a new task on every run. The older Welcome event planning fixture is an alternative; inspect its accepted actions and existing tasks before describing an expected create count.

If the local server is unavailable, use the saved task screenshots and CI receipts as a clearly labeled evidence walkthrough. Say that the live app is unavailable; do not present screenshots as a new live execution. If a provider is unavailable, stay on the prepared synthetic review fixture and record the provider check as pending. Do not expose private environment files.

For a shorter demo, skip the optional registration tab and live stale-edit example, but explain the version conflict rule and show its test evidence. Keep the member access and explicit approval/import retry segments.

## Questions you should be able to answer

**What is specifically your work?**
Accounts extensions, Tasks and their shared recovery/approval/import safeguards, with architecture/test/deployment evidence. Existing account/committee foundations and teammate Events, Membership and meeting-provider modules retain their ownership.

**Why check permissions again in the service?**
A page or cached object can be older than a suspension, role change or committee removal. The service reloads effective account and membership state before changing a task.

**Why use a version field?**
It prevents a stale edit or competing claim from overwriting a newer one. The conditional write accepts the expected version once, advances it and appends history in the same task document.

**What makes repeated imports safe?**
An imported task has a unique origin key tied to the approved source action. Preview and creation share the accepted review snapshot. An existing key returns the existing task rather than creating another.

**Are all database changes transactional?**
No. One task's state/version/history update is atomic. Signup, membership access and meeting/import workflows span records and use durable intent, blocked intermediate states and safe retries. Import batches can be partially completed.

**What happens after an interrupted signup?**
The durable signup-attempt journal identifies the exact owned pending operation. Operator repair is dry-run by default and requires writers stopped before applying. It does not automatically activate, promote, merge or delete a reviewed account.

**What does verified email mean here?**
Google requires its verified provider identity. Local password signup plus officer review does not prove possession of that mailbox. The team must reconcile the older strict local-verification requirement; do not claim it is implemented.

**What did the automated checks not prove?**
The actual team VM, real provider/SMTP operation, whole-project coverage, 25-user host benchmark, scheduled backup retention, five-person usability and human/course acceptance remain their own checks.

**How was AI used?**
Codex assisted analysis, implementation, tests, integration and documents. Claude performed actual static source review; Codex reproduced and checked findings. AI assistance is documented and does not replace my own explanation or human team signoff.

## Personal rehearsal record

After practicing, record the real date/revision, task/draft IDs, observed claim/status/403/404/conflict/import outcomes and any corrections. Confirm that you can explain each answer in your own words. Record only outcomes you actually observe during the rehearsal; no personal effort hours or approval is inferred from the prepared script.
