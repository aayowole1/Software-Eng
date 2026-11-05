# Shared resources and announcement deletion

## Member walkthrough

1. Sign in with an active Member, Officer or Admin account.
2. Open **Resources** in the navigation. Search by title/description or choose a
   category. The library shares organization-wide resources with active members.
3. Choose **Download document** for a private, authenticated file download or
   **Open link** to visit an external HTTP(S) website.
4. The dashboard now shows up to three recent published announcements. Draft,
   scheduled and archived notices are excluded, including on officer dashboards.

Anonymous users and Applicants cannot browse or open resources. Existing account
suspension and unfinished account-access updates also block resource access.
External websites have their own access rules after the user follows a link.

## Officer/Admin walkthrough

1. Open **Resources → Add resource**. Enter a title, optional description and
   category, then choose exactly one file (up to 25 MiB) or HTTP(S) link.
2. Save and verify that the resource appears in member search results.
3. Use **Edit** to update metadata, replace the document, or clear the existing
   document and enter a link. Officers/Admins can manage any library resource.
4. Use **Remove**, review the confirmation and submit **Delete resource**.
   Merely visiting the confirmation screen does not remove anything.
5. For announcements, authors can delete their own notices and organization
   Admins can delete any notice. Other Officers cannot delete another author's
   notice. Use **Delete announcement** on its detail page and confirm.

## Routes and implementation

- `/resources/`: searchable/filterable library.
- `/resources/create/`, `/resources/<id>/edit/`: GET forms, POST saves.
- `/resources/<id>/delete/`: GET confirmation, POST removal.
- `/resources/<id>/open/`: current-account-authorized file download or validated
  external redirect. File paths are never exposed as public media URLs.
- `/announcements/<id>/delete/`: GET confirmation, POST deletion.

All mutations use the existing session and CSRF middleware. The endpoints are
Django HTTP/form endpoints; no separate JSON REST API is introduced.

Run migration `announcements.0003_resource` before using the updated application.
Files use the existing private `MEDIA_ROOT`/production `media_data` volume.
Production needs a rebuilt image and its normal explicit migration release step.
Do not expose the media directory through a public web-server route.

## Retention and limits

Removing a resource or announcement removes its application records and access
through the protected routes. Physical file bytes are retained. Replacing a
file can also leave the previous bytes. This avoids deleting a file that a
backup or interrupted request still references, but requires an operator-owned
retention/orphan cleanup policy. Back up and restore files alongside MongoDB.
Database and storage changes are separate operations, without transactional
rollback or automatic cleanup guarantees.

This library is organization-wide; committee-specific visibility and notifications
remain separate work. No external URL is fetched by the application server.
Automated layout rendering and HTTP tests do not replace a human accessibility
review or production container/recovery validation.

## Jira traceability

- SCRUM-29: deletion now accompanies create/edit/pin; confirm that the team
  accepts the existing HTTP/form API contract before closing the API subtask.
- SCRUM-30 and SCRUM-32: organization resource upload/link management and library UI.
- SCRUM-33: resource lifecycle, permission, validation and download regressions.
- SCRUM-34: this guide and local demo preparation; team demo acceptance pending.
- SCRUM-66: member search/access and officer/admin add/edit/remove flows.
- SCRUM-67: recent announcements added alongside inherited events/tasks.

These are implementation mappings, not Jira status changes or peer approval.

See the [follow-up validation receipt](resources-validation.md) for local test
results and remaining release checks.
