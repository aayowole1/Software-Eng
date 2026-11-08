# Current engineering diagrams

These diagrams describe the implemented Accounts, Tasks and shared integration
paths at application commit `812d9e6`. They are current handoff supplements; dated
proposal, analysis and design reports remain historical records.

| Diagram | Source | Image | Main evidence |
|---|---|---|---|
| Current architecture | [Mermaid](current-architecture.mmd) | [PNG](current-architecture.png) | `orgflow_project/urls.py`, `accounts/backends.py`, `accounts/forms.py`, `accounts/google_auth.py`, `accounts/provisioning.py`, `accounts/signup_attempts.py`, `accounts/models.py`, `membership/models.py`, `tasks/models.py`, `tasks/services.py` |
| Task domain and storage | [Mermaid](task-domain.mmd) | [PNG](task-domain.png) | `tasks/models.py`, `tasks/migrations/0002_description_limit.py`, `committees/models.py`, `meetings/models.py`, `meetings/migrations/0003_generation_publication.py` |
| Authorized task update and claim | [Mermaid](task-mutations.mmd) | [PNG](task-mutations.png) | `tasks/views.py`, `tasks/forms.py`, `tasks/models.py`, `tasks/services.py` |

The architecture distinguishes Chau's Accounts and Tasks work from shared team
integration and external provider boundaries. Password, Google, existing-session
and task eligibility checks block suspension and unfinished membership or
suspension access updates. Account provisioning has durable attempt records and
bounded operator repair; it is not a multi-document rollback. Profiles have role
history and versioned suspension recovery state. Suspension recovery saves its
snapshot and restore intent; it does not append a suspension audit history.
These local Accounts paths do not establish an organization-wide audit service.

Meeting generation stages actions under a fresh token, then publishes the draft
or conditionally switches its current generation after staging completes.
Review and revision require the expected generation. Review records its decision,
original reviewer metadata and normalized action intent before changing separate
ActionItems. An unfinished marker blocks conversion until **Finish review**
completes the recorded intent. Unknown final-write outcomes retain data; old or
uncertain unpublished generations may remain stored but are not selected for
display or conversion. There is no automatic background cleanup. See
[`meetings/README.md`](../../meetings/README.md) for the publication contract.

The domain diagram shows selected fields and logical Django references stored in MongoDB. FK deletion
rules are Django application behavior, not SQL foreign-key enforcement. The two
nullable User references on Task are `assignee` and `created_by`. Task history is
embedded JSON containing actor, timestamp and changed values. Current descriptions
remain complete, up to 5,000 characters; long historical values use a preview,
character count and SHA-256 fingerprint. The service rejects actual changes whose
proposed history exceeds 8 MiB of BSON, preserving existing state and history.
This is bounded storage, not unlimited retention. Overdue is computed from due
date, completion status and the configured local day.

Approved meeting conversion requires a finished review and uses the recorded
accepted IDs/text from the current generation. The confirmation page and import
share that source. Unique task `origin_key` values make retries safe; rejected
actions and later unreviewed additions are excluded. Legacy approved drafts
without recorded intent retain accepted-item import behavior within their
published generation.

The mutation sequence expands a successful change and stale-write conflicts.
Authorization, data validation and history-capacity errors stop before persistence; unchanged submissions
return without a version increment or duplicate audit entry. The version predicate
protects Task updates and claims in a single MongoDB document. Other workflows do
not gain transaction guarantees from this diagram. An invalid assignee or missing
committee requires officer reassignment before further task changes; see
[`tasks/README.md`](../../tasks/README.md).

## Current validation

The final combined run at application `812d9e6` collected **417 tests: 415 passed
and two live Deepgram tests were skipped**, in **207.778 seconds**; see the
[complete combined transcript](../evidence/final-combined-tests.txt). The primary
contribution rerun at `bf6ad6d` passed **404 tests in 112.265 seconds**; see the
[complete primary transcript](../evidence/final-primary-tests.txt). That primary
revision corrects old meeting test fixtures without changing application behavior.

The combined run measured **95.35% statement coverage** and **90.82% branch
coverage** for the selected Accounts/Tasks Python scope: **1,377 statements and
414 branches**, including custom admin and management-command sources. This is
not whole-project coverage. The [coverage summary](../evidence/final-coverage-summary.txt)
and [totals](../evidence/final-coverage-totals.json) retain the measurement;
[source equivalence](../evidence/source-equivalence.txt) confirms all 19 measured
sources match between primary `8c58a07` and combined `812d9e6` after normalizing
checkout line endings. Current review disposition, CI receipts and remaining
human/provider limits are in the [review and resolution record](../chau-claude-review.md).

Intermediate history remains distinct: the combined run at `5dff37b` collected
340 tests, with 338 passed and two live Deepgram skips. The generation-publication
run at `0699419` passed all 105 scoped meeting, Tasks and shared integration tests;
that was not a full-suite run. Live Google, OpenAI and Deepgram behavior remains
outside the offline evidence. These diagrams do not mark the team's other
planned modules complete.

The PNG exports are generated from the adjacent Mermaid sources with Mermaid
11.12.1 and an installed headless Edge renderer. Rendering blocks network requests
and uses local files. Exports are approximately 2,864 pixels wide for clear
printing at 6.7 inches. Sources remain editable for future changes.
