# OrgFlow

OrgFlow is a Django web application using MongoDB and Docker for a consistent development environment.

## Tech Stack

* Python 3.12
* Django 6.1
* MongoDB
* Docker
* Docker Compose
* Git/GitHub

## Setup

Clone the repository:

```bash
git clone git@github.com:Tmonstah/OrgFlow.git
cd OrgFlow
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

* `web` — Django application
* `mongo` — MongoDB database

Django connects to MongoDB internally using:

```text
mongodb://mongo:27017
```

MongoDB data is stored in a persistent Docker volume.

## Features

Ported from the Software-Eng Node.js prototype (WBS 1.3, 1.4, 1.9) and aligned with the project proposal.

| App | What it does | Proposal |
|-----|--------------|----------|
| `accounts` | Sign-up with a username and email, sign-in with either, organization roles, admin role management | FR-01, NFR-02 |
| `membership` | Membership applications, officer approve/reject, member roster | FR-02 |
| `committees` | Committees with a chair and members; officers manage rosters | FR-04 |
| `meetings` | Officers submit meeting notes; AI drafts a summary and action items; an officer reviews before anything is kept | FR-06, FR-12 |
| `core` | Public landing page, dashboard, `/health/` check, shared layout and styles | FR-08 (partial), NFR-03 |

### Roles

Each role includes everything the roles below it can do.

| Role | Can |
|------|-----|
| `applicant` | Apply for membership (default for new accounts) |
| `member` | View the roster and committees |
| `officer` | Review applications, create committees and manage their rosters, submit and review meeting drafts |
| `admin` | Change anyone's role, delete committees and drafts |

Accounts created with `createsuperuser` are admins (see [Setup](#setup)).

### AI meeting drafts

`meetings/ai.py` is a **rule-based placeholder**: lines starting with `Action:`, `TODO:` or `- [ ]` become proposed action items, and the first few sentences become the summary. Replace `summarize_meeting()` with a real model call (keep the same return type) and evaluate it with DeepEval. Approved action items will become tasks once the task module (WBS 1.6) exists.

### Not yet implemented

Events and attendance (1.5), tasks (1.6), announcements and resources (1.7), reports (1.8), audit history (FR-09), and Google sign-in.

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

To reset a password, use the **username** (not the email):

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

The repository is available at:

```text
git@github.com:Tmonstah/OrgFlow.git
```
