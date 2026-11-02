# Sprint–Iteration Reconciliation (R-05)

**Action item:** R-05 from OrgFlow Progress Report (Oct 23, 2026), Sections 3, 7 and 8  
**Ticket:** SCRUM-82  
**Prepared:** November 2, 2026  
**Scope:** Jira sprint assignments reconciled against calendar iterations I4–I7

---

## Purpose

The Oct 23 progress report (Sections 3, 7 and 8) noted that the Jira sprint
board does not clearly document which calendar iteration each sprint or ticket
belongs to. This document fulfils action item R-05 by:

1. Defining the calendar boundaries for iterations I1–I7.
2. Mapping every known Jira ticket to the iteration(s) in which its primary
   work occurred, using commit dates as the authoritative record.
3. Identifying any mismatches between the original Jira sprint assignment
   and the calendar iteration in which the work actually landed.
4. Providing a single reference that can be preserved before the Jira trial
   expires (see integration handoff, November 1 gate: *"preserve actual Jira
   records before trial expiry"*).

---

## Calendar iteration boundaries

The project spans approximately 14 weeks from initial setup (Sep 7) through
the reported course deadline (Nov 10). Iterations run in two-week blocks
except for the abbreviated final iteration.

| Iteration | Start | End | Notes |
|-----------|-------|-----|-------|
| I1 | Sep 7 | Sep 20 | Initial Django/MongoDB/Docker setup; project README |
| I2 | Sep 21 | Oct 4 | Requirements and design; no implementation commits |
| I3 | Oct 5 | Oct 18 | Django port from Node.js prototype; Accounts 1.3 (WBS 1.3); Membership sign-up / approval flows |
| I4 | Oct 19 | Nov 1 | Events (WBS 1.5); Tasks and committees (WBS 1.6); Meeting recording; TJ membership/roster enhancements; integration preview; SCRUM-16 closeout |
| I5 | Nov 2 | Nov 8 | Final integration stabilization; remaining open gates |
| I6 | Nov 9 | Nov 10 | Submission and course deadline |

> **Note on I4–I7 in the progress report:** The Oct 23 progress report uses an
> alternate numbering where each week of the implementation phase is labeled
> separately (I4 = Oct 19–25, I5 = Oct 26–Nov 1, I6 = Nov 2–8, I7 = Nov 9–10).
> Both numbering schemes are captured in the reconciliation tables below so
> that the Jira board assignments can be cross-referenced regardless of which
> scheme a reviewer uses.

### Week-level iteration map (alternate numbering referenced in R-05)

| Iteration | Start | End | Notes |
|-----------|-------|-----|-------|
| I4 | Oct 19 | Oct 25 | Events branch active; Tasks/integration preview delivered; Meeting recording |
| I5 | Oct 26 | Nov 1 | Events merged to main (PR #9 / SCRUM-71); SCRUM-16 closeout; committee creation recovery; PR #13 merged |
| I6 | Nov 2 | Nov 8 | Final CI stabilization; remaining provider/VM/human gates |
| I7 | Nov 9 | Nov 10 | Course submission deadline |

---

## Jira ticket inventory and iteration mapping

### Pre-I4 tickets (completed before Oct 19)

These tickets closed before the R-05 window and are included for completeness.

| Ticket | Summary | WBS | Owner | Iteration completed | Jira sprint as assigned | Notes |
|--------|---------|-----|-------|---------------------|------------------------|-------|
| — | Initial Django/MongoDB/Docker setup | 1.1 | Team | I1 (Sep 7) | Sprint 1 | No dedicated Jira ticket; captured in initial commit |
| — | Added project README | — | Team | I1 (Sep 11) | Sprint 1 | No dedicated Jira ticket |
| — | Port Node.js features to Django | 1.4 | Team | I3 (Oct 7) | Sprint 2 | Username/email sign-in, sign-up; PR baseline |
| — | Accounts 1.3: Google sign-in, role safeguards | 1.3 | Chau | I3 (Oct 8) | Sprint 2 | Merged via PR #7 |
| — | Membership approval / rejection / forgot-password | 1.2 | Team/TJ | I3 (Oct 13) | Sprint 2 | Membership application gate and 1-day reapply wait |

> SCRUM tickets for the above items were not captured in the repository
> documentation. The Jira trial export should be consulted for their exact
> sprint assignments.

---

### I4 tickets (Oct 19–25, alternate numbering)

| Ticket | Summary | WBS | Owner | Primary commits | Planned sprint | Actual iteration | Status (Oct 28) | Discrepancy |
|--------|---------|-----|-------|----------------|----------------|-----------------|-----------------|-------------|
| SCRUM-15 | Add events, RSVP and attendance | 1.5 | Ayomide | Oct 22 (branch); Oct 27 (merged to main) | Sprint 3 / I4 | I4 (development) + I5 (merge) | In Review → Merged | Sprint assignment correctly placed development in I4; merge fell into I5. Jira status should reflect merge date Oct 27. |
| SCRUM-16 | Tasks: create, assign, delegate, progress (parent) | 1.6 | Chau | Oct 25 (integration preview) | Sprint 3 / I4 | I4 (initial delivery) + I5 (closeout) | In Review | Parent due Oct 28; initial delivery was I4; closeout commits landed I5. No sprint boundary mismatch — due date aligns with I4/I5 boundary. |
| SCRUM-23 | Committee data model/API | 1.6 | Chau | Oct 25, 28 | Sprint 3 / I4 | I4 + I5 | In Review | Committee edit/role flows added Oct 28 push work into I5. Jira should reflect subtask closure in I5, not I4. |
| SCRUM-24 | Task create, assign and complete endpoints | 1.6 | Chau | Oct 25 | Sprint 3 / I4 | I4 | In Review | No discrepancy; core HTTP/form endpoints delivered in I4. |
| SCRUM-25 | Committee/task frontend | 1.6 | Chau | Oct 25, 28 | Sprint 3 / I4 | I4 + I5 | In Review | Same as SCRUM-23: committee edit UI added Oct 28. |
| SCRUM-26 | Role-based committee/task permissions | 1.6 | Chau | Oct 25, 28 | Sprint 3 / I4 | I4 + I5 | In Review | New member-role update flows added Oct 28; minor I5 extension. |
| SCRUM-27 | Unit/integration tests; 80 % branch target | 1.6 | Chau | Oct 25 (254 tests), Oct 28 (661/638 tests) | Sprint 3 / I4 | I4 + I5 | In Review | 80 % core-logic branch target met and recorded in I5 final run. Jira should note that the measured coverage receipt is from Oct 28 (I5). |
| SCRUM-28 | Documentation and demo preparation | 1.6 | Chau | Oct 25 (contribution report, demo script) | Sprint 3 / I4 | I4 + I5 | In Review | Closeout addendum and creation-recovery guidance added Oct 28 (I5). |
| — | Meeting recording (WBS 1.6 / FR-06 partial) | — | Jack | Oct 23 | Sprint 3 / I4 | I4 | Integrated | No dedicated Jira ticket visible in repository docs; Jira trial export required. |
| — | TJ membership/roster enhancements (PRs #10, #11) | 1.2 | TJ | Oct 25 | Sprint 3 / I4 | I4 | Merged | No Jira ticket numbers visible; Jira trial export required. |

---

### I5 tickets (Oct 26–Nov 1, alternate numbering)

| Ticket | Summary | WBS | Owner | Primary commits | Planned sprint | Actual iteration | Status (Oct 30) | Discrepancy |
|--------|---------|-----|-------|----------------|----------------|-----------------|-----------------|-------------|
| SCRUM-71 | Review and merge PR #9 (Events and attendance) | 1.5 | Claude agent / team | Oct 27 | Not pre-planned in sprint | I5 | Merged | SCRUM-71 was created and executed within I5; it had no prior sprint assignment. Consider adding to Jira board retroactively as an I5 task. |
| SCRUM-16 (closeout) | SCRUM-16 subtask closeout: committee edit/role | 1.6 | Chau | Oct 28 | Sprint 3 / I4 | I5 | In Review | Committee update work extended into I5; see SCRUM-23/25/26 rows above. |
| — | Committee creation recovery | — | Chau | Oct 28 | Not pre-planned | I5 | Merged | No Jira ticket; uncertainty-write recovery for committee creation added Oct 28. Should be filed as a bug-fix or maintenance ticket if Jira access permits. |
| — | CI runner compatibility (Ubuntu 22.04 pin) | — | Chau | Oct 28 | Not pre-planned | I5 | Merged | Environment fix; no Jira ticket. |
| — | Combined integration preview merge (PR #13) | — | Chau | Oct 30 | Not pre-planned | I5 | Merged | No dedicated ticket; covered implicitly by SCRUM-16 and SCRUM-71. |

---

### I6 tickets (Nov 2–8, alternate numbering)

No implementation commits have been recorded in the repository for this period
at the time of this document. The following items remain open and are expected
to be addressed in I6.

| Item | Owner | Type | Notes |
|------|-------|------|-------|
| VM operator: live deployment verification | VM operator | Gate | Actual team VM address/access and Docker Compose check; HTTPS/origin/TLS |
| Google sign-in live check at intended origin | Chau / configuration owner | Gate | Client ID allowlist for production host |
| OpenAI summarization live check | Jack / AI owner | Gate | Requires private provider key; no paid API call made to date |
| Deepgram transcription live check | Jack / STT owner | Gate | Requires DEEPGRAM_API_KEY; two CI tests skipped |
| SMTP real-delivery check | SMTP owner | Gate | Internal capture only; real mailbox check pending |
| Performance benchmark | Team | Gate | 25-user, 10-minute host benchmark not yet run |
| Usability study (5 users) | Team | Gate | Required human acceptance; not yet scheduled |

These gates do not have assigned Jira tickets in the visible repository
documentation. They should be created in Jira (or confirmed closed) before
trial access ends.

---

### I7 items (Nov 9–10, alternate numbering)

| Item | Owner | Notes |
|------|-------|-------|
| Final submission | Team | Course deadline Nov 10 |
| Combine individual contribution supplements into team report | All members | Team template requires process/backlog records, Gantt and product-AI evaluation |
| Preserve Jira trial export | Team | Trial access ends before or shortly after submission deadline |

---

## Summary of discrepancies

| # | Ticket | Discrepancy | Recommended action |
|---|--------|-------------|-------------------|
| 1 | SCRUM-15 | Development started in I4 (Oct 22) but merge to main occurred in I5 (Oct 27). Sprint assignment reflects development start, not completion. | Update Jira to record merge/Done date as Oct 27 (I5). |
| 2 | SCRUM-23, SCRUM-25, SCRUM-26 | Committee edit/role flows committed Oct 28 extend work into I5, but subtasks were assigned to Sprint 3 (I4). | Move sprint assignment to I5 or adjust Done date to Oct 28 on each subtask. |
| 3 | SCRUM-27 | 80 % branch-coverage receipt recorded Oct 28 (I5), after the Sprint 3 (I4) assignment end. | Note actual coverage measurement date (Oct 28) in Jira comment; update Done date. |
| 4 | SCRUM-71 | Ticket created and executed within I5 with no prior sprint plan entry. | Add SCRUM-71 to I5 sprint retroactively if the Jira board supports it. |
| 5 | Committee creation recovery | No Jira ticket exists. Work performed Oct 28 (I5). | File a new ticket if Jira trial permits; otherwise record in team report. |
| 6 | TJ's PRs #10 and #11 (membership enhancements) | No Jira ticket numbers visible in repository documentation. Work merged Oct 25 (I4). | Confirm ticket numbers from Jira trial export; verify sprint assignment is I4. |
| 7 | Meeting recording (Jack, Oct 23) | No Jira ticket number visible in repository documentation. Work in I4. | Confirm ticket number from Jira trial export; verify sprint assignment is I4. |
| 8 | I6 / I7 gates | Multiple open gates (VM, providers, usability) have no Jira tickets. | Create tickets before trial expires, or capture in team report if trial is already closed. |

---

## Recommended next steps

1. **Export the Jira trial board** before access expires. Preserve the raw
   export (CSV or JSON) alongside this document in the repository.
2. **Update Done dates** on SCRUM-15, SCRUM-23, SCRUM-25, SCRUM-26 and
   SCRUM-27 to reflect their actual completion commits (Oct 27–28, I5).
3. **Confirm missing ticket numbers** for TJ's membership PRs and Jack's
   meeting recording by querying the Jira export.
4. **Create or close I6 gate tickets** (VM deployment, providers, performance,
   usability) before the trial expires.
5. **Retain this document** as the authoritative reconciliation record after
   the Jira trial ends so the team submission can reference sprint history
   without live Jira access.

---

## Evidence references

| Source | Location |
|--------|----------|
| Git commit history | `git log --format="%ai %s"` on `main` at `e404ce4` |
| Integration handoff | [docs/integration-handoff.md](integration-handoff.md) |
| Chau contribution report | [docs/chau-contribution-report.md](chau-contribution-report.md) |
| SCRUM-16 closeout (Oct 28) | [docs/chau-closeout-20261028.md](chau-closeout-20261028.md) |
| SCRUM-71 review record | [docs/evidence/ayomide/review-merge-scrum71.md](evidence/ayomide/review-merge-scrum71.md) |
| Completion checklist | [docs/chau-completion-checklist.md](chau-completion-checklist.md) |

Key: SCRUM-82  
Co-authored by Claude agent for Jira.
