# Announcements integration

This working integration imports the announcements app from Jack's branch at
`642352f`, retaining its authorship and migrations. It preserves main's shared
layout, navigation and transcription references. Templates use the existing
OrgFlow stylesheet, with labeled search/filter controls and ordinary form fields.

## Access and storage

- Active Members can search and read published announcements and download their
  attachments. Applicants cannot access the feed or files.
- Officers and Admins can create notices and view unpublished notices. An Officer
  edits their own notices; organization Admins can edit any notice. Django staff
  flags and an `Officer` group do not grant organization publishing authority.
- Every endpoint rechecks current account activation, suspension, pending
  suspension and membership-access updates, using the existing authentication
  backend rules and current organization profile role.
- Mark-read accepts POST only and checks publication visibility. Attachments use
  an authenticated download route with attachment disposition and private,
  no-store caching. Do not configure a public `/media/` server route.
- Uploads allow up to five files per request, each no larger than 25 MiB.
- Development stores files in `media/`. Production uses the `media_data` volume
  at `/var/lib/orgflow/media`, owned by the application container user. Set
  `DJANGO_MEDIA_ROOT` when using another storage location.

## Deployment

Run the existing release migration command before starting the updated web
image. Both existing announcements migrations are required. The production
Dockerfile copies the announcements app, and the web service mounts private
media separately from read-only static files. Existing deployments must recreate
their image/container to gain these changes.

Back up `media_data` together with the database and restore both to an isolated
environment when rehearsing recovery. A database-only backup cannot restore
uploaded file contents. Volume persistence and container ownership still require
the production smoke/recovery check on a Docker host.

## Current scope and remaining SCRUM-17 work

This increment supplies the feed, category/search/status filters, authoring,
manual publication, attachment downloads and read receipts. It removes the
imported hardcoded average read-rate statistic.

Scheduled notices remain private until an officer explicitly switches their
status to Published; this increment does not provide a scheduler. Categories
can be managed through Django admin; officers can publish under General without
preconfigured categories. The follow-up now provides the
[resource library and deletion flows](resources-guide.md)
and recent published dashboard announcements. Committee-specific targeting,
in-app notifications, automatic scheduled publication and a full
accessibility/browser acceptance pass remain separate work. This does not
close all of SCRUM-17.

Announcement save, attachment writes and read telemetry are separate writes.
They do not provide transaction-style recovery after a storage/database error.
Removed attachment records may leave files requiring a later orphan-file cleanup
policy. Do not claim the resource-hub recovery acceptance criteria from this
initial integration alone.

## Validation

Run `python manage.py test announcements` against a disposable MongoDB database,
then the complete Django suite, migration drift check and navigation tests.
`announcements/tests/test_permissions.py` covers organization roles versus Django
staff/groups, current account guards, hidden draft access, protected downloads,
upload count validation and the POST-only mark-read endpoint. Local execution
results are recorded in the [validation receipt](announcements-validation.md).
