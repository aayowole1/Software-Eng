# Tasks quality and authorization evidence

Prepared October 25, 2026, with Codex assistance for Chau Minh Viet Nguyen.
Scope: Chau's Accounts/Tasks work and its shared integration. The team target is
November 1; the reported submission deadline is November 10. This record does
not establish Chau's personal demonstration, actual effort hours or team approval.

## Revisions and method

- Primary task source inspected: PR #12, head `3509516`; the tested implementation
  was `638123e`, followed by documentation updates.
- Combined preview inspected: `chau/integration-preview`, including the shared
  sidebar. The sidebar correction below changes the preview only; PR #12 is
  unchanged.
- Read-only Django form rendering used the existing Python environment and
  synthetic `orgflow_tasks_demo_v2` database on localhost:27029. No application
  records were created or modified by that inspection.
- Creating an independent in-app browser tab returned **"Browser is not
  available: iab"** in this agent's tool session. This audit therefore makes no
  independent live keyboard, screen-reader, viewport or computed-style claim.
  It did not use the root agent's signed-in tab.

Existing regression evidence is in [tasks-verification.txt](tasks-verification.txt):
254 tests passed in 267.225 seconds; the focused task/account/membership run passed
84 tests in 13.081 seconds. These are retained earlier runs, not additional runs
performed during this audit. The [integration handoff](integration-handoff.md)
records the combined preview's earlier 267 collected tests: 265 passed and two
live Deepgram checks skipped. Those Django results precede this sidebar change.

## Task form and keyboard structure

The following checks were actually performed by rendering the forms and parsing
their HTML, together with inspection of their templates, styles and scripts:

| Check | Observed evidence |
| --- | --- |
| Visible field names | All 18 controls had associated `<label for>`/`id` pairs: TaskForm 7, TaskImportForm 4, TaskStatusForm 1 and TaskFilterForm 6. No duplicate IDs occurred within a form. |
| Help and errors | Committee/assignee guidance is connected by `aria-describedby`. An invalid status selection rendered `aria-invalid="true"` and a reference to its error text. |
| Native controls | Task inputs, selects, buttons and links use native elements. Hidden version fields are not presented as visible controls. This supports keyboard operation but does not prove a live keyboard walkthrough. |
| Focus and bypass | The shared stylesheet defines a three-pixel `:focus-visible` outline for links, buttons and form controls. The base template includes a Skip to content link targeting the main landmark. |
| Task table | The list has a table caption, column headers with `scope="col"`, and a horizontal overflow container. Live zoom/reflow and keyboard scrolling remain to be checked. |
| Assignment changes | `assignment.js` announces loading, completion and failure through a polite live region; it blocks save while loading or failed, offers a native retry button and cancels stale requests. Server-side eligibility validation remains authoritative. |
| Status and history | Details use headings and a definition list; claim errors use `role="alert"`. Audit actor, field and value text remains escaped. |

Source-derived contrast calculations for the primary palette were 15.74:1 for
body text on the page background, 6.42:1 for muted text on white and 6.46:1 for
accent text on white. These are calculations from CSS literals, not a rendered
contrast scan or certification of all states and backgrounds.

## Consequential preview finding and correction

The inherited combined-preview mobile sidebar was only moved offscreen by a CSS
transform. Its links remained eligible for focus, its controls lacked expanded
state/control relationships, and it provided no Escape/focus-return behavior.
Its transparent toggle also inherited white button text: source-derived contrast
was approximately 1.07:1 on the page and 1.05:1 on the sidebar.

The preview correction is limited to navigation:

- The sidebar is a named navigation landmark; both native toggle buttons identify
  the controlled sidebar and expose its expanded state.
- Closed mobile navigation is both `hidden` and `inert`. Desktop navigation is
  restored on breakpoint changes, including removal of the closed state.
- Opening moves focus to Close navigation. Closing or Escape returns focus to
  Open navigation. Resizing avoids leaving focus in a hidden drawer or control.
- Toggle text uses the ordinary dark text color on the surface background, and
  the close button stays inside the drawer rather than outside its clipped edge.
- The drawer is nonmodal navigation; no modal or focus-trap behavior is claimed.

Actual checks run after this correction:

```text
node --check core/static/core/sidebar.js
node --test core/tests_sidebar_navigation.cjs
7 tests passed; 0 failed; 0 skipped
git diff --check
```

The seven tests execute the real sidebar script with a small dependency-free DOM
fixture. They verify closed hidden/inert state, open/focus behavior, Escape,
close-button focus return, desktop availability and both responsive focus
transitions. They test state transitions, not browser rendering or assistive
technology behavior. The root agent subsequently performed the separate live
browser checks recorded below.

## Root-performed live navigation checks

The root agent reported these observations on October 25 against the combined
preview at `http://127.0.0.1:8017`, using synthetic database
`orgflow_combined_demo_20261025`. The preview server was restarted so the updated
template was served. These are the root agent's browser observations, not this
audit agent's independent browser run or Chau's personal demonstration.

- At a 390 × 844 viewport, the closed drawer's navigation links were absent from
  the accessibility-tree observation.
- Enter on Open navigation opened the drawer, moved focus to Close navigation
  and exposed `aria-expanded="true"`.
- Escape closed the drawer and returned focus to Open navigation.
- Tab from the closed Open navigation control reached Skip to content, skipping
  the hidden navigation links.
- Returning to the normal 1265-pixel viewport restored desktop navigation after
  the responsive change settled.
- In an additional mobile check, Space opened and closed navigation with the
  expected focus. With the drawer open, Tab reached the brand link; resizing to
  1024 pixels retained focus on that link. Resizing back to 390 pixels closed the
  drawer and returned focus to Open navigation.
- On an existing assigned task, ArrowDown changed the Status selection from
  To do to In progress. Tab reached Save status; Shift+Tab returned to Status.
  Enter on Save status produced success feedback and a persisted Updated history
  entry attributed to synthetic member `task_demo_member`.

Screenshots retained by the root agent:
[mobile tasks](evidence/integration-tasks-mobile.jpg) and
[desktop tasks](evidence/integration-tasks-desktop.jpg), plus
[updated task history](evidence/integration-task-history.jpg). These observations verify
the stated navigation and status behavior only; they are not an axe scan, screen-reader
session or a complete task-form keyboard audit.

A later preview-only navigation check found that Start a meeting was displayed
to members even though its endpoint already requires an officer. The link is now
restricted to officers/admins. The seven existing cross-app integration tests
passed in 2.107 seconds after adding member/applicant absence and officer presence
assertions. A refreshed synthetic member browser view confirms the link is absent.
This follow-up changes the shared template and test assertions; the measured
Accounts/Tasks Python sources below are unchanged.

## Authorization and integration traceability

The test names below exist in the inspected source and were included in the
retained regression runs. They exercise behavior against the database and HTTP
endpoints; this table is scenario traceability, not a numeric coverage report.

| Requirement or risk | Concrete existing test evidence |
| --- | --- |
| Anonymous/applicant access denied; officer delegation allowed | `tasks.tests.test_views.TaskViewTests.test_anonymous_redirect_and_applicant_denied`; `test_officer_creates_delegated_task_and_member_cannot` |
| Fresh account state overrides stale caller objects | `tasks.tests.test_services.TaskServiceTests.test_only_current_active_officers_manage_tasks`; `test_deactivated_stale_officer_instance_cannot_create` |
| Incomplete membership access withholds task visibility, assignment, claims and updates | `tasks.tests.test_services.TaskServiceTests.test_incomplete_membership_access_update_blocks_tasks_until_finalized` |
| Committee scope and removal revoke access, even to an assigned task | `tasks.tests.test_services.TaskServiceTests.test_visibility_hides_other_general_and_other_committee_tasks`; `test_departed_committee_member_loses_even_assigned_task_access`; `tasks.tests.test_views.TaskViewTests.test_removed_committee_member_loses_assigned_task_access` |
| Assignee updates progress; other members cannot change it or task metadata | `tasks.tests.test_services.TaskServiceTests.test_assignee_updates_only_progress_and_audit_is_persisted`; `test_unassigned_and_other_assigned_tasks_cannot_be_updated_by_member`; `tasks.tests.test_views.TaskViewTests.test_assignee_updates_status_but_cannot_edit_metadata` |
| Invalid and inappropriate assignees are rejected | `tasks.tests.test_services.TaskServiceTests.test_assignment_rejects_applicants_and_noncommittee_members`; `test_assignment_rejects_inactive_and_suspended_members` |
| Stale edits/claims do not overwrite newer data or append misleading audit | `tasks.tests.test_services.TaskServiceTests.test_stale_update_cannot_overwrite_new_state_or_append_audit`; `test_conditional_write_failure_does_not_report_success`; `tasks.tests.test_views.TaskViewTests.test_claim_without_version_and_stale_second_claim_cannot_overwrite` |
| Mutations require POST and CSRF protection | `tasks.tests.test_views.TaskViewTests.test_claim_is_post_only_and_records_member_assignment`; `test_csrf_protects_create_status_and_claim`; `test_import_requires_csrf` |
| Hidden task IDs and invalid filter input cannot bypass scope | `tasks.tests.test_views.TaskViewTests.test_unknown_malformed_and_cross_committee_task_are_404`; `test_invalid_filters_show_feedback`; `test_member_counts_and_filters_never_include_other_committee` |
| Only officers convert approved, accepted meeting actions; retries preserve tasks | `tasks.tests.test_services.TaskServiceTests.test_import_requires_approval_and_officer_and_only_accepted_items`; `test_import_retries_do_not_duplicate_or_overwrite_tasks`; `test_import_resumes_after_partial_batch_and_source_deletion_preserves_task`; `tasks.tests.test_views.TaskViewTests.test_import_get_is_read_only_and_post_is_accepted_only_idempotent` |
| Task text and audit content remain escaped | `tasks.tests.test_views.TaskViewTests.test_task_title_description_and_audit_are_escaped` |
| Dashboard and committee integration preserve role scope | `core.test_tasks_integration.TaskIntegrationTests.test_dashboard_counts_only_my_accessible_assignments`; `test_public_and_applicant_dashboards_hide_tasks`; `test_committee_task_summary_requires_membership_or_officer_role` |
| Password/session/Google access fails closed during suspension or unfinished review | `accounts.test_provisioning_recovery.AccountAccessRecoveryTests.test_password_and_backend_session_lookup_deny_suspension_until_reinstated`; `test_existing_session_loses_access_when_only_suspension_flag_is_written`; `test_unfinished_membership_access_update_blocks_password_and_existing_session`; `test_unfinished_membership_access_update_blocks_google_until_completion` |
| Review recovery preserves decisions and does not reactivate suspended accounts | `membership.test_review_recovery.ReviewRecoveryTests.test_activation_failure_keeps_review_intent_and_officer_retry_preserves_decision`; `test_final_stamp_failure_retains_flag_and_retry_does_not_repeat_activation`; `test_suspended_account_is_not_reactivated_and_intent_remains`; `test_interleaving_review_uses_pending_compare_and_set` |
| Superuser authority cannot be demoted by ordinary role management | `accounts.test_account_safety.SuperuserRoleSafetyTests.test_superuser_demotion_rejected_by_service`; `test_admin_post_cannot_demote_another_superuser`; `test_role_change_requires_csrf_even_for_admin` |

The table demonstrates positive officer/member workflows and meaningful forbidden
paths. It does not establish every possible role × endpoint × object-state
combination or a complete authorization proof.

## Measured statement and branch coverage

Coverage.py **7.17.0** was installed into the separate workspace tool directory
`tmp/orgflow_tasks_runtime/coverage-deps`. The shared virtual environment,
repository dependency files and application settings were unchanged. Measurement
started before Django setup and covered the application Python modules in
`accounts` and `tasks`. Tests, migrations, package initializers, app/admin
registration and the test helper were excluded. HTML, CSS and JavaScript are not
included in these Python percentages.

The initial focused run passed all **84 tests in 22.161 seconds**. Its combined
Accounts/Tasks branch result was 169/260, or 65.00%. That run intentionally omitted
the ordinary Accounts/Google test modules, so it was not used as a full-suite
coverage gate. The existing full combined suite was then measured once, without
adding tests to pursue a percentage.

The full measurement at revision **`8e2f7348bf4cfb4665b77093d70f5be3da371dcc`**
collected **267 tests: 265 passed and two live Deepgram checks were skipped**,
in **59.940 seconds**. It used standalone MongoDB at localhost:27029 and distinct
disposable database `test_orgflow_chau_full_branch_coverage`. Provider keys were
explicitly empty; the fast MD5 password hasher was overridden only in the test
process. This run also covered the preview's updated template through HTTP tests.

| Instrumented scope | Executed statements / total | Statement coverage | Executed branch destinations / total | Branch coverage |
| --- | ---: | ---: | ---: | ---: |
| Accounts | 457 / 478 | 95.61% | 109 / 124 | 87.90% |
| Tasks | 453 / 484 | 93.60% | 117 / 136 | 86.03% |
| Combined Accounts and Tasks | 910 / 962 | 94.59% | 226 / 260 | 86.92% |

Coverage.py's combined statement-plus-branch percentage was **92.96%**; its
default rounded `Cover` column shows 93%. That is distinct from the explicitly
calculated **86.92% branch coverage** above. Thirty-four branch destinations and
52 statements in this scope remained unexecuted.

Remaining paths include certain account input/administrative fallbacks,
post-validation task error feedback, unsupported service-field rejection and the
concurrent import uniqueness-collision handler. The JSON retains exact missing
line and branch pairs. The successful sequential import retry tests do not prove
that every concurrent collision path was exercised.

Both measured packages exceed 80% branch coverage in this run. This substantiates
that threshold for the stated Accounts/Tasks scope, **not** the earlier proposal's
whole-system criterion spanning membership, RSVP and AI-approval logic. Those
other packages were exercised by tests but were not instrumented for this report.
Passing tests and coverage percentages do not prove absence of defects.

Local raw artifacts, outside the repository and therefore absent from a fresh
clone, are retained under `tmp/orgflow_tasks_runtime/`:

- `coverage-full267-raw.txt`: raw full-suite result and aggregate totals.
- `coverage-full267-summary.txt`: per-module summary and missing line ranges.
- `coverage-full267.json`: detailed statement and branch data.
- `coverage-full267-totals.json` and `.coverage-full267`: aggregate/data files.
- Corresponding `coverage-focused84*` files preserve the intermediate run.
- `run_focused_branch_coverage.py --full` reproduces the full measurement using
  the isolated coverage and existing preview dependency targets.

The full-run [transcript](evidence/coverage-full267-raw.txt),
[module summary](evidence/coverage-full267-summary.txt) and
[aggregate totals](evidence/coverage-full267-totals.json) are also retained in this
repository for a fresh clone. The detailed JSON and coverage database remain local.

## Limits and remaining acceptance evidence

- Python coverage is now measured as above. Browser-side coverage and the
  whole-system branch-coverage criterion remain outside this source scope.
- No axe or other accessibility scanner was run. Zero serious/critical findings,
  WCAG conformance, screen-reader behavior and the five-user usability target are
  unverified by this audit.
- The root's navigation and status checks above do not complete all keyboard
  acceptance. Remaining checks include full creation/edit/import form order and
  operation, date input, field errors, assignment loading/retry and keyboard
  claim submission. Use synthetic records.
- The separate meeting-provider evaluation, deployment, Docker, performance,
  backup/restore and Chau's personal explanation remain outside these results.

No new authorization defect was established by this audit. The consequential
shared-navigation issue was corrected in the preview and received the limited
root-performed live confirmation above. No claim of complete project acceptance
is made.
