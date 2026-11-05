# SCRUM-83: five-user pilot protocol and current readiness

## Current status — November 4, 2026

**Human pilot not run. Human participants: 0. Acceptance: not evaluated.**
The user cannot currently recruit participants. SCRUM-83 requires five actual
users, with at least four completing a core workflow unaided within three
minutes. It cannot be closed from automated tests, five AI personas, hypothetical
timings, or repeated runs by one person. An alternative assessment only replaces
this criterion if the project/course owner explicitly approves that change.

Five synthetic HTTP readiness workflows passed on the local review app:

| Automated readiness workflow | Outcome |
|---|---|
| Member login and dashboard | Pass |
| Find upcoming event and save RSVP | Pass |
| Search resource and download document | Pass |
| Update an assigned task's progress | Pass |
| Officer publishes a notice; member reads the feed | Pass |

[The machine-readable result](evidence/scrum83-20261104/http-readiness.json)
explicitly records zero humans and does not count toward SCRUM-83. The browser
automation helper failed to initialize (`failed to write kernel assets`, path
not found), including after retry/reset. These were HTTP checks, not rendered
browser inspection, accessibility assessment or a usability study. No human
completion times, satisfaction results or unaided success rates were inferred.

The scoring helper's eight unit tests and five benchmark-summary tests passed
(13 total standalone tool checks). These are synthetic software tests, not
participant observations. The blank pilot sheet remains INCOMPLETE.

The checks created clearly named `SCRUM83 readiness <run-id>` demo event, task,
resource and announcement fixtures in the isolated `orgflow_local_review`
database. They did not contact real participants or external services. The
resource fixture uses private file storage. Do not reuse their completed RSVP
or task state as a clean human-test starting state.

## Human test protocol (prepared, not executed)

Use five distinct people representative of prospective organization members.
Assign anonymous IDs P01–P05, not real names in the repository. Use the same
application revision, environment, device setup and task goal for the cohort.
Record device/browser and prior exposure so learning effects are visible.

### Pre-session setup

- Prepare five active synthetic Member accounts and one clearly named upcoming
  pilot event. Each account must have no existing RSVP for that event.
- Check the app, account credentials and event availability before participants
  begin. Use a separate browser session per participant; sign out the previous
  user. Keep test notes/route instructions hidden from participants.
- Record the source revision and environment in a copy of
  `usability-pilot-results.template.json`. Keep account passwords outside Git.
- Give each person only their test credentials and the goal below. They may
  copy/paste credentials. Account creation/setup is outside the timed task;
  signing in and finding/completing the workflow are included.

### Goal shown to each participant

> Using the supplied test account, sign in to OrgFlow, tell the organization you
> are going to **[exact pilot event title]**, and confirm your response was saved.

Do not include navigation instructions such as “click Events” in the goal.
Replace the event-title placeholder consistently for all five participants.

### Observation and scoring

1. Start with the sign-in screen ready. Start a stopwatch when the participant
   receives the goal and begins interacting.
2. Do not guide navigation or point out controls. Record any assistance; a
   workflow completed with guidance cannot count as an unaided success.
3. Stop when the participant independently confirms the saved Going RSVP.
   Verify persisted RSVP state afterward. Record elapsed seconds, completion,
   assistance, confusion points and any app/technical failures without coaching.
4. Record each person's first attempt. Do not omit slow or failed attempts.
   A timeout or app failure is a failed attempt, not a reason to silently replace
   a participant. An unobserved/missing timing is incomplete evidence.
5. Success requires completed=true, assisted=false and elapsed_seconds <=180.
   At least four of five real observed participants must succeed. One person
   trying five times does not provide five participants.

After the timed attempt, ask what was confusing, whether they knew their RSVP
was saved, and what they expected to happen. Record their actual answers only.
If the UI changes and testing is repeated, label the new cohort/run and any
repeat participants; do not merge observations from different revisions into a
claimed single pilot.

### Scoring tool

Copy the JSON template, fill only actual observed results and run:

```text
python deploy/score_usability_pilot.py path/to/recorded-results.json
```

The blank template reports **INCOMPLETE**. Exit codes: 0 PASS, 1 FAIL, 2
INCOMPLETE. The tool checks record shape/thresholds; it cannot independently
establish that people participated. Its synthetic unit-test fixtures are not
pilot data. Never replace empty observations with fabricated measurements.

## What remains

- Five actual participant observations, timing and assistance records.
- User-reported confusion/findings and any needed fixes/retests.
- Human acceptance evidence linked to Jira before closure.

If recruitment remains impossible, retain this limitation in the final project
report and ask the course/project owner whether a documented alternative is
acceptable. Keep the current Jira criterion unsatisfied until it is met or
formally changed.
