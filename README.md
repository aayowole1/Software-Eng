# OrgFlow

Chau preparation: [contribution report](docs/chau-contribution-report.md), [demo script](docs/chau-demo-script.md) and [completion checklist](docs/chau-completion-checklist.md).

See the [current deployment checks](docs/deployment-readiness.md) and
[production release/recovery runbook](docs/deployment-runbook.md) for the November 1 target.

OrgFlow is a Django web application using MongoDB and Docker for a consistent development environment.

This integration preview combines Chau's task-management work (SCRUM-16 / WBS 1.6),
Ayomide's events and attendance branch, and Jack's meeting recording branch on top
of the team's merged membership and account safeguards at `26b5177`.
See the [November 1 integration handoff](docs/integration-handoff.md) for tested
revisions, review responsibilities, and remaining team checks.
See the [task review and user guide](docs/tasks-checkpoint.md),
[acceptance checklist](docs/tasks-acceptance.md), and
[AI assistance record](docs/tasks-ai-use.md).
The [Accounts 1.3 checkpoint](docs/accounts-checkpoint.md) and its
[verification results](docs/verification-results.txt) preserve earlier history;
the account changes were subsequently merged through PR #7.

## Tech Stack

* Python 3.12
* Django 5.2.17 (matches `requirements.txt`)
* MongoDB
* Docker
* Docker Compose
* Git/GitHub

## Setup

Clone the repository:

```bash
git clone https://github.com/aayowole1/Software-Eng.git
cd Software-Eng
```

Start Docker Desktop and wait until it shows Docker is running. The commands below fail with "Cannot connect to the Docker daemon" until it is.

Build and start the containers:

```bash
docker compose up -d --build
```

You should see `orgflow_mongo` as **Healthy** and `orgflow_web` as **Started**. If not, see [Troubleshooting](#troubleshooting).

Run migrations:

```bash
docker compose exec web python manage.py migrate
```

Create your admin account (you can sign in with either the username or the email you enter):

```bash
docker compose exec web python manage.py createsuperuser
```

Check the project:

```bash
docker compose exec web python manage.py check
```

## Access

On the same machine:

```text
http://localhost:8000
```

If running inside a VM, use the VM's `192.168.x.x` address:

```text
http://192.168.x.x:8000
```

## Docker Services

* `web` â€” Django application
* `mongo` â€” MongoDB database
* `cleanup` â€” once an hour, deletes rejected membership applications 7 days after the decision

Django connects to MongoDB internally using:

```text
mongodb://mongo:27017
```

MongoDB data is stored in a persistent Docker volume.

## Features

Ported from the Software-Eng Node.js prototype (WBS 1.3, 1.4, 1.9) and aligned with the project proposal.

| App | What it does | Proposal |
|-----|--------------|----------|
| `accounts` | Sign-up (with a membership application) by username/email or Google, sign-in with either, organization roles, admin role management | FR-01, NFR-02 |
| `membership` | Membership applications, officer approve/reject, member roster | FR-02 |
| `committees` | Committees with a chair and members; officers manage rosters | FR-04 |
| `tasks` | Officer task creation and delegation; committee work, member claiming and progress, due dates, priorities, scoped counts and audit history | FR-04, FR-09; WBS 1.6 |
| `events` | Officers create, edit and cancel events; members RSVP; officers record attendance; upcoming events on the dashboard | FR-03, FR-08 (partial) |
| `announcements` | Published member feed, officer authoring, category/search filters, private attachment downloads and read receipts | FR-05 (partial), WBS 1.7 |
| Resource library (in `announcements`) | Member search/downloads and external links; Officer/Admin add/edit/remove | FR-07, WBS 1.7; [user guide](docs/resources-guide.md) |
| `meetings` | Officers submit meeting notes; AI drafts a summary and action items; an officer reviews before anything is kept | FR-06, FR-12 |
| `reports` | Participation and engagement report for officers and admins: attendance by event, member and committee, and task counts, for a chosen date range, with CSV download | FR-6.2, FR-6.3, WBS 1.8 |
| `core` | Public dashboard (signed-in users also see their own sections), `/health/` check, shared layout and styles | FR-08 (partial), NFR-03 |

### Roles

Each role includes everything the roles below it can do.

| Role | Can |
|------|-----|
| `applicant` | Waiting on a membership application (default for new accounts) |
| `member` | View the roster, committees and events; RSVP to events |
| `officer` | Create and manage events and record attendance; review applications, create committees and manage their rosters, submit and review meeting drafts; view participation reports |
| `admin` | Change anyone's role, delete committees and drafts |

Accounts created with `createsuperuser` are admins (see [Setup](#setup)).

### Joining

Creating an account is also the membership application: the sign-up form asks "Why do you want to join?". The new account stays switched off until an officer approves the application under **Applications**; approving switches it on and makes the person a member. Until then, signing in shows "Your membership application is still pending". Rejecting requires a reason. The rejected person can then sign in with applicant-only access, see "Not approved" with the officer's reason, and apply again from the same account **1 day** after the decision. Applications are kept with who reviewed them, when, and why (see **Applications â†’ Reviewed**); **rejected applications are deleted 7 days after the decision** by the `cleanup` service (the person's account stays). Without Docker, run `python manage.py purge_rejected_applications` on a schedule instead. Signing up with Google works the same way: Google confirms the email, then the person answers the same question.

The dashboard is public, so anyone can see how to join and the list of committees without signing in.

### Interrupted account updates

An officer's membership decision is recorded with a pending-access marker before
activation and role changes. If a database write fails, **Reviewed Applications**
shows **Finish account access** so an officer can retry the recorded decision
without changing its reviewer, note or date. Unfinished reviews are retained, and
sign-in, existing sessions and task eligibility stay blocked until completion.
The administrative suspension flag also blocks sign-in if the separate account
activation write has not completed.

Google application provisioning compensates for failed writes by removing only
the attempted account. Transient database failures show a retry form and preserve
the verified signup and statement. If the database also prevents cleanup, an
operator-recovery alert is logged; this does not claim a multi-document rollback.

### Forgot password

The sign-in page has a **Forgot your password?** link that emails a reset link. Accounts that sign in with Google, or that are still waiting for approval, don't get one.

By default, emails aren't actually sent: they're printed to the app's log. To see a reset link while developing:

```bash
docker compose logs web
```

To send real email, set `EMAIL_BACKEND` and the `EMAIL_HOST*` settings in `.env` (see `.env.example`), then run `docker compose restart web`.

Superuser accounts retain the Admin role; organization role management cannot
demote them. Migration `accounts.0002_backfill_profiles` gives preexisting users
missing profiles an Applicant role (Admin for superusers), preserving existing
profiles. Run migrations before reviewing the user list.

### Google sign-in (Accounts 1.3)

Google sign-in is available when `GOOGLE_CLIENT_ID` is configured. See
[Accounts setup and review](docs/accounts-checkpoint.md) for configuration,
tests, and the remaining live-provider check. Existing password accounts are
not automatically linked by email. New Google accounts start as applicants.

### AI meeting drafts
`meetings/ai.py` uses OpenRouter to produce a concise discussion summary and
proposed action items. Set `OPENROUTER_API_KEY` in `.env`; this replaces the
previous `OPENAI_API_KEY` integration, so existing deployments must add the
OpenRouter key before meeting summaries will work again.
`OPENROUTER_MODEL` is optional and defaults to `openai/gpt-4o-mini`. The
response must be valid JSON with validated summary and action-item fields.
Action items are normalized to start with `Action:`, `TODO:`, or `- [ ]` before
they are saved. The officer's notes are sent alongside the Deepgram transcript.
Approved action items will become tasks once the task module (WBS 1.6) exists.

**Uploading a recording (FR-7.1).** Officers can also upload a recording made
elsewhere (phone, Zoom, Teams) on the Take notes or Revise page: mp3, m4a, wav,
webm, ogg, flac or mp4, up to 25 MB. The file goes straight to Deepgram's
pre-recorded API with the same model and speaker settings as live notes, the
transcript is added after any live transcript, and the audio is never stored.
No local FFmpeg is needed. If Deepgram is unavailable, the form keeps the
officer's notes and asks them to retry or submit without the recording. The
public proxy must allow 26 MB request bodies (see `docs/deployment-runbook.md`).

Meeting recording uses Deepgram real-time transcription. The browser sends
16 kHz mono PCM chunks to Django. Django writes the active session to a
uniquely named temporary PCM file, sends that file to Deepgram when recording
stops, saves the returned transcript in `MeetingDraft.transcript`, and deletes
the temporary file in all success and error paths. The officer can add notes
before submitting; both sources are retained and passed to OpenRouter.

### Participation reports (WBS 1.8)

Officers and admins open **Reports** in the sidebar (`/reports/`). Pick a start and
end date (the last 30 days by default); both days are included in full, in the
organization's time zone. The page shows:

* **Events held:** non-cancelled events in the range that have already started,
  with RSVPs going and attendance for each. Upcoming events are not counted.
* **Members:** events attended out of the events held since their membership
  started (their latest approval), attendance %, and tasks assigned, completed
  and overdue (tasks created in the range).
* **Committees:** members, attendance % across those events, and task totals.

Under the **Download CSV** heading, pick a report from the **Report** dropdown
and click **Download**. The download uses the date range currently selected.
**All reports (ZIP)** (the default) downloads one ZIP file,
`orgflow-report-all-{start}_{end}.zip`, containing the three CSVs below; or
choose a single report:

| Download | File name pattern | Columns |
|---|---|---|
| Events | `orgflow-report-events-{start}_{end}.csv` | Event, Date, Start time, Location, RSVPs going, Attended |
| Members | `orgflow-report-members-{start}_{end}.csv` | Member, Email, Role, Status, Attended, Events held, Attendance %, Tasks assigned, Tasks completed, Tasks overdue |
| Committees | `orgflow-report-committees-{start}_{end}.csv` | Committee, Members, Attendance %, Tasks total, Tasks completed, Tasks overdue |

Members are sorted by name. **Status** shows actual account access: `active`
(the same rule as the dashboard's Active members count), `suspended`, `pending`
(a membership approval still updating) or `disabled` (the account is switched
off). Each file is UTF-8 with a byte-order mark so that names with accents open
correctly in Excel. Attendance % is a plain number with one decimal place
(e.g. `66.7`), and cells with no value are blank rather than `N/A`. Cells that
start with `=`, `+`, `-`, `@`, tab or carriage return are escaped so
spreadsheets do not interpret them as formulas. An end date before the start
date, or an unknown report choice, is rejected with HTTP 400. Charts are not
included yet (SCRUM-37).

### Tasks and committee work

Officers and admins can create, edit and assign tasks with a due date and priority.
The assignee can update progress. Active, unsuspended committee members can see
their committee's work and claim its unassigned, unfinished tasks. Organization
tasks without a committee are visible to their assignee and officers. A member
removed from a committee loses access to that committee's tasks.

The task list supports search, committee, status, priority, assignee and overdue
filters. Completed and overdue counts respect the signed-in user's access.
The dashboard shows personal assignments, and committee pages link to their work.
Task state and its change history are written together in one MongoDB document;
an outdated form cannot silently overwrite a newer assignment or status.

Dates use the configured `TIME_ZONE`, defaulting to `America/Chicago`. A task is
overdue when its due date is before today and it is not Done. A committee with
tasks cannot be deleted until those tasks are moved or their committee is cleared;
its roster and task history remain intact if deletion is blocked.

Meeting recording sends 16 kHz mono PCM chunks from the browser to Django.
Jack's implementation buffers them in a temporary server-side PCM file, sends
the file to Deepgram when recording is finalized, and removes the file after
transcription or an explicit discard. The returned text can include speaker
labels. This preview does not verify live transcription or abandoned-recording
cleanup.

Set `DEEPGRAM_API_KEY` in `.env` before starting Docker:

```bash
DEEPGRAM_API_KEY=your-key-here
docker compose up -d --build
```

The API key remains on the server and is never sent to the browser. Review
Deepgram's current data-retention and processing terms before sending
sensitive meeting audio.

The opt-in Deepgram quality tests measure word error rate (WER) and character
error rate (CER) against the meeting fixtures:

```bash
DEEPGRAM_API_KEY=your-key-here docker compose exec web \
  python manage.py test meetings.tests.test_stt_deepgram -v 2
```

The tests cover [single_speaker.wav](meetings/testdata/single_speaker.wav)
against its text reference and
[multi_speakers.wav](meetings/testdata/multi_speakers.wav) against the
structured reference in `multi_speakers.jsonl`. They are skipped when
`DEEPGRAM_API_KEY` is absent. Speaker labels are removed before WER/CER
calculation because these metrics evaluate transcription text, not diarization
accuracy. The current acceptance thresholds are 35% WER and 25% CER.

### Not yet implemented

Announcements are integrated in this working branch; see the
[integration notes](docs/announcements-integration.md) for access rules, private
file storage and remaining committee-targeting/notification work. Participation
reports (1.8) are available to officers and admins; charts (SCRUM-37) are not
included yet. Task change history is included;
an organization-wide audit system remains separate. Live OpenAI summarization and
Deepgram transcription still need configured credentials and provider checks.
Existing local Google checks are recorded in the Accounts checkpoint; a fresh
deployment needs its own Google client configuration and live check.

## About page settings

The signed-out dashboard shows a public **About** section with the organization's
name, mission, benefits and a leadership contact link. Configure these in `.env`:

| Setting | Environment variable | Default |
|---------|----------------------|---------|
| Organization name | `ORG_NAME` | Placeholder text |
| Mission statement | `ORG_MISSION` | Placeholder text |
| Benefits of joining | `ORG_BENEFITS` | Pipe-separated list, e.g. `Networking\|Leadership skills` |
| Contact email | `ORG_CONTACT_EMAIL` | Empty (shows "Contact an officer after you sign in") |

Example `.env` entries:

```env
ORG_NAME=Acme Student Association
ORG_MISSION=We bring students together to build real-world skills.
ORG_BENEFITS=Professional networking|Leadership opportunities|Community events
ORG_CONTACT_EMAIL=officers@acme.edu
```

Restart the web container after changing these values:

```bash
docker compose restart web
```

## Running Tests

SCRUM-83's human pilot is not yet complete: no participants are currently
available. See the [pilot protocol and readiness evidence](docs/usability-pilot.md)
and blank results sheet. Automated HTTP checks and unit tests do not replace
the five-person unaided workflow/timing requirement.

Tests use Django's test framework and need MongoDB running:

```bash
docker compose exec web python manage.py test
```

## Troubleshooting

### "Cannot connect to the Docker daemon"

Docker Desktop isn't running. Open it, wait until it says it's running, and try again.

### "The container name "/orgflow_mongo" is already in use"

Another copy of OrgFlow on your machine already has a container with that name. The container names are fixed in `docker-compose.yml`, so only one copy can run at a time. If the other copy isn't running, remove its old container. This doesn't delete its data, which lives in a separate Docker volume:

```bash
docker rm orgflow_mongo orgflow_web
```

If the other copy is running, run `docker compose down` in its folder first.

### "dependency failed to start: container orgflow_mongo is unhealthy"

Check the MongoDB logs:

```bash
docker logs orgflow_mongo
```

If they say *"MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility"*, your Docker Desktop's Linux kernel is too new for MongoDB 8 (kernels 6.19 through 7.0.13 are affected). Upgrading MongoDB doesn't help. Fix it by updating Docker Desktop (**Check for updates**) to a version with kernel **7.0.14 or later**. Check your kernel with:

```bash
docker info --format '{{.KernelVersion}}'
```

Then run `docker compose up -d --build` again.

If no Docker Desktop update is available yet, you can run MongoDB 7 on your machine only. Create a `docker-compose.override.yml` file (don't commit it) containing:

```yaml
services:
  mongo:
    image: mongo:7
```

Then run `docker compose down && docker compose up -d --build`.

### "Please enter a correct username and password" at sign-in

Check the account's username and email:

```bash
docker compose exec web python manage.py shell -c "from django.contrib.auth.models import User; print(list(User.objects.values_list('username', 'email')))"
```

Use **Forgot your password?** on the sign-in page, or reset it from the command line using the **username** (not the email):

```bash
docker compose exec web python manage.py changepassword <username>
```

## Useful Commands

Start:

```bash
docker compose up -d
```

Stop:

```bash
docker compose down
```

Rebuild:

```bash
docker compose up -d --build
```

View containers:

```bash
docker compose ps
```

View Django logs:

```bash
docker compose logs -f web
```

## Team Workflow

Create a feature branch:

```bash
git checkout -b feature/feature-name
```

Commit changes:

```bash
git add .
git commit -m "Describe changes"
```

Push the branch:

```bash
git push -u origin feature/feature-name
```

Then create a Pull Request on GitHub.

## Notes

Do not commit:

```text
.env
.venv/
__pycache__/
```

<!-- The repository is available at:

```text
git@github.com:Tmonstah/OrgFlow.git
```
-->
