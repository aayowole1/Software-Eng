# Jira review readiness — November 4, 2026

This review package builds on Jack's announcements branch at `642352f` and main
`e404ce4`. It adds integration with the existing organization role/account guards,
protected downloads, refreshed templates, resource management, announcement
deletion, recent dashboard notices, tests and deployment/storage configuration.
The inherited announcements foundation and AI/task safeguards retain their
original authorship. Jira status changes and peer acceptance are separate.

| Ticket | Review disposition |
|---|---|
| SCRUM-30 — Resource upload and links | Implemented: organization file/link creation and management, HTTP(S) validation and protected downloads. |
| SCRUM-31 — Announcements feed UI | Implemented: pinned notices, search/category/status filters and existing responsive layout. Human browser/mobile acceptance pending. |
| SCRUM-32 — Resource library UI | Implemented: browse/search/filter, file/link opening and Officer/Admin management. |
| SCRUM-33 — Tests | Announcements/resources focused suite: 72 tests passed. See validation scope below. |
| SCRUM-42 — Regression run | Full local run recorded: 732 collected, 730 passed, 2 live Deepgram skips. Latest small file-repair change received focused regression afterward. |
| SCRUM-29 — Announcement API | Create/edit/pin/delete form endpoints implemented. Team must accept the HTTP/form contract or specify a separate JSON API before closure. |
| SCRUM-34 — Docs/demo | User guide, integration notes, test receipts and running local demo prepared. Team demonstration acceptance pending. |
| SCRUM-66 — Shared documents/links | Stated member browse/search and Officer/Admin add/edit/remove/access controls implemented. Ready for acceptance review. |
| SCRUM-67 — Dashboard | Recent published announcements now accompany inherited events and personal tasks. Ready for acceptance review; inherited features are not new authorship. |
| SCRUM-70 — Announcement/AI workflow | New announcement functionality combines with inherited approved-only AI task import. Ready for combined acceptance review. |

## Validation and review limits

- [Follow-up validation](resources-validation.md): full regression, final focused
  suite, seven sidebar tests, clean system/migration checks and running-preview
  member/officer HTTP smoke.
- [User walkthrough](resources-guide.md) and [integration notes](announcements-integration.md).
- No new branch coverage measurement, formal accessibility audit, real provider
  calls, production Docker build or backup/restore validation was performed.
- Production needs migration `announcements.0003_resource` and a rebuilt image
  with the private media volume. Media files must be backed up with the database.
- Removed/replaced physical files are retained; orphan cleanup and retention
  policy remain open. Database and file changes are not transactional.
- Committee-specific visibility, notifications and automatic scheduled publication
  remain outside this increment. The complete SCRUM-17 story is not declared Done.

Reviewers should verify both member and officer flows using synthetic data,
confirm the API contract and retention policy, and record acceptance before
changing Jira tickets to Done.
