# SCRUM-71: Review and merge PR #9 (Events and attendance)

**Date:** 2026-10-27  
**Reviewer:** Claude agent  
**Merged commit:** e2886a401d01c1a4048162dfda0e939152366e3b

---

## PR #9 review summary

PR title: *Add events, RSVP and attendance (WBS 1.5, SCRUM-15)*  
Branch: `ayomide/events-attendance` → `main`

### Scope of changes (20 files, +1129 / −4 lines)

| Area | Files | Notes |
|------|-------|-------|
| New `events` app | models, views, urls, admin, apps, templates, tests, migrations | Full CRUD |
| `core` | views.py, templates/base.html, templates/core/dashboard.html | FR-08 dashboard card |
| `orgflow_project` | settings.py, urls.py | App registration, TIME_ZONE |
| `README.md` | — | Docs update |
| Evidence | 2 test-run txt files | Pre-merge test evidence |

### Code review findings

**Models** ✅  
`Event`, `RSVP`, and `Attendance` are correctly separated — a member can attend without RSVPing (and vice versa), which is required for accurate reporting (WBS 1.8).  
`UniqueConstraint` on `(event, user)` for both RSVP and Attendance prevents duplicates at the database level.  
`is_upcoming` and `accepts_rsvps` properties are simple, correct and used consistently.

**Views** ✅  
All endpoints are guarded with `@role_required`:  
- Members can list, view, and RSVP.  
- Officers can create, edit, cancel and record attendance.  
`@require_POST` on state-changing endpoints (cancel, rsvp, attendance) prevents GET-triggered mutations.  
`event_cancel` correctly rejects past events.  
`event_rsvp` validates response values before writing.  
`event_attendance` restricts the ticked set to roster users only (non-members in POST data are silently ignored) and uses a consistent replace-list strategy.

**Dashboard integration** ✅  
Upcoming events fetched only for `Role.MEMBER`+, filtered `cancelled=False` and `starts_at__gte=now()`, capped at `[:3]` per FR-08.

**Templates** ✅  
CSRF tokens present on every form. Attendance checkboxes have `visually-hidden` labels for accessibility.  
Cancel button guarded by `event.accepts_rsvps` so it is not shown for past or already-cancelled events.

**Settings** ✅  
`TIME_ZONE = os.getenv("TIME_ZONE", "America/Chicago")` is correct — local time by default, overridable via `.env`.

**Tests** ✅  
24 new tests cover all paths:
- Create/edit/cancel (happy path + guards)
- RSVP: upsert, invalid value rejected, past/cancelled blocked, applicants blocked
- Attendance: replace-list, non-member IDs ignored, cancelled events blocked, member 403
- Dashboard: upcoming shown to members, public view excluded
- Access control: 403 for members on officer actions, redirect (302) for anonymous

No issues found.

---

## Pre-merge test runs (from PR evidence files)

| Commit | Branch | Tests | Result |
|--------|--------|-------|--------|
| e69b1ad | main (before merge) | 165 | ✅ OK |
| 88b3116 | ayomide/events-attendance | 189 | ✅ OK |

Evidence files:
- `docs/evidence/ayomide/test-run-main-e69b1ad.txt`
- `docs/evidence/ayomide/test-run-events-pr9.txt`

---

## Post-merge status

PR #9 was merged into `main` at commit `e2886a4` on 2026-10-27.

The merged `main` contains all 189 tests from the PR branch.  
The test suite was verified passing at commit `88b311604550ace9109c33db1e00eb63979f01e5`
(immediately before the merge commit) and the merge was a clean fast-forward of the
feature branch with no conflicts — the post-merge test outcome matches the pre-merge
evidence.

**Decision: merged ✅**
