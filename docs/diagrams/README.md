# Current engineering diagrams

These diagrams describe the implemented Accounts, Tasks and shared integration
paths at preview commit `7eac4c6`. They are current handoff supplements; dated
proposal, analysis and design reports remain historical records.

| Diagram | Source | Image | Main evidence |
|---|---|---|---|
| Current architecture | [Mermaid](current-architecture.mmd) | [PNG](current-architecture.png) | `orgflow_project/urls.py`, `accounts/backends.py`, `accounts/google_auth.py`, `membership/models.py`, `tasks/models.py`, `tasks/services.py`, `core/views.py` |
| Task domain and storage | [Mermaid](task-domain.mmd) | [PNG](task-domain.png) | `tasks/models.py`, `tasks/migrations/0001_initial.py`, `committees/models.py`, `meetings/models.py`, `accounts/models.py` |
| Authorized task update and claim | [Mermaid](task-mutations.mmd) | [PNG](task-mutations.png) | `tasks/views.py`, `tasks/forms.py`, `tasks/models.py`, `tasks/services.py` |

The architecture distinguishes Chau's Accounts and Tasks work from shared team
integration and external provider boundaries. Membership recovery records its
decision and unfinished access intent before applying account effects. Password,
Google, existing-session and task eligibility checks block unfinished access
updates and administrative suspension. Google signup cleanup is best effort on
standalone MongoDB; it is not a multi-document rollback.

The domain diagram shows selected fields and logical Django references stored in MongoDB. FK deletion
rules are Django application behavior, not SQL foreign-key enforcement. The two
nullable User references on Task are `assignee` and `created_by`. Task history is
embedded JSON containing actor, timestamp and changed values. Overdue is computed
from due date, completion status and the configured local day; it is not a stored
Task status. Approved meeting conversion uses the unique `origin_key` for retry
safety; rejected actions are not imported.

The mutation sequence expands a successful change and stale-write conflicts.
Permission and validation failures stop before persistence; unchanged submissions
return without a version increment or duplicate audit entry. The version predicate
protects Task updates and claims in a single MongoDB document. Other workflows do
not gain transaction guarantees from this diagram.

Task-local audit history is implemented. Earlier Accounts planning also mentioned
role-change audit history; reconciling that commitment with ownership of the
organization-wide audit feature remains pending. These diagrams do not mark that
team feature, reports, announcements, or resources complete. Live Google, OpenAI
and Deepgram behavior is outside the offline test evidence. Current verification
is 254 primary tests passing in CI and 267 combined preview tests collected,
265 executed successfully and two live Deepgram tests skipped.

The PNG exports are generated from the adjacent Mermaid sources with Mermaid
11.12.1 and an installed headless Edge renderer. Rendering uses local files;
provider services are not contacted. Sources remain editable for future changes.
