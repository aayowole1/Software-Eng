"""User and admin guides for the in-app Help page and docs/ (SCRUM-50).

This module is the single source for both. The Help page shows each person the
sections for their role; `manage.py export_help_docs` writes the same content to
docs/user-and-admin-guide.md, and a test fails if that file is out of date.

`coming_soon` marks a whole guide for a feature that hasn't merged yet. A note
can instead name a feature check in FEATURE_CHECKS: the Help page then shows the
finished text once the feature is in the running code and a Coming soon version
until then. docs/ always shows the finished text, since it is for the final
package.
"""

from accounts.models import Role

AUDIENCES = [
    (Role.MEMBER, "Member guides", "For everyone with an account."),
    (Role.OFFICER, "Officer guides", "Shown to Officers and Admins."),
    (Role.ADMIN, "Admin guides", "Shown to Admins only."),
]

GUIDES = [
    # --- Members (everyone signed in) -------------------------------------
    {
        "audience": Role.MEMBER,
        "slug": "sign-up",
        "title": "Sign up and apply to join",
        "steps": [
            "On the Sign in page, choose **Create an account and apply to join** (or **Get Started**). You can also sign in with Google.",
            "Fill in your details and your application statement, then submit.",
            "Until an officer approves you, you are an Applicant. On your dashboard, choose **View or submit an application** to see **My applications** and their status.",
            "If an application is rejected, the reason is shown there. You can apply again after 1 day.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "rsvp",
        "title": "RSVP to an event",
        "steps": [
            "Open **Events** and choose an upcoming event.",
            "Under **Your RSVP**, choose **Going** or **Not going**.",
            "You can change your answer until the event starts. Cancelled events don't take RSVPs.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "attendance",
        "title": "View your attendance",
        "steps": [
            "Open **My account** and scroll to **My attendance**.",
            "You'll see each past event since your membership started, whether your attendance was recorded, and your attendance rate.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "tasks",
        "title": "Claim and update tasks",
        "steps": [
            "Open **Tasks**. Use **Filter tasks** to narrow by committee, status, priority or due date.",
            "To take an unassigned task in one of your committees, open it and choose **Assign to me**.",
            "To report progress on your task, open it, choose **Update progress**, pick a status (To Do, In Progress, Under Review or Done) and choose **Save status**.",
            "The **Task history** on each task shows every change.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "announcements",
        "title": "Read announcements",
        "steps": [
            "Open **Announcements**. Search by keyword, or filter by category or tag (click a tag on any post to filter by it).",
            "Open a post to read it, then choose **Mark as read**.",
            "If comments are enabled, add yours and choose **Post comment**.",
            "Committee announcements are only shown to that committee's members.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "resources",
        "title": "Download resources",
        "steps": [
            "Open **Resources**. Search, or filter by category or tag.",
            "Choose **Download document** for a file or **Open link** for an external link.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "profile",
        "title": "Edit your profile",
        "steps": [
            "Open **My account** and choose **Edit profile**.",
            "Update your first and last name, contact email and graduation year, then choose **Save profile**.",
            "If you sign in with Google, your email is managed by Google and can't be changed here.",
        ],
    },
    {
        "audience": Role.MEMBER,
        "slug": "password",
        "title": "Reset your password",
        "steps": [
            "On the Sign in page, choose **Forgot your password?**.",
            "Enter your email and choose **Send reset link**.",
            "Open the link in the email (it expires after 3 days) and choose **Set password** with your new password.",
            "Accounts that only use Google sign-in don't have a password; use **Sign in with Google**.",
        ],
    },
    # --- Officers (Officers and Admins) -----------------------------------
    {
        "audience": Role.OFFICER,
        "slug": "applications",
        "title": "Review applications",
        "steps": [
            "Open **Applications** under Officer Tools. Search by name or email, or filter by status.",
            "For each pending application, approve it, or reject it with a reason (a reason is required to reject).",
            "If **Finish account access** appears on a reviewed application, choose it to complete the member's access update.",
        ],
    },
    {
        "audience": Role.OFFICER,
        "slug": "events",
        "title": "Create events and record attendance",
        "steps": [
            "Open **Events** and choose **New event**. Enter the title, location, description, start time and an optional end time, then choose **Save event**.",
            "To change or call off an event, open it and choose **Edit event** or **Cancel event**.",
            "After the event, open it and go to **Attendance**. Check off the members who attended and choose **Save attendance**. Saving again replaces the list.",
        ],
    },
    {
        "audience": Role.OFFICER,
        "slug": "committees",
        "title": "Manage committees and tasks",
        "steps": [
            "Open **Committees** and choose **New committee**. Enter a name and description and confirm the Chair.",
            "Open a committee to **Add a member**, change roles with **Save role**, or **Edit committee**. Only Admins can delete a committee.",
            "Open **Tasks** and choose **New task**. Set the title, description, committee (or the whole organization), due date, priority and assignee, then choose **Save task**.",
            "Committee Chairs can create, edit and assign tasks within the committees they chair.",
        ],
    },
    {
        "audience": Role.OFFICER,
        "slug": "meeting-drafts",
        "title": "Review AI meeting drafts",
        "steps": [
            "Choose **Start Note Transcription** (or open **Notes**). Type your officer notes, and choose **Start Notes** to record the meeting with your microphone. Choose **Submit Notes** when you're done.",
            "The AI writes a summary and proposed action items, saved as a draft that is **Pending review**. Only Officers and Admins can see drafts.",
            "On the draft, edit an action item's text, untick **Keep** to drop it, or add new ones under **Add action items (one per line)**.",
            "Choose a decision (**Approved**, **Revision requested** or **Rejected**) and choose **Submit review**. After a revision request, use **Revise notes and regenerate**.",
            "For an approved draft, choose **Create tasks from accepted action items** and then **Confirm and create tasks**. Nothing becomes a task without an officer's approval.",
        ],
        "notes": [
            {
                "available": "ai_fallback",
                "text": "If the AI service is offline, your notes are still saved as a draft marked **Manual summary**. Write the summary on the draft page, add action items under **Add action items (one per line)**, and submit the review. A summary is required to approve it.",
                "coming_soon_text": "If the AI service is offline, your notes will still be saved and you'll write the summary and action items yourself on the draft page.",
            },
            {
                "available": "recording_upload",
                "text": "To use a recording made elsewhere (phone, Zoom or Teams), choose **Upload a recording** on the Take notes page before **Submit Notes**. Use an mp3, m4a, wav, webm, ogg, flac or mp4 file up to 25 MB.",
                "coming_soon_text": "You'll be able to upload a recording made elsewhere (phone, Zoom or Teams) instead of recording live.",
            },
        ],
    },
    {
        "audience": Role.OFFICER,
        "slug": "publish",
        "title": "Publish announcements and resources",
        "steps": [
            "Open **Announcements** and create an announcement. Add a title, category, **Audience** (all members, or a committee you belong to), tags and the body text.",
            "Optionally set a **Scheduled Auto-Publish Time**, add attachments, a location or a meeting link, and allow comments.",
            "Choose **Publish Announcement**, or **Save Draft** to finish later.",
            "Open **Resources** and choose **Add resource**. Add a title, description, category and tags, then upload a file (up to 25 MB) or enter a link, and choose **Save resource**.",
        ],
    },
    {
        "audience": Role.OFFICER,
        "slug": "reports",
        "title": "View participation reports",
        "steps": [
            "Open **Reports** under Officer Tools. Pick a start and end date and choose **Generate report**.",
            "The report shows each event's RSVPs and attendance, each member's attendance and tasks, and each committee's attendance and tasks. **How numbers are calculated** explains each figure.",
            "Under **Download CSV**, choose a report (all reports as a ZIP, or one table) and choose **Download**.",
            "Scroll down to **Charts** for attendance by event, attendance by committee and tasks by committee for the same dates. The tables above stay available if the charts can't load.",
        ],
    },
    # --- Admins only ------------------------------------------------------
    {
        "audience": Role.ADMIN,
        "slug": "roles",
        "title": "Change roles",
        "steps": [
            "Open **Users** under Admin.",
            "Find the person, choose their new role and choose **Save**. Every role change is recorded in the audit history.",
        ],
    },
    {
        "audience": Role.ADMIN,
        "slug": "officer-applications",
        "title": "Approve officer applications",
        "steps": [
            "Members apply with **Apply to become an officer** on their dashboard.",
            "Open **Applications** and set **Application type** to Officer. Officers can see these requests, but only Admins can decide them.",
            "Approve to promote the member to Officer, or reject with a reason (a reason is required to reject). The member sees the decision under their officer applications.",
            "If an approval is interrupted, choose **Finish approval** to complete it.",
        ],
    },
    {
        "audience": Role.ADMIN,
        "slug": "suspend",
        "title": "Suspend and reinstate accounts",
        "steps": [
            "Open **Users** under Admin and choose **Suspend** or **Reinstate** for the account.",
            "A suspended account can't sign in, and existing sessions stop working.",
            "If **Finish suspension** or **Finish reinstatement** appears, choose it to complete the change.",
        ],
    },
    {
        "audience": Role.ADMIN,
        "slug": "audit",
        "title": "View audit history",
        "steps": [
            "Open **Audit history** under Admin.",
            "Filter by type (role, membership, attendance or task changes) and by date, then choose **Apply filters**.",
        ],
    },
    {
        "audience": Role.ADMIN,
        "slug": "export-roster",
        "title": "Export the roster",
        "steps": [
            "Open **Roster**, search or filter as needed, and choose **Export CSV**.",
            "The file lists each member's username, email, role, committees, join date and account status.",
        ],
    },
]

FAQ = [
    ("I applied. Why can't I see events or the roster yet?",
     "Applicants only see the dashboard and the Apply page until an officer approves the application."),
    ("How soon can I apply again after a rejection?",
     "After 1 day. The rejection reason is shown on the Apply page."),
    ("Why can't I RSVP to an event?",
     "RSVPs close when the event starts, and cancelled events don't take RSVPs."),
    ("Where does my attendance rate count from?",
     "From the date your membership was approved. Events before that aren't counted."),
    ("Which tasks can I see?",
     "Tasks in the committees you belong to, and organization tasks assigned to you. Officers and Admins see all tasks."),
    ("Who can see AI meeting drafts?",
     "Only Officers and Admins. A draft never becomes tasks or an announcement until an officer approves it."),
    ("Why can't I change my email?",
     "Accounts that sign in with Google keep the Google email. Other accounts can change it under Edit profile."),
    ("My password reset link doesn't work.",
     "Reset links expire after 3 days and work once. Request a new one from Forgot your password?."),
    ("Who can delete a committee?",
     "Only Admins, and only after its tasks and committee announcements have been moved or cleared."),
]


def _ai_fallback_available():
    from meetings.models import MeetingDraft

    return any(field.name == "ai_unavailable" for field in MeetingDraft._meta.get_fields())


def _recording_upload_available():
    from meetings import stt

    return hasattr(stt, "transcribe_uploaded_audio")


# A note with "available" shows its finished text once that feature is in the
# running code, and its coming_soon_text (with a Coming soon badge) until then,
# so the Help page is right whichever order the feature PRs merge in.
FEATURE_CHECKS = {
    "ai_fallback": _ai_fallback_available,
    "recording_upload": _recording_upload_available,
}


def _resolve_note(note):
    check = FEATURE_CHECKS.get(note.get("available"))
    if check is None or check():
        return {"text": note["text"], "coming_soon": False}
    return {"text": note["coming_soon_text"], "coming_soon": True}


def guides_for(role_flags):
    """Return the audience sections visible to a viewer.

    role_flags maps each Role in AUDIENCES to whether the viewer has it, e.g.
    {Role.MEMBER: True, Role.OFFICER: True, Role.ADMIN: False}.
    """
    return [
        {
            "title": title,
            "intro": intro,
            "guides": [
                {**g, "notes": [_resolve_note(note) for note in g.get("notes", [])]}
                for g in GUIDES if g["audience"] == role
            ],
        }
        for role, title, intro in AUDIENCES
        if role_flags.get(role)
    ]


def render_markdown():
    """The full guide (every audience) as Markdown for docs/."""
    lines = [
        "# OrgFlow user and admin guide",
        "",
        "<!-- Generated by `python manage.py export_help_docs` from core/help_content.py. Do not edit by hand. -->",
        "",
        "The same guides appear in the app under **Help** in the sidebar, where each person sees the sections for their role.",
        "",
    ]
    for role, title, intro in AUDIENCES:
        lines += [f"## {title}", "", f"_{intro}_", ""]
        for guide in (g for g in GUIDES if g["audience"] == role):
            heading = guide["title"] + (" (coming soon)" if guide.get("coming_soon") else "")
            lines += [f"### {heading}", ""]
            lines += [f"{number}. {step}" for number, step in enumerate(guide["steps"], 1)]
            lines += [""] + [f"> {note['text']}" for note in guide.get("notes", [])]
            if guide.get("notes"):
                lines.append("")
    lines += ["## Frequently asked questions", ""]
    for question, answer in FAQ:
        lines += [f"**{question}**", "", answer, ""]
    return "\n".join(lines).rstrip("\n") + "\n"
