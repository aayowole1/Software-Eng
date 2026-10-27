# Announcements module

## Overview

The announcements module lets authenticated users view organization
announcements. Officers and administrators can create and edit announcements,
publish or schedule them, attach files, and monitor basic read metrics.

The module is registered as `announcements.apps.AnnouncementsConfig` in
`orgflow_project/settings.py` and is mounted under `/announcements/`.

## AI attestation
The announcements page UI was developed using Google Stitch. First, a vague idea of
how the UI should look like was pitched to Google Stitch and refinement was done
on Google Stitch's output. Google Stitch then suggested Python code to integrate its
UI with Django and VS Code's Copilot interface was used to fix errors with the integration.

## App structure

| File or directory | Purpose |
|---|---|
| `announcements/models.py` | Defines categories, announcements, attachments, and read receipts |
| `announcements/forms.py` | Defines create/edit and attachment forms |
| `announcements/views.py` | Handles listing, creation, editing, detail, and read actions |
| `announcements/urls.py` | Defines namespaced announcement routes |
| `announcements/admin.py` | Registers announcement models with Django admin |
| `announcements/templates/announcements/` | Contains page, form, detail, and card templates |
| `announcements/migrations/` | Contains MongoDB-compatible migrations |
| `announcements/tests.py` | Reserved for module tests |

The global navigation sidebar is defined in
`core/templates/base.html`. It includes announcement links for all
announcements, drafts, and scheduled announcements. Individual announcement
pages should not add another sidebar.

## Data model

### `Category`

Stores an announcement category and its URL-friendly slug.

| Field | Type | Description |
|---|---|---|
| `name` | `CharField` | Category display name |
| `slug` | `SlugField` | Unique URL-friendly identifier |

### `Announcement`

| Field | Type | Description |
|---|---|---|
| `title` | `CharField` | Announcement title |
| `content` | `TextField` | Announcement body |
| `status` | Choice field | `draft`, `scheduled`, `published`, or `archived` |
| `is_pinned` | `BooleanField` | Keeps the announcement at the top of the list |
| `is_urgent` | `BooleanField` | Marks the announcement as urgent |
| `category` | Foreign key | Optional category |
| `author` | Foreign key | User who created the announcement |
| `author_role` | `CharField` | Role displayed with the author |
| `published_at` | `DateTimeField` | Publication timestamp |
| `scheduled_for` | `DateTimeField` | Optional scheduled publication time |
| `created_at` | `DateTimeField` | Creation timestamp |
| `updated_at` | `DateTimeField` | Last update timestamp |
| `meeting_location` | `CharField` | Optional physical meeting location |
| `meeting_virtual_url` | `URLField` | Optional virtual meeting link |
| `read_count` | `PositiveIntegerField` | Number of recorded reads |
| `target_reach` | `PositiveIntegerField` | Expected audience size |
| `comments_count` | `PositiveIntegerField` | Stored comment count |

Announcements are ordered by pinned status and publication time. The
`read_percentage` property calculates the read percentage without exceeding
100 percent.

### `AnnouncementAttachment`

Stores files attached to an announcement, including the uploaded file name and
a human-readable size label.

### `AnnouncementReadReceipt`

Records when a user reads an announcement. Each user can have one read receipt
per announcement.

All models use the project's MongoDB-compatible
`ObjectIdAutoField` configuration.

## URLs

The project includes the app with:

```python
path("announcements/", include("announcements.urls"))
```

The app uses the `announcements` URL namespace.

| URL | Name | Purpose |
|---|---|---|
| `/announcements/` | `announcements:list` | List announcements |
| `/announcements/create/` | `announcements:create` | Create an announcement |
| `/announcements/<id>/` | `announcements:detail` | View one announcement |
| `/announcements/<id>/edit/` | `announcements:edit` | Edit an announcement |
| `/announcements/<id>/read/` | `announcements:mark_read` | Record a read receipt |

Use namespaced URL references in templates and redirects:

```django
{% url "announcements:list" %}
{% url "announcements:create" %}
{% url "announcements:detail" announcement.id %}
```

## Access and behavior

- All announcement pages require authentication.
- Regular members see published announcements.
- Officers and staff administrators can view status filters, create
  announcements, and edit announcements they are allowed to manage.
- The list supports search with the `q` query parameter.
- The list supports category filtering with the `category` query parameter.
- Staff and officers can filter by status with the `status` query parameter:
  `draft`, `scheduled`, or `all`.
- Pinned announcements appear first.
- The shared sidebar provides links to all announcements, drafts, and
  scheduled announcements.
- The announcement page displays an empty-state message when no records match
  the current filters.

## Templates and styling

The main templates are:

| Template | Purpose |
|---|---|
| `announcements_page.html` | Announcement feed and admin/member dashboard |
| `announcement_form.html` | Create and edit form |
| `announcement_detail.html` | Full announcement view |
| `partials/_card.html` | Reusable announcement card |

These templates extend the shared
`core/templates/base.html` layout. Global typography, sidebar styling,
responsive layout, focus states, and announcement utility classes are provided
by `core/static/core/site.css`.

## Development commands

Run project checks:

```bash
docker compose exec web python manage.py check
```

Create and apply migrations after changing models:

```bash
docker compose exec web python manage.py makemigrations announcements
docker compose exec web python manage.py migrate
```

Run the module tests:

```bash
docker compose exec web python manage.py test announcements
```

Open the module locally:

```text
http://localhost:8000/announcements/
```

## Future work

- Add comprehensive model, view, URL, permission, and template tests.
- Add a dedicated test package if the module grows beyond one test file.
- Add scheduled-publication processing if scheduled records should publish
  automatically.
- Add pagination for larger announcement feeds.
- Add a dedicated comment model and workflow if comments become supported.
- Add explicit authorization tests for officer and administrator actions.
