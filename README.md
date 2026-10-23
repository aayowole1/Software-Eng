# OrgFlow

OrgFlow is a Django web application using MongoDB and Docker for a consistent development environment.

This local `chau/accounts-progress` checkout includes an Accounts 1.3 checkpoint.
See [the review guide](docs/accounts-checkpoint.md) and
[verification results](docs/verification-results.txt). The changes have not been
pushed; the clone command below retrieves the team's baseline branch. Use the
prepared checkpoint folder/archive to review the new work.

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
git clone --branch django-conversion https://github.com/aayowole1/Software-Eng.git
cd Software-Eng
```

Start Docker Desktop and wait until it shows Docker is running. The commands below fail with "Cannot connect to the Docker daemon" until it is.

Build and start the containers (takes approx. 157 seconds):

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

* `web` — Django application
* `mongo` — MongoDB database
* `cleanup` — once an hour, deletes rejected membership applications 7 days after the decision

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
| `meetings` | Officers submit meeting notes; AI drafts a summary and action items; an officer reviews before anything is kept | FR-06, FR-12 |
| `core` | Public dashboard (signed-in users also see their own sections), `/health/` check, shared layout and styles | FR-08 (partial), NFR-03 |

### Roles

Each role includes everything the roles below it can do.

| Role | Can |
|------|-----|
| `applicant` | Waiting on a membership application (default for new accounts) |
| `member` | View the roster and committees |
| `officer` | Review applications, create committees and manage their rosters, submit and review meeting drafts |
| `admin` | Change anyone's role, delete committees and drafts |

Accounts created with `createsuperuser` are admins (see [Setup](#setup)).

### Joining

Creating an account is also the membership application: the sign-up form asks "Why do you want to join?". The new account stays switched off until an officer approves the application under **Applications**; approving switches it on and makes the person a member. Until then, signing in shows "Your membership application is still pending". Rejecting requires a reason. The rejected person can then sign in with applicant-only access, see "Not approved" with the officer's reason, and apply again from the same account **1 day** after the decision. Applications are kept with who reviewed them, when, and why (see **Applications → Reviewed**); **rejected applications are deleted 7 days after the decision** by the `cleanup` service (the person's account stays). Without Docker, run `python manage.py purge_rejected_applications` on a schedule instead. Signing up with Google works the same way: Google confirms the email, then the person answers the same question.

The dashboard is public, so anyone can see how to join and the list of committees without signing in.

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

`meetings/ai.py` is a **rule-based placeholder**: lines starting with `Action:`, `TODO:` or `- [ ]` become proposed action items, and the first few sentences become the summary. Replace `summarize_meeting()` with a real model call (keep the same return type) and evaluate it with DeepEval. Approved action items will become tasks once the task module (WBS 1.6) exists.

Meeting recording uses Deepgram real-time transcription. The browser sends
16 kHz mono PCM chunks to Django, and Django maintains a private Deepgram
WebSocket for each recording. Deepgram returns interim and final text with
speaker labels when available. Audio is not written to disk or retained by
OrgFlow; only the resulting meeting notes are saved when the user submits the
form.

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

Events and attendance (1.5), tasks (1.6), announcements and resources (1.7), reports (1.8), and audit history (FR-09). Google sign-in still requires a configured Google client and a live end-to-end check.

## Running Tests

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
