"""Seed a small demo organization for showing the dashboard and reports (SCRUM-40).

    python manage.py seed_reports_demo            # empty database only
    python manage.py seed_reports_demo --force    # add the demo to a database that has users
    python manage.py seed_reports_demo --show-expected

All dates are relative to today, so the demo works on any day. Demo accounts
get random passwords that are printed once to the console and never saved.
The numbers the audience should see are kept in DEMO_EXPECTED below; the demo
script (docs/reports-dashboard-demo.md) and core/test_reports_demo.py both use
them, so the three stay in agreement.
"""

import os
import secrets
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.lifecycle import apply_suspension
from accounts.models import Profile, Role, set_role
from committees.models import Committee, CommitteeMember, CommitteeRole
from events.models import (
    RSVP, Attendance, AttendanceAction, AttendanceAuditLog, AttendanceAuditStatus, Event, RSVPResponse,
)
from meetings.models import DraftStatus, MeetingDraft
from membership.models import MembershipApplication
from tasks.models import TaskPriority, TaskStatus
from tasks.services import create_task


EMAIL_DOMAIN = "example.com"

# username: (first name, last name, kind). Kinds: admin, officer, member,
# newcomer (approved 5 days ago), suspended, applicant (pending application).
PEOPLE = {
    "demo_admin": ("Morgan", "Reyes", "admin"),
    "demo_officer": ("Priya", "Shah", "officer"),
    "demo_chair": ("Jordan", "Lee", "member"),
    "demo_member": ("Sam", "Carter", "member"),
    "demo_member2": ("Taylor", "Brooks", "member"),
    "demo_member3": ("Casey", "Nguyen", "member"),
    "demo_newcomer": ("Riley", "Patel", "newcomer"),
    "demo_suspended": ("Drew", "Kim", "suspended"),
    "demo_applicant": ("Alex", "Rivera", "applicant"),
}
MEMBER_APPROVED_DAYS_AGO = 40
NEWCOMER_APPROVED_DAYS_AGO = 5
ADMIN_JOINED_DAYS_AGO = 60

COMMITTEES = {
    "Outreach": {
        "description": "Plans volunteer days and community events.",
        "chair": "demo_chair",
        "members": ["demo_member", "demo_member2", "demo_newcomer"],
    },
    "Finance": {
        "description": "Tracks the budget, receipts and reimbursements.",
        "chair": "demo_member3",
        "members": ["demo_officer", "demo_suspended"],
    },
}

EVENT_HOUR = 18  # every demo event starts at 6:00 PM local time
# key: (title, location, days from today, cancelled, RSVPs going, attended)
EVENTS = {
    "social": (
        "Welcome Back Social", "Student Union Ballroom", -25, False,
        ["demo_admin", "demo_officer", "demo_chair", "demo_member", "demo_member2", "demo_member3", "demo_suspended"],
        ["demo_admin", "demo_officer", "demo_chair", "demo_member", "demo_member3", "demo_suspended"],
    ),
    "training": (
        "Volunteer Training", "Room 204", -18, False,
        ["demo_admin", "demo_officer", "demo_chair", "demo_member2"],
        ["demo_admin", "demo_officer", "demo_chair", "demo_member2", "demo_suspended"],
    ),
    "study": (
        "Study Night", "Library Commons", -11, False,
        ["demo_admin", "demo_chair", "demo_member", "demo_member2", "demo_member3"],
        ["demo_admin", "demo_chair", "demo_member", "demo_member2"],
    ),
    "bowling": (
        "Bowling Night", "Campus Lanes", -7, True,
        ["demo_member", "demo_member2"],
        [],
    ),
    "speaker": (
        "Guest Speaker: Careers in Nonprofits", "Auditorium B", -4, False,
        ["demo_admin", "demo_officer", "demo_chair", "demo_member", "demo_member2", "demo_newcomer"],
        ["demo_admin", "demo_officer", "demo_chair", "demo_member2", "demo_newcomer"],
    ),
    "fundraiser": (
        "Fundraiser Planning Meeting", "Room 204", 3, False,
        ["demo_officer", "demo_member3"],
        [],
    ),
    "cleanup": (
        "Community Park Cleanup", "Riverside Park", 10, False,
        ["demo_chair", "demo_member", "demo_member2", "demo_newcomer"],
        [],
    ),
}
# "Not going" answers are stored but never counted as RSVPs going.
NOT_GOING = {"study": ["demo_officer"]}

# (title, committee or None, assignee or None, status, due in days or None, priority, created by)
TASKS = [
    ("Design the cleanup flyer", "Outreach", "demo_member", TaskStatus.DONE, -6, TaskPriority.MEDIUM, "demo_chair"),
    ("Book the park pavilion", "Outreach", "demo_member", TaskStatus.TODO, 5, TaskPriority.HIGH, "demo_chair"),
    ("Collect volunteer waivers", "Outreach", "demo_member", TaskStatus.IN_PROGRESS, -2, TaskPriority.HIGH, "demo_chair"),
    ("Post the cleanup on social media", "Outreach", "demo_member2", TaskStatus.DONE, -1, TaskPriority.LOW, "demo_chair"),
    ("Recruit ten volunteers", "Outreach", "demo_chair", TaskStatus.IN_PROGRESS, 9, TaskPriority.MEDIUM, "demo_officer"),
    ("Order trash bags and gloves", "Outreach", None, TaskStatus.TODO, 8, TaskPriority.MEDIUM, "demo_chair"),
    ("Reconcile September receipts", "Finance", "demo_member3", TaskStatus.TODO, -3, TaskPriority.URGENT, "demo_officer"),
    ("Draft the spring budget", "Finance", "demo_officer", TaskStatus.UNDER_REVIEW, 7, TaskPriority.HIGH, "demo_officer"),
    ("Submit the reimbursement form", "Finance", "demo_member3", TaskStatus.DONE, -5, TaskPriority.LOW, "demo_officer"),
    ("Update the member handbook", None, "demo_admin", TaskStatus.IN_PROGRESS, 14, TaskPriority.MEDIUM, "demo_officer"),
    ("Renew the room reservation", None, "demo_officer", TaskStatus.TODO, -1, TaskPriority.HIGH, "demo_admin"),
    ("Prepare the new-member welcome packet", None, "demo_newcomer", TaskStatus.TODO, 6, TaskPriority.MEDIUM, "demo_officer"),
]

DRAFT_TITLE = "Officer meeting - fundraiser planning"

# What the audience should see right after seeding an empty database, using
# the report's default range (the last 30 days). Written out by hand rather
# than computed, so the test checks the app against these numbers.
DEMO_EXPECTED = {
    "dashboard": {
        "active_members": 7,
        "upcoming_events": 2,
        "open_tasks": 9,
        "pending_approvals": 2,
        "pending_applications": 1,
        "pending_drafts": 1,
    },
    # Member dashboard and My account, signed in as each username.
    "member_views": {
        "demo_member": {
            "tasks_assigned": 3, "tasks_completed": 1, "tasks_overdue": 1,
            "open_tasks": ["Collect volunteer waivers", "Book the park pavilion"],
            "attended": 2, "events": 4, "rate": 50,
        },
        "demo_newcomer": {
            "tasks_assigned": 1, "tasks_completed": 0, "tasks_overdue": 0,
            "open_tasks": ["Prepare the new-member welcome packet"],
            "attended": 1, "events": 1, "rate": 100,
        },
    },
    "report": {
        "events_held": 4,
        # (event, RSVPs going, attended), oldest first
        "events": [
            ("Welcome Back Social", 7, 6),
            ("Volunteer Training", 4, 5),
            ("Study Night", 5, 4),
            ("Guest Speaker: Careers in Nonprofits", 6, 5),
        ],
        # (member, attended, events held, attendance %, tasks assigned, completed, overdue)
        "members": [
            ("Morgan Reyes", 4, 4, 100.0, 1, 0, 0),
            ("Jordan Lee", 4, 4, 100.0, 1, 0, 0),
            ("Sam Carter", 2, 4, 50.0, 3, 1, 1),
            ("Taylor Brooks", 3, 4, 75.0, 1, 1, 0),
            ("Casey Nguyen", 1, 4, 25.0, 2, 1, 1),
            ("Riley Patel", 1, 1, 100.0, 1, 0, 0),
            ("Priya Shah", 3, 4, 75.0, 2, 0, 1),
            ("Drew Kim", 2, 4, 50.0, 0, 0, 0),
        ],
        # (committee, members, attendance %, tasks total, completed, overdue)
        "committees": [
            ("Finance", 3, 50.0, 3, 1, 1),
            ("Outreach", 4, 76.9, 6, 2, 1),
        ],
    },
}


def expected_numbers_markdown():
    """The expected-numbers tables, exactly as they appear in the demo script."""
    d = DEMO_EXPECTED["dashboard"]
    r = DEMO_EXPECTED["report"]
    lines = [
        "| Dashboard card | Number |",
        "|---|---|",
        f"| Active members | {d['active_members']} |",
        f"| Upcoming events | {d['upcoming_events']} |",
        f"| Open tasks | {d['open_tasks']} |",
        f"| Pending approvals | {d['pending_approvals']} "
        f"({d['pending_applications']} application + {d['pending_drafts']} draft) |",
        "",
        f"Events held (non-cancelled): **{r['events_held']}**",
        "",
        "| Event | RSVPs (Going) | Attended |",
        "|---|---|---|",
        *(f"| {title} | {going} | {attended} |" for title, going, attended in r["events"]),
        "",
        "| Member | Events attended | Events held | Attendance % | Tasks assigned | Tasks completed | Tasks overdue |",
        "|---|---|---|---|---|---|---|",
        *(
            f"| {name} | {att} | {held} | {pct}% | {assigned} | {done} | {overdue} |"
            for name, att, held, pct, assigned, done, overdue in r["members"]
        ),
        "",
        "| Committee | Members | Attendance % | Tasks (total) | Tasks completed | Tasks overdue |",
        "|---|---|---|---|---|---|",
        *(
            f"| {name} | {members} | {pct}% | {total} | {done} | {overdue} |"
            for name, members, pct, total, done, overdue in r["committees"]
        ),
    ]
    return "\n".join(lines) + "\n"


def demo_email(username):
    return f"{username.replace('_', '.')}@{EMAIL_DOMAIN}"


class Command(BaseCommand):
    help = (
        "Create a small demo organization (accounts, committees, events, tasks) for "
        "showing the dashboard and participation reports. Refuses to run when user "
        "accounts already exist unless --force is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Add the demo even though other user accounts already exist.",
        )
        parser.add_argument(
            "--show-expected", action="store_true",
            help="Print the numbers the demo should show (Markdown) and exit without changing anything.",
        )

    def handle(self, *args, **options):
        if options["show_expected"]:
            self.stdout.write(expected_numbers_markdown(), ending="")
            return
        self._check_safe_to_run(options["force"])

        self.now = timezone.now()
        self.today = timezone.localdate()
        self.passwords = {}
        users = self._create_people()
        committees = self._create_committees(users)
        self._create_events(users)
        self._create_tasks(users, committees)
        MeetingDraft.objects.create(
            title=DRAFT_TITLE,
            notes=(
                "Agreed to hold a bake sale before the park cleanup. Priya will price supplies; "
                "Casey will check the budget."
            ),
            summary="The officers discussed fundraiser options and chose a bake sale.",
            status=DraftStatus.PENDING_REVIEW,
            created_by=users["demo_officer"],
        )
        self._print_logins(users)

    # -- safety ----------------------------------------------------------

    def _check_safe_to_run(self, force):
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if settings_module.endswith("settings_production"):
            raise CommandError(
                "seed_reports_demo only runs with development settings. "
                "It never runs with orgflow_project.settings_production."
            )
        User = get_user_model()
        existing = User.objects.count()
        if existing and not force:
            raise CommandError(
                f"This database already has {existing} user account(s), so no demo data was added. "
                "The demo is meant for an empty database (the numbers in "
                "docs/reports-dashboard-demo.md assume one). Run with --force to add it anyway."
            )
        taken = sorted(User.objects.filter(username__in=list(PEOPLE)).values_list("username", flat=True))
        if taken:
            raise CommandError(
                "The demo has already been added to this database (found "
                f"{', '.join(taken)}). Nothing was changed."
            )
        clashes = sorted(Committee.objects.filter(name__in=list(COMMITTEES)).values_list("name", flat=True))
        if clashes:
            raise CommandError(
                f"Committee(s) {', '.join(clashes)} already exist. Nothing was changed."
            )

    # -- people ------------------------------------------------------------

    def _new_user(self, username, *, active, joined_at):
        first, last, _ = PEOPLE[username]
        password = secrets.token_urlsafe(12)
        self.passwords[username] = password
        user = get_user_model().objects.create_user(
            username=username, email=demo_email(username), password=password,
            first_name=first, last_name=last, is_active=active,
        )
        get_user_model().objects.filter(pk=user.pk).update(date_joined=joined_at)
        user.refresh_from_db()
        return user

    def _approve(self, user, reviewer, approved_at):
        """Approve a membership application, then date it `approved_at` (like a real past review)."""
        submitted_at = approved_at - timedelta(days=2)
        application = MembershipApplication.objects.create(
            user=user, statement="I'd like to help with events and volunteering.",
        )
        application.review(reviewer, approve=True)
        application.refresh_from_db()
        history = list(application.history or [])
        for entry, moment in zip(history, (submitted_at, approved_at)):
            entry["at"] = moment.isoformat()
        MembershipApplication.objects.filter(pk=application.pk).update(
            submitted_at=submitted_at, reviewed_at=approved_at, history=history,
        )
        profile = Profile.objects.get(user=user)
        role_history = list(profile.role_history or [])
        for entry in role_history:
            if str(entry.get("source", "")).startswith("membership_review:"):
                entry["at"] = approved_at.isoformat()
        Profile.objects.filter(pk=profile.pk).update(role_history=role_history)

    def _create_people(self):
        users = {}
        admin_joined = self.now - timedelta(days=ADMIN_JOINED_DAYS_AGO)
        admin = self._new_user("demo_admin", active=True, joined_at=admin_joined)
        set_role(admin, Role.ADMIN)
        users["demo_admin"] = admin

        for username, (_, _, kind) in PEOPLE.items():
            if kind == "admin":
                continue
            if kind == "applicant":
                user = self._new_user(username, active=False, joined_at=self.now - timedelta(days=1))
                application = MembershipApplication.objects.create(
                    user=user, statement="I'm a first-year student and want to volunteer.",
                )
                MembershipApplication.objects.filter(pk=application.pk).update(
                    submitted_at=self.now - timedelta(days=1),
                )
                users[username] = user
                continue
            days = NEWCOMER_APPROVED_DAYS_AGO if kind == "newcomer" else MEMBER_APPROVED_DAYS_AGO
            approved_at = self.now - timedelta(days=days)
            user = self._new_user(username, active=False, joined_at=approved_at - timedelta(days=2))
            self._approve(user, admin, approved_at)
            if kind == "officer":
                set_role(user, Role.OFFICER, actor=admin, source="account_role_management")
            if kind == "suspended":
                apply_suspension(user, True)
            user.refresh_from_db()
            users[username] = user
        return users

    def _create_committees(self, users):
        committees = {}
        for name, spec in COMMITTEES.items():
            committee = Committee.objects.create(
                name=name, description=spec["description"], created_by=users["demo_admin"],
            )
            CommitteeMember.objects.create(committee=committee, user=users[spec["chair"]], role=CommitteeRole.CHAIR)
            for username in spec["members"]:
                CommitteeMember.objects.create(committee=committee, user=users[username], role=CommitteeRole.MEMBER)
            committees[name] = committee
        return committees

    # -- events --------------------------------------------------------------

    def _local(self, days, hour=EVENT_HOUR):
        tz = timezone.get_current_timezone()
        return timezone.make_aware(
            datetime.combine(self.today + timedelta(days=days), time(hour=hour)), tz,
        )

    def _create_events(self, users):
        officer = users["demo_officer"]
        for key, (title, location, days, cancelled, going, attended) in EVENTS.items():
            starts_at = self._local(days)
            event = Event.objects.create(
                title=title, location=location, starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=2), cancelled=cancelled,
                description=f"{title} for the demo organization.", created_by=officer,
            )
            for username in going:
                RSVP.objects.create(event=event, user=users[username], response=RSVPResponse.GOING)
            for username in NOT_GOING.get(key, []):
                RSVP.objects.create(event=event, user=users[username], response=RSVPResponse.NOT_GOING)
            marked_at = starts_at + timedelta(hours=2)
            for username in attended:
                record = Attendance.objects.create(event=event, user=users[username], marked_by=officer)
                Attendance.objects.filter(pk=record.pk).update(marked_at=marked_at)
                AttendanceAuditLog.objects.create(
                    change_key=f"mark:{record.pk}", event=event, user=users[username],
                    action=AttendanceAction.MARKED, actor=officer, at=marked_at,
                    status=AttendanceAuditStatus.COMPLETED,
                )

    # -- tasks -----------------------------------------------------------------

    def _create_tasks(self, users, committees):
        for title, committee, assignee, status, due_in, priority, creator in TASKS:
            create_task(
                users[creator],
                title=title,
                committee=committees[committee] if committee else None,
                assignee=users[assignee] if assignee else None,
                status=status,
                due_date=self.today + timedelta(days=due_in) if due_in is not None else None,
                priority=priority,
            )

    # -- output ----------------------------------------------------------------

    def _print_logins(self, users):
        notes = {
            "demo_admin": "Admin",
            "demo_officer": "Officer",
            "demo_chair": "Member, Outreach Chair",
            "demo_member": "Member (use for the member dashboard)",
            "demo_member2": "Member",
            "demo_member3": "Member, Finance Chair",
            "demo_newcomer": f"Member approved {NEWCOMER_APPROVED_DAYS_AGO} days ago",
            "demo_suspended": "Suspended member (cannot sign in)",
            "demo_applicant": "Pending application (cannot sign in until approved)",
        }
        self.stdout.write(self.style.SUCCESS(
            f"Demo organization created: {len(users)} accounts, {len(COMMITTEES)} committees, "
            f"{len(EVENTS)} events, {len(TASKS)} tasks and 1 meeting draft."
        ))
        self.stdout.write("")
        self.stdout.write("Demo sign-ins (shown once; passwords are not saved anywhere):")
        width = max(len(name) for name in users)
        for username in PEOPLE:
            self.stdout.write(
                f"  {username.ljust(width)}  {self.passwords[username]}  {notes[username]}"
            )
        self.stdout.write("")
        self.stdout.write(
            "Sign in with the username (or its email, e.g. "
            f"{demo_email('demo_officer')}). Follow docs/reports-dashboard-demo.md."
        )
