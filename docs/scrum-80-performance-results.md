# SCRUM-80 local measurement — November 4, 2026

The user selected the current local application rather than a deployed host.
The complete local measurement meets the ticket's aggregate criterion: at least
95% of requests under three seconds. This result is scoped to the measured HTML
page workload; it does **not** establish a per-page pass for every endpoint or
production-host/browser performance acceptance.

## Executed comparison

| Metric | Failed baseline | Roster pagination fix |
|---|---:|---:|
| Application revision | `dd20440` (application code unchanged from `4dcc933`) | `9c61b10` |
| Planned measurement window | 600 seconds | 600 seconds |
| Virtual users / think time | 25 / 1 second | 25 / 1 second |
| Requests | 7,009 | 7,335 |
| Successful HTTP responses | 6,976 | 7,335 |
| Errors | 33, all on roster | 0 |
| Successful requests strictly below 3 seconds | 90.398% | **95.869%** |
| Aggregate p95 | 5.8276 seconds | **2.8632 seconds** |
| Roster p95 | 9.4326 seconds | **2.2869 seconds** |
| Aggregate target | Fail | **Pass** |

The measurement window accepts requests starting during 600 seconds and drains
in-flight requests afterward (recorded elapsed time is about 601 seconds).
Percentiles use nearest rank. Errors never count as successful fast responses.
Logins and per-account page warm-up precede the measured window; their timings
are retained separately. Both runs used normal application password hashing.

Equivalent fresh synthetic datasets contained 500 active organization members,
100 events, 1,000 tasks, 10 committees, 2,500 RSVPs, 1,250 attendance rows,
50 announcements, 50 resources and 20 meeting drafts. Twenty Member and five
Officer accounts cycled the same role-appropriate page paths. The separate
review app/database on port 8000 was not modified by the benchmark.

## Per-page fixed result

| Page | Requests | Successful under 3s | p95 seconds |
|---|---:|---:|---:|
| Personal profile | 879 | 100.000% | 0.8829 |
| Announcements | 882 | 97.392% | 2.8086 |
| Committees | 880 | 100.000% | 1.1790 |
| Dashboard | 880 | 99.432% | 2.2499 |
| **Events** | 881 | **75.369%** | **4.5055** |
| Meeting drafts | 143 | 100.000% | 1.9657 |
| Membership applications | 143 | 100.000% | 1.0826 |
| Member roster | 880 | 99.205% | 2.2869 |
| Resources | 884 | 97.285% | 2.5095 |
| Tasks | 883 | 96.942% | 2.8700 |

The events list remains a hotspot and does **not** meet the threshold when
evaluated alone. It renders the entire 100-event history without pagination.
The next performance action should investigate/bound event-list rendering and
repeat its measurements. Aggregate SCRUM-80 measurement closure is not a claim
that this individual page is fast enough. The aggregate pass also has limited
headroom; different hardware or traffic mixes may produce different results.

## Implemented fix

The roster previously rendered all 500 members and committee entries in one
response. It now returns 25 members per page with a deterministic alphabetical
order, keeps search/role filters in navigation links and handles invalid/empty
pages. Role checks remain unchanged. No database migration or password/auth
configuration change was required.

Validation:

- All **75 membership tests passed** in 13.693 seconds, including new page-size,
  full traversal/no-duplicates, filter preservation, invalid/empty-page and
  Applicant-denial cases.
- Five standalone benchmark-summary tests passed, checking the strict 3-second
  boundary, failures, no samples and the 95% threshold.
- CI for `9c61b10`: **738 collected, 736 passed, two live Deepgram skips**,
  277.730 seconds. Both integration and synthetic deployment-smoke jobs passed:
  [run 41971790070](https://github.com/aayowole1/Software-Eng/actions/runs/41971790070).
- System and migration-drift checks were clean.

## Reproduction and retained evidence

- [Benchmark protocol and commands](performance-benchmark.md).
- [Failed baseline JSON](evidence/scrum80-20261104/baseline.json).
- [Fixed-run JSON](evidence/scrum80-20261104/after.json).
- [Dataset counts](evidence/scrum80-20261104/dataset.json).
- Scripts: `deploy/seed_benchmark.py`, `deploy/benchmark_pages.py` and
  `deploy/settings_benchmark.py`.

Both runs used Windows 11, Python 3.12.14, MongoDB 8.0.16 and Django's threaded
development server on localhost:8001 with DEBUG=False. Private dotenv loading
and live provider settings were disabled. This is not the production
Gunicorn/container/TLS topology. The benchmark processes stopped after each
run. Results contain no account passwords, session cookies or page bodies;
synthetic accounts/database/log files remain outside Git and Docker images.

The performance fix is proposed in PR #23 and is not a claim that main has
already received the change. Deployment, browser rendering, static assets,
provider/network calls and write-path performance require separate acceptance.
