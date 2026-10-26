# Task mutation limits and recovery

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
update, an officer must reassign or clear the assignment before any task update,
including a status-only update. This preserves assignment validation rather than
allowing progress updates to retain an invalid delegate.

Normal committee deletion is blocked while tasks reference it. If a deletion
race or external database change nevertheless leaves a missing committee, task
pages identify the missing assignment. Updates fail validation until an officer
edits the task and chooses an existing committee or clears it to Organization.
This recovery does not expand member visibility rules.
