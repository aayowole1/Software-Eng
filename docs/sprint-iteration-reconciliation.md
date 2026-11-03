# Sprint–Iteration Reconciliation (R-05)

**Action item:** R-05 from OrgFlow Progress Report (Oct 23, 2026), Sections 3, 7 and 8  
**Ticket:** SCRUM-82  
**Prepared:** November 2, 2026; updated November 3, 2026  
**Scope:** Jira sprint assignments reconciled against calendar iterations I4–I7

---

## Purpose

The Oct 23 progress report (Sections 3, 7 and 8) noted that the Jira sprint
board does not clearly document which calendar iteration each sprint or ticket
belongs to. This document fulfils action item R-05 by:

1. Defining a single agreed calendar for iterations I1–I7.
2. Mapping every known Jira ticket to the iteration(s) in which its primary
   work occurred, using commit dates as the authoritative record, with
   implementation, merge and acceptance dates recorded separately.
3. Identifying any mismatches between the original Jira sprint assignment
   and the calendar iteration in which the work actually landed.
4. Providing a single reference that can be preserved now that the Jira trial
   has ended and the board has moved to Jira Free (effective October 31).

---

## Calendar iteration boundaries

The project spans approximately 9 weeks from initial setup (Sep 7) through the
reported course deadline (Nov 10). Iterations I1–I3 are two-week blocks
covering setup and design; iterations I4–I7 are one-week blocks covering active
implementation, integration and submission.

| Iteration | Start | End | Primary focus |
|-----------|-------|-----|---------------|
| I1 | Sep 7 | Sep 20 | Initial Django/MongoDB/Docker setup (WBS 1.2); project README |
| I2 | Sep 21 | Oct 4 | Requirements and design; no implementation commits |
| I3 | Oct 5 | Oct 18 | Django port from Node.js prototype; Accounts 1.3 (WBS 1.3); Membership sign-up and approval flows (WBS 1.4) |
| I4 | Oct 19 | Oct 25 | Events dev (WBS 1.5); Tasks/committees initial delivery (WBS 1.6); Meeting recording dev (WBS 1.9); TJ membership/roster enhancements (WBS 1.4) |
| I5 | Oct 26 | Nov 1 | Events merge to main (SCRUM-71); SCRUM-16 subtask closeout commits; committee creation recovery; CI runner fix; PR #13 merge |
| I6 | Nov 2 | Nov 8 | Remaining open gates (VM, providers, performance, usability) |
| I7 | Nov 9 | Nov 10 | Course submission deadline |

---

## Jira ticket inventory and iteration mapping

Columns distinguish **implementation date** (last commit that completes
the feature work), **merge date** (date the branch landed on `main`), and
**acceptance date** (human or owner sign-off, where recorded). Status values
reflect the state captured in the Jira board as of October 28; the board has
since moved to Jira Free.

### Pre-I4 tickets (work completed before Oct 19)

| Ticket | Summary | WBS | Owner | Implementation | Merge | Acceptance | Jira sprint | Notes |
|--------|---------|-----|-------|---------------|-------|------------|-------------|-------|
| — | Initial Django/MongoDB/Docker setup | 1.2 | Team | Sep 7 | Sep 7 | — | Sprint 1 | No dedicated Jira ticket; captured in initial commit |
| — | Project README | — | Team | Sep 11 | Sep 11 | — | Sprint 1 | No dedicated Jira ticket |
| — | Port Node.js features to Django (sign-in, sign-up) | 1.3 / 1.4 | Team | Oct 7 | Oct 7 | — | Sprint 2 | Username/email sign-in, sign-up baseline |
| — | Accounts 1.3: Google sign-in, role safeguards | 1.3 | Chau | Oct 8 | Oct 8 (PR #7) | — | Sprint 2 | Merged via PR #7 |
| — | Membership approval / rejection / forgot-password | 1.4 | TJ / Team | Oct 13 | Oct 13 | — | Sprint 2 | Membership application gate and 1-day reapply wait |

> Jira ticket numbers for the above items are not visible in repository
> documentation. The Jira Free board or any retained export should be
> consulted for their exact sprint assignments.

---

### I4 tickets (Oct 19–25)

| Ticket | Summary | WBS | Owner | Implementation | Merge | Acceptance | Planned sprint | Actual iteration | Jira status (Oct 28) | Discrepancy |
|--------|---------|-----|-------|---------------|-------|------------|----------------|-----------------|----------------------|-------------|
| SCRUM-15 | Add events, RSVP and attendance | 1.5 | Ayomide | Oct 22 | Oct 27 (PR #9, I5) | Pending | Sprint 3 | I4 (impl) / I5 (merge) | In Review | Sprint assignment reflects implementation start (I4); merge to main occurred in I5 (Oct 27). Jira Done date should be Oct 27. |
| SCRUM-16 | Tasks: create, assign, delegate, progress (parent) | 1.6 | Chau | Oct 25 | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (impl) / I5 (merge) | In Review | Parent due Oct 28; initial delivery in I4; merge to main via PR #13 on Oct 30 (I5). Subtask closeout commits also extend into I5. |
| SCRUM-23 | Committee data model/API | 1.6 | Chau | Oct 28 (I5) | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (initial) / I5 (committee edit/role flows) | In Review | Committee name/description editing and member role-update flows were added Oct 28, which is in I5. Sprint 3 (I4) assignment does not reflect the Oct 28 completion. |
| SCRUM-24 | Task create, assign and complete endpoints | 1.6 | Chau | Oct 25 | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 | In Review | Core HTTP/form endpoints delivered in I4; no functional discrepancy on implementation date. |
| SCRUM-25 | Committee/task frontend | 1.6 | Chau | Oct 28 (I5) | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (initial) / I5 (committee edit UI) | In Review | Committee edit template added Oct 28 (I5); same boundary as SCRUM-23. |
| SCRUM-26 | Role-based committee/task permissions | 1.6 | Chau | Oct 28 (I5) | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (initial) / I5 (member-role update flows) | In Review | Member committee-role update permission checks added Oct 28 (I5). |
| SCRUM-27 | Unit/integration tests; 80 % branch target | 1.6 | Chau | Oct 28 (I5) | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (initial run) / I5 (final measured result) | In Review | Final measured coverage receipt is from Oct 28 (I5): combined preview run at `de676e2` yielded **659 passed, 2 Deepgram skips** and **94.78 % Committees/Tasks branch coverage** (218/230 branches, 835/871 statements). Sprint 3 (I4) assignment predates this measurement. |
| SCRUM-28 | Documentation and demo preparation | 1.6 | Chau | Oct 28 (I5) | Oct 30 (PR #13, I5) | Pending | Sprint 3 | I4 (contribution report, demo script) / I5 (closeout addendum, creation-recovery guidance) | In Review | Closeout addendum and creation-recovery guidance added Oct 28 (I5). |
| — | Meeting recording and transcription | 1.9 | Jack | Oct 23 | Oct 25 (integration preview) | Pending | Sprint 3 | I4 | Integrated | No dedicated Jira ticket visible in repository docs; confirm number from Jira Free board. |
| — | TJ membership/roster enhancements (PRs #10, #11) | 1.4 | TJ | Oct 25 | Oct 25 (I4) | — | Sprint 3 | I4 | Merged | No Jira ticket numbers visible in repository docs; confirm from Jira Free board. |

---

### I5 tickets (Oct 26–Nov 1)

| Ticket | Summary | WBS | Owner | Implementation | Merge | Acceptance | Planned sprint | Actual iteration | Jira status (Oct 30) | Discrepancy |
|--------|---------|-----|-------|---------------|-------|------------|----------------|-----------------|----------------------|-------------|
| SCRUM-71 | Review and merge PR #9 (Events and attendance) | 1.5 | Claude agent / team | Oct 27 | Oct 27 (I5) | — | Not pre-planned | I5 | Merged | SCRUM-71 was created and completed within I5 with no prior sprint entry. Add to I5 on the Jira Free board retroactively. |
| SCRUM-16 (closeout commits) | Committee edit/role flows; SCRUM-23/25/26 additions | 1.6 | Chau | Oct 28 | Oct 30 (PR #13) | Pending | Sprint 3 (I4) | I5 | In Review | Implementation extended into I5; see SCRUM-23/25/26 rows above. |
| — | Committee creation recovery (uncertain-write fix) | 1.6 | Chau | Oct 28 | Oct 30 (PR #13) | Pending | Not pre-planned | I5 | — | No Jira ticket. Should be filed as a bug-fix or maintenance ticket on the Jira Free board. |
| — | CI runner compatibility (Ubuntu 22.04 pin) | — | Chau | Oct 28 | Oct 28 | — | Not pre-planned | I5 | — | Environment fix; no Jira ticket required unless team policy mandates it. |
| — | Combined integration preview merge (PR #13) | — | Chau | Oct 30 | Oct 30 | — | Not pre-planned | I5 | — | No dedicated ticket; covered implicitly by SCRUM-16 and SCRUM-71. |

---

### I6 items (Nov 2–8)

No implementation commits have been recorded in the repository for this period
at the time of this document. The following open gates are expected to be
addressed in I6 and currently have no Jira tickets.

| Item | Owner | Type | Notes |
|------|-------|------|-------|
| VM operator: live deployment verification | VM operator | Gate | Actual team VM address/access and Docker Compose check; HTTPS/origin/TLS |
| Google sign-in live check at intended origin | Chau / configuration owner | Gate | Client ID allowlist for production host |
| OpenAI summarization live check | Jack / AI owner | Gate | Requires private provider key; no paid API call made to date |
| Deepgram transcription live check | Jack / STT owner | Gate | Requires DEEPGRAM_API_KEY; two CI tests currently skipped |
| SMTP real-delivery check | SMTP owner | Gate | Internal capture only; real mailbox check pending |
| Performance benchmark | Team | Gate | 25-user, 10-minute host benchmark not yet run |
| Usability study (5 users) | Team | Gate | Required human acceptance; not yet scheduled |

---

### I7 items (Nov 9–10)

| Item | Owner | Notes |
|------|-------|-------|
| Final submission | Team | Course deadline Nov 10 |
| Combine individual contribution supplements into team report | All members | Team template requires process/backlog records, Gantt and product-AI evaluation |

---

## Summary of discrepancies

| # | Ticket | Discrepancy | Recommended action |
|---|--------|-------------|-------------------|
| 1 | SCRUM-15 | Implementation in I4 (Oct 22); merge to main in I5 (Oct 27). Sprint assignment reflects implementation start only. | Record merge date Oct 27 as the completion date in Jira Free; update sprint to I5 or add merge milestone. |
| 2 | SCRUM-23, SCRUM-25, SCRUM-26 | Committee edit/role flows committed Oct 28 (I5); assigned to Sprint 3 (I4). | Adjust Done date to Oct 28 (I5) on each subtask in Jira Free. |
| 3 | SCRUM-27 | 80 % branch-coverage receipt measured Oct 28 (I5); sprint assigned to I4. Final result: 659 passed, 2 Deepgram skips, 94.78 % branch coverage. | Add Oct 28 measurement date as a Jira comment; update Done date to Oct 28. |
| 4 | SCRUM-16 (parent) | Six subtasks remain **In Review**; PR #13 merge (Oct 30) does not establish human acceptance. Implementation, merge and acceptance are separate events. | Do not mark Done until affected-owner review and human acceptance are recorded. |
| 5 | SCRUM-71 | Ticket created and completed in I5 with no prior sprint plan entry. | Add to I5 sprint on the Jira Free board retroactively. |
| 6 | Committee creation recovery | No Jira ticket; work committed Oct 28 (I5). | File a new bug-fix ticket on the Jira Free board. |
| 7 | TJ's PRs #10 and #11 (membership enhancements) | No Jira ticket numbers visible in repository docs; work merged Oct 25 (I4). | Confirm ticket numbers from the Jira Free board; verify sprint assignment is I4. |
| 8 | Meeting recording (Jack, WBS 1.9) | No Jira ticket number visible in repository docs; work in I4. | Confirm ticket number from the Jira Free board; verify sprint assignment is I4. |
| 9 | I6 / I7 gates | Multiple open gates (VM, providers, usability) have no Jira tickets. | Create tickets on the Jira Free board, or capture in team report if board is no longer maintained. |

---

## Recommended next steps

1. **Retain a Jira Free board export** (CSV or JSON) alongside this document
   in the repository so the team submission can reference sprint history
   without requiring board access.
2. **Update Done dates** on SCRUM-15, SCRUM-23, SCRUM-25, SCRUM-26 and
   SCRUM-27 to reflect actual completion commits (Oct 27–28, I5).
3. **Do not mark SCRUM-16 subtasks Done** until affected-owner reviews and
   human acceptance are recorded; In Review is the correct current status.
4. **Confirm missing ticket numbers** for TJ's membership PRs and Jack's
   meeting recording by querying the Jira Free board.
5. **Create or close I6 gate tickets** (VM deployment, providers, performance,
   usability) on the Jira Free board.

---

## Evidence references

| Source | Date / commit | Location |
|--------|--------------|----------|
| Git commit history | `main` at `e404ce4` | `git log --format="%ai %s"` |
| Committee creation recovery (test counts and coverage) | Oct 28, `de676e2` | [docs/chau-creation-recovery-20261028.md](chau-creation-recovery-20261028.md) |
| SCRUM-16 closeout | Oct 28 | [docs/chau-closeout-20261028.md](chau-closeout-20261028.md) |
| Integration handoff | Oct 25 | [docs/integration-handoff.md](integration-handoff.md) |
| Chau contribution report | Oct 25–28 | [docs/chau-contribution-report.md](chau-contribution-report.md) |
| SCRUM-71 review record | Oct 27 | [docs/evidence/ayomide/review-merge-scrum71.md](evidence/ayomide/review-merge-scrum71.md) |
| Completion checklist | Oct 25–28 | [docs/chau-completion-checklist.md](chau-completion-checklist.md) |

Key: SCRUM-82  
Co-authored by Claude agent for Jira.
