# Reports and dashboard demo (SCRUM-40)

A 5–7 minute click-through of the operations dashboard and the participation
report, using a small made-up organization. Every number below is what the
audience should see right after seeding. The same numbers are checked by
`core/test_reports_demo.py`, so if the code changes the test fails before this
script goes out of date.

## Before the demo (about 2 minutes, do it beforehand)

The demo needs a database **with no other user accounts**, because the numbers
assume only the demo organization exists. Pick one of these:

**A. A fresh setup** (a new clone, or a machine that has never run OrgFlow):

```bash
docker compose up -d --build
```

```bash
docker compose exec web python manage.py migrate
```

```bash
docker compose exec web python manage.py seed_reports_demo
```

Open <http://localhost:8000>.

**B. Keep your existing data** and run the demo from a separate database on
port 8001 (your normal site on port 8000 is not changed):

```bash
docker compose run --rm -e MONGODB_NAME=orgflow_demo -p 8001:8000 web sh -c "python manage.py migrate && python manage.py seed_reports_demo && python manage.py runserver 0.0.0.0:8000"
```

Open <http://localhost:8001>. Stop it with Ctrl+C when the demo is over.

`seed_reports_demo` prints one line per demo account with a random password.
**The passwords are shown only once and are not saved anywhere**, so copy
them somewhere private for the demo. You can sign in with the username or its
email (for example `demo.officer@example.com`).

| Username | Who | Used for |
|---|---|---|
| `demo_admin` | Morgan Reyes, Admin | (optional) admin view |
| `demo_officer` | Priya Shah, Officer | dashboard cards, Reports |
| `demo_chair` | Jordan Lee, Outreach Chair | |
| `demo_member` | Sam Carter, Member | member dashboard, My account |
| `demo_member2` | Taylor Brooks, Member | |
| `demo_member3` | Casey Nguyen, Finance Chair | |
| `demo_newcomer` | Riley Patel, approved 5 days ago | membership start |
| `demo_suspended` | Drew Kim, suspended | cannot sign in |
| `demo_applicant` | Alex Rivera, pending application | cannot sign in |

Safety: the command refuses to run if any user accounts already exist (add
`--force` to add the demo anyway; the numbers below will then be different),
never runs twice into the same database, and refuses to run with the
production settings.

Seed on the day of the demo. All dates are relative to the day you seed
(events 25, 18, 11 and 4 days ago, a cancelled event 7 days ago, and upcoming
events in 3 and 10 days), and the numbers stay correct for two days after
seeding.

## Expected numbers

Report range: the default (the last 30 days, ending today).

| Dashboard card | Number |
|---|---|
| Active members | 7 |
| Upcoming events | 2 |
| Open tasks | 9 |
| Pending approvals | 2 (1 application + 1 draft) |

Events held (non-cancelled): **4**

| Event | RSVPs (Going) | Attended |
|---|---|---|
| Welcome Back Social | 7 | 6 |
| Volunteer Training | 4 | 5 |
| Study Night | 5 | 4 |
| Guest Speaker: Careers in Nonprofits | 6 | 5 |

| Member | Events attended | Events held | Attendance % | Tasks assigned | Tasks completed | Tasks overdue |
|---|---|---|---|---|---|---|
| Morgan Reyes | 4 | 4 | 100.0% | 1 | 0 | 0 |
| Jordan Lee | 4 | 4 | 100.0% | 1 | 0 | 0 |
| Sam Carter | 2 | 4 | 50.0% | 3 | 1 | 1 |
| Taylor Brooks | 3 | 4 | 75.0% | 1 | 1 | 0 |
| Casey Nguyen | 1 | 4 | 25.0% | 2 | 1 | 1 |
| Riley Patel | 1 | 1 | 100.0% | 1 | 0 | 0 |
| Priya Shah | 3 | 4 | 75.0% | 2 | 0 | 1 |
| Drew Kim | 2 | 4 | 50.0% | 0 | 0 | 0 |

| Committee | Members | Attendance % | Tasks (total) | Tasks completed | Tasks overdue |
|---|---|---|---|---|---|
| Finance | 3 | 50.0% | 3 | 1 | 1 |
| Outreach | 4 | 76.9% | 6 | 2 | 1 |

(`python manage.py seed_reports_demo --show-expected` prints these tables
without changing anything.)

## The click-through

### 1. Officer dashboard (about 1 minute)

Sign in as **`demo_officer`**. You land on the **Dashboard**.

Say: "Officers and admins get four summary cards at the top."

* **Active members: 7.** Members, officers and admins whose accounts work
  right now. Drew (suspended) and Alex (still applying) are not counted. The
  card links to the **Roster**.
* **Upcoming events: 2.** The fundraiser planning meeting and the park
  cleanup. Cancelled and past events don't count. Links to **Events**.
* **Open tasks: 9.** Every task that isn't Done: 4 in Outreach, 2 in Finance
  and 3 organization-wide. Links to **Tasks**.
* **Pending approvals: 2**, split into **applications** (Alex's membership
  application) and **drafts** (the "Officer meeting - fundraiser planning"
  meeting draft waiting for review).

Point at **Needs your attention** below the cards: "1 membership application
pending" and "1 meeting draft pending review". Each line opens the list to
act on.

### 2. Member dashboard (about 1 minute)

Sign out and sign in as **`demo_member`** (Sam Carter). There are no summary
cards; members see their own work instead.

* **My tasks:** "3 assigned · 1 completed · 1 overdue". The list shows Sam's
  two unfinished tasks, soonest due first: **Collect volunteer waivers**
  (In progress, marked **Overdue**) and **Book the park pavilion** (To do).
  The finished flyer task is counted but not listed.
* **Upcoming events:** the two upcoming events.
* **My attendance:** "Attended 2 of 4 events (50%)". Click it.

### 3. My account attendance history (about 30 seconds)

The link opens **My account** at **My attendance**: "Counting events since
your membership started on …" (40 days before the seed date), "Attended 2 of
4 events (50%)", then each event newest first: Guest Speaker *Not recorded*,
Study Night *Attended*, Volunteer Training *Not recorded*, Welcome Back
Social *Attended*. The cancelled Bowling Night is not listed.

### 4. Reports, default range (about 2 minutes)

Sign out and sign in as **`demo_officer`** again. In the sidebar under
**Officer Tools**, click **Reports**. The page is **Participation &
Engagement Report**, with **Start date** and **End date** already set to the
last 30 days. Nothing needs to be clicked; the report for that range is shown.

* **Events:** "Events held (non-cancelled): **4**". Read one row: Welcome
  Back Social had 7 RSVPs (Going) and 6 attended. Volunteer Training shows
  5 attended but only 4 RSVPs: Drew came without RSVPing, and attendance is
  recorded separately from RSVPs. Bowling Night was cancelled, so it isn't
  listed, and upcoming events aren't counted yet.
* **Per-member report:** Sam Carter 2 of 4, 50.0%, with 3 tasks assigned,
  1 completed, 1 overdue. Drew Kim is still listed (Drew is on the roster,
  just suspended) but is not in the Active members card.
* **Per-committee report:** Outreach has 4 members and **76.9%** attendance
  (10 attendances out of 13 possible), Finance has 3 members and **50.0%**.
* Scroll to **How numbers are calculated** and read the first and third
  bullets: attendance % only counts events since each member's membership
  started, which is when their application was last approved.

### 5. The newcomer (about 30 seconds)

In **Per-member report**, point at **Riley Patel: 1 attended, 1 event held,
100.0%**. Riley was approved 5 days ago, so only the Guest Speaker event
(4 days ago) counts. Without this rule Riley would show 1 of 4 (25%) for
events held before they joined. The same rule is used on Riley's own
My account page, so the numbers always agree. (Optional: sign in as
`demo_newcomer` and show "Attended 1 of 1 event (100%)".)

### 6. Charts (about 30 seconds)

Scroll up to **Charts**:

* **Attendance by event:** RSVPs Going vs Attended bars for the four events.
* **Attendance by committee:** Finance 50, Outreach 76.9.
* **Tasks by committee:** Finance 1 completed, 1 open, 1 overdue; Outreach 2
  completed, 3 open, 1 overdue.

The tables stay on the page even if the charts can't load.

### 7. CSV download (about 1 minute)

Under **Download CSV**, the **Report** dropdown is set to **All reports
(ZIP)**. Click **Download**: you get
`orgflow-report-all-{start}_{end}.zip` containing the Events, Members and
Committees CSVs for the same range. Open the Members CSV: 8 rows, sorted by
name, with a **Status** column (Drew Kim is `suspended`, everyone else is
`active`).

Then choose **Committees** in the dropdown and click **Download** again to get
one CSV: `orgflow-report-committees-{start}_{end}.csv`, with the Outreach row
`Outreach,4,76.9,6,2,1`.

Wrap up: "Officers see the state of the organization at a glance on the
dashboard, and the report explains the numbers and exports them."

## Questions you may be asked

**Why does Volunteer Training show more attended than RSVPs?**
RSVPs and attendance are separate. People can come without RSVPing (Drew) or
RSVP and not come.

**Why is Drew in the report but not in Active members?**
The report lists everyone on the roster (members, officers and admins) so
past participation isn't lost. Active members only counts accounts that can
be used right now, the same rule used for assigning tasks; the Members CSV
shows Drew's Status as `suspended`.

**Why does Riley have 100% after one event?**
Attendance % only counts events held since the member's membership started.
Riley joined 5 days ago and attended the one event since then.

**How is committee attendance calculated?**
All attendances by the committee's members divided by the events each member
could attend since joining. Outreach: Jordan 4 of 4, Sam 2 of 4, Taylor 3 of
4, Riley 1 of 1, so 10 of 13 = 76.9%.

**Which tasks count in the report?**
Tasks created in the selected range. All demo tasks were created on the seed
day, so all 12 count. "Overdue" means a past due date and not Done, as of
today. The dashboard's Open tasks card counts every unfinished task,
whatever its date.

**Does Pending approvals include officer applications?**
The demo creates none, so the card shows 2 either way.

**What time zone are dates in?**
The organization's time zone (`TIME_ZONE`, America/Chicago by default). The
start and end days are included in full.

**Can I change the range?**
Yes. Change **Start date** or **End date** and click **Generate report**.
Downloads always use the range shown. An end date before the start date is
rejected.

**Is the demo data real? Where are the passwords?**
Everything is made up and uses `example.com` emails. Passwords are random,
printed once by the command, and stored only as normal password hashes.
