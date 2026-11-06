# Task mutation limits and recovery

Officers and Admins manage tasks across the organization. A current committee
Chair can create, edit and assign tasks in that committee, using its current
eligible roster. A Chair must manage both the source and destination committee
to move a task, and cannot create or move a task to Organization. Chair access
does not grant committee roster/edit, meeting review/import, Officer or Admin
authority. Members retain task claiming and their own progress updates. Account
and Chair membership are rechecked after validation before writing a task.

Tasks support Low, Medium, High and Urgent priorities, and To do, In progress,
Under Review and Done statuses. Under Review is a progress label, with the same
task permissions and stale-form checks as other statuses. It
does not require a separate approval before an authorized assignee marks work
Done. The create/edit, progress, import-priority and filter forms use the model
choices, and task history displays their labels.

Task descriptions accept at most 5,000 characters. The current description is
stored and displayed in full. New history entries abbreviate descriptions longer
than 240 characters to a 160-character preview, original character count and
SHA-256 fingerprint. Short values and existing history entries are unchanged;
an abbreviated entry does not contain enough text to reconstruct its old value.

Before a task creation or actual update, the service measures the proposed
history as BSON and rejects history above 8 MiB. It preserves the existing task,
version and history, leaving room below MongoDB's 16 MiB document limit. A no-op
does not append history or require additional history capacity. This is a bounded
storage policy, not unlimited audit retention; an administrator must resolve a
capacity error without silently discarding recorded changes.

Assignments must remain valid at mutation time. If an assignee becomes inactive,
suspended, loses committee membership, or has an unfinished membership access
update, an authorized task manager must reassign or clear the assignment before any task update,
including a status-only update. This preserves assignment validation rather than
allowing progress updates to retain an invalid delegate.

Normal committee deletion is blocked while tasks reference it. If a deletion
race or external database change nevertheless leaves a missing committee, task
pages identify the missing assignment. Updates fail validation until an officer
edits the task and chooses an existing committee or clears it to Organization.
This recovery does not expand member visibility rules.
