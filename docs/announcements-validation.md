# Announcements integration validation — November 3, 2026

Working branch: `feature/announcements-integration`, based on main `e404ce4`.
Imported app source: `origin/jack/announcements` at `642352f`, with the local
integration/access/storage/template changes described in
[the integration notes](announcements-integration.md). These are local results,
not GitHub CI or production deployment results.

| Check | Observed result |
|---|---|
| Initial focused announcements run | 46 tests passed, 9.431 seconds |
| Full Django regression | 707 collected: 705 passed, 2 live Deepgram skips, 151.711 seconds |
| Final focused run after optional General-category form change | 47 tests passed, 9.257 seconds |
| Migration drift check, full and final focused runners | No changes detected |
| Django system checks | No issues |
| Existing sidebar navigation interaction tests | 7 passed using Node 24.22.1 |
| Announcement template compilation / shared layout smoke render | Passed |
| Python compilation and `git diff --check` | Passed |

The final category change and its new test followed the full run; they received
the final focused regression, not another full-suite run. Counts overlap and
must not be added as unique cases. No new whole-project coverage measurement
was made.

Tests used Python 3.12.14, the declared requirements in an isolated `.venv`, and
portable MongoDB 8.0.16 bound to localhost:27029. The full/final runners used a
disposable `test_orgflow_announcements_full_validation` database and stopped their
owned MongoDB process after completion. Provider credentials were cleared and
private dotenv loading disabled. A fast MD5 password hasher was set only in the
test process; application password configuration was not changed. No live AI,
Google or email service was contacted.

Earlier attempts failed because the sandbox blocked localhost sockets, and a
subsequent attempt found the prior database process no longer running. Starting
the isolated database and test process together outside the sandbox resolved
the environment issue. These failed setup attempts are not application failures
or passing tests.

Docker is unavailable on this machine. Production image build, named-volume
ownership/persistence, container smoke/recovery and real browser/accessibility
acceptance remain pending. File contents must be included in backup procedures
alongside the database.
