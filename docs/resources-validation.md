# Resource library follow-up validation — November 4, 2026

Local working branch: `feature/announcements-integration`, based on main
`e404ce4`; results were collected before the review commit. This follow-up adds resource file/link CRUD,
search/category filtering, protected open/download, announcement deletion and
recent published dashboard announcements.

| Check | Result |
|---|---|
| Initial announcements/resources focused suite | 68 tests passed in 12.360 seconds |
| Full regression including dashboard additions | 732 collected: 730 passed, 2 live Deepgram skips; 131.301 seconds |
| Final focused suite after stored-file repair validation change | 72 tests passed in 11.805 seconds |
| Migration drift | No changes detected after generating `0003_resource` |
| Django system check | No issues |
| Existing sidebar interaction tests | 7 passed |
| Whitespace/diff check | Passed |
| Local review database upgrade | `announcements.0003_resource` applied successfully; preview readiness passed |
| Running-preview HTTP smoke | Member and Officer login, library and private downloads passed; member creation denied (403), officer creation form allowed (200); dashboard showed published notices only |

The final form change limits size validation to new uploads so a missing stored
file does not block metadata repair. It and its new test followed the full run;
the final focused suite covers the latest source. Counts overlap and are not
additive. No new coverage percentage is claimed.

The isolated runner used Python 3.12.14, the declared requirements and portable
MongoDB 8.0.16 on localhost:27029, with a separate synthetic test database.
Private dotenv loading was disabled and provider keys cleared. The fast MD5
password hasher was scoped to the test process only. Each test runner stopped
its owned MongoDB process; the separate preview database on port 27030 remains
running for user review. Application password settings were not changed.

Focused cases cover:

- Member browsing, title/description search, category filters and private downloads.
- Officer/Admin add/edit/remove, file replacement and conversion to a link.
- Applicants, anonymous users, unrelated staff/groups and suspended actors denied
  their prohibited operations; mutation requests require CSRF.
- Exactly one file/link, HTTP(S)-only URLs, maximum upload size and missing files.
- GET deletion confirmation versus POST deletion, author/Admin notice deletion
  permissions, and removed records becoming inaccessible through download routes.
- Dashboard published-only visibility, member/officer access, anonymous/Applicant
  exclusion and a three-announcement limit.

Production Docker image build, volume ownership, physical file retention/cleanup,
backup/restore, formal accessibility and peer/team demo acceptance remain open.
Removed/replaced physical files are retained; record removal is not secure erasure.
No Jira statuses, comments, remote branches or pull requests were changed.
