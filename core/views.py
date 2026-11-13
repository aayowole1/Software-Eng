from datetime import datetime, timezone as dt_timezone

from django import forms
from django.http import JsonResponse
from django.db import DatabaseError, connections
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from pymongo import timeout
from pymongo.errors import PyMongoError

from accounts.decorators import role_required
from accounts.models import Profile, Role, get_role, has_minimum_role
from committees.models import Committee, CommitteeMember
from events.models import AttendanceAuditLog, AttendanceAuditStatus, Event
from meetings.models import DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication, next_application_allowed_at
from tasks.models import Task, TaskStatus
from announcements.permissions import effective_role, visible_announcements
from announcements.models import AnnouncementCommentAudit


def dashboard(request):
    """The dashboard is public; signed-in users also see their own sections."""
    from django.conf import settings as django_settings
    from membership.models import REAPPLY_WAIT

    context = {
        "committees_public": Committee.objects.all(),
        "org_name": django_settings.ORG_NAME,
        "org_mission": django_settings.ORG_MISSION,
        "org_benefits": django_settings.ORG_BENEFITS,
        "org_contact_email": django_settings.ORG_CONTACT_EMAIL,
        "reapply_wait_days": REAPPLY_WAIT.days,
    }
    if request.user.is_authenticated:
        role = get_role(request.user)
        context.update(
            role=role,
            latest_application=MembershipApplication.objects.filter(user=request.user).first(),
            committees=CommitteeMember.objects.filter(user=request.user).select_related("committee"),
            reapply_at=next_application_allowed_at(request.user),
        )
        if has_minimum_role(role, Role.MEMBER):
            # FR-08: upcoming events for signed-in members.
            context["upcoming_events"] = Event.objects.filter(
                starts_at__gte=timezone.now(), cancelled=False
            )[:3]
            announcement_role = effective_role(request.user)
            if has_minimum_role(announcement_role, Role.MEMBER):
                context["recent_announcements"] = visible_announcements(
                    request.user, announcement_role
                ).filter(status="published").order_by("-published_at", "-id")[:3]
        if has_minimum_role(role, Role.OFFICER):
            context["pending_applications"] = MembershipApplication.objects.filter(
                status=ApplicationStatus.PENDING
            ).count()
            context["pending_drafts"] = MeetingDraft.objects.filter(status=DraftStatus.PENDING_REVIEW).count()
            # FR-6.1: summary cards for officers and admins. Imported here so
            # this change doesn't touch the module import lines other PRs edit.
            from tasks.models import eligible_assignees

            # Active members are roster members whose accounts can be used
            # now: switched on, not suspended or mid-suspension, and with no
            # unfinished membership approval. This is the same rule that
            # decides who can be assigned tasks.
            context["summary_active_members"] = eligible_assignees().count()
            context["summary_upcoming_events"] = Event.objects.filter(
                starts_at__gte=timezone.now(),
                cancelled=False,
            ).count()
            context["summary_open_tasks"] = Task.objects.exclude(status=TaskStatus.DONE).count()
            # FR-2.3 / FR-6.1: officer applications (#31) are pending approvals too.
            from officer_applications.models import OfficerApplication

            context["pending_officer_applications"] = OfficerApplication.objects.filter(
                status=ApplicationStatus.PENDING
            ).count()
            context["summary_pending_approvals"] = (
                context["pending_applications"]
                + context["pending_officer_applications"]
                + context["pending_drafts"]
            )
        if has_minimum_role(role, Role.MEMBER):
            assigned = Task.objects.visible_to(request.user).filter(assignee=request.user)
            context["my_tasks"] = assigned.exclude(status=TaskStatus.DONE).order_by("due_date", "-created_at")[:5]
            context["my_task_counts"] = {
                "total": assigned.count(),
                "completed": assigned.filter(status=TaskStatus.DONE).count(),
                "overdue": assigned.exclude(status=TaskStatus.DONE).filter(due_date__lt=timezone.localdate()).count(),
            }
            # US-13: the member's own attendance summary, linking to My account.
            attendance = Event.objects.attendance_summary_for(request.user)
            if attendance["total"]:
                context["attendance_summary"] = attendance
    return render(request, "core/dashboard.html", context)


AUDIT_TYPES = [
    ("role", "Role change"),
    ("membership", "Membership"),
    ("attendance", "Attendance"),
    ("task", "Task"),
    ("comment", "Comment"),
]
AUDIT_DISPLAY_LIMIT = 500


class AuditFilterForm(forms.Form):
    """FR-09 / SCRUM-68: filter the audit history by type and date range."""

    type = forms.ChoiceField(
        label="Type", required=False, choices=[("", "All types"), *AUDIT_TYPES],
    )
    start = forms.DateField(
        label="From", required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )
    end = forms.DateField(
        label="To", required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", "The end date can't be before the start date.")
        return cleaned


def _audit_local_date(value):
    """Return the local calendar date of an ISO timestamp, or None if it can't be read."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if timezone.is_naive(moment):
        moment = moment.replace(tzinfo=dt_timezone.utc)
    return timezone.localtime(moment).date()


@role_required(Role.ADMIN)
def audit_history(request):
    """FR-09: Unified audit history for role, membership, attendance, and task changes.

    Admins can narrow the list by type and by an inclusive date range, using
    the organization's time zone (SCRUM-68).
    """
    form = AuditFilterForm(request.GET or None)
    filters = form.cleaned_data if form.is_bound and form.is_valid() else {}
    selected_type = filters.get("type") or ""
    start, end = filters.get("start"), filters.get("end")

    def wanted(entry_type):
        return not selected_type or selected_type == entry_type

    entries = []

    # --- Role change history (from Profile.role_history) ---
    for profile in Profile.objects.select_related("user").order_by("user__username") if wanted("role") else []:
        for entry in profile.role_history or []:
            entries.append({
                "type": "role",
                "type_label": "Role change",
                "at": entry.get("at", ""),
                "actor": entry.get("actor", ""),
                "description": (
                    f"{profile.user.get_username()}: "
                    f"{entry.get('old_role', '?').capitalize()} → "
                    f"{entry.get('new_role', '?').capitalize()}"
                ),
                "detail": _role_source_label(entry.get("source", "")),
            })

    # --- Membership application history ---
    applications = MembershipApplication.objects.select_related("user").order_by("-submitted_at")
    for app in applications if wanted("membership") else []:
        for entry in app.history or []:
            action = entry.get("action", "")
            entries.append({
                "type": "membership",
                "type_label": "Membership",
                "at": entry.get("at", ""),
                "actor": entry.get("actor", ""),
                "description": (
                    f"{app.user.get_username()}: "
                    f"{_membership_action_label(action)}"
                ),
                "detail": entry.get("note", "") or "",
            })

    # --- Attendance audit log ---
    # Pending removals have not happened yet, so only completed changes are shown.
    attendance_logs = AttendanceAuditLog.objects.filter(status=AttendanceAuditStatus.COMPLETED).select_related(
        "event", "user", "actor"
    ).order_by("-at")
    for log in attendance_logs if wanted("attendance") else []:
        entries.append({
            "type": "attendance",
            "type_label": "Attendance",
            "at": log.at.isoformat() if log.at else "",
            "actor": log.actor.get_username() if log.actor else "Unknown",
            "description": (
                f"{log.user.get_username()} "
                f"{'marked present' if log.action == 'marked' else 'marked absent'} "
                f'for event "{log.event.title}"'
            ),
            "detail": "",
        })

    # --- Task history ---
    for task in Task.objects.select_related("committee").order_by("-created_at") if wanted("task") else []:
        for entry in task.history or []:
            action = entry.get("action", "updated")
            changes = entry.get("changes", {})
            change_fields = ", ".join(changes.keys()) if changes else ""
            entries.append({
                "type": "task",
                "type_label": "Task",
                "at": entry.get("at", ""),
                "actor": entry.get("actor", ""),
                "description": (
                    f'Task "{task.title}": {action.capitalize()}'
                    + (f" ({change_fields})" if change_fields else "")
                ),
                "detail": "",
            })

    # --- Announcement comment history ---
    for audit in (
        AnnouncementCommentAudit.objects.select_related("announcement", "author", "actor")
        .order_by("-created_at") if wanted("comment") else []
    ):
        entries.append({
            "type": "comment",
            "type_label": "Comment",
            "at": audit.created_at.isoformat() if audit.created_at else "",
            "actor": audit.actor.get_username() if audit.actor else "Unknown",
            "description": (
                f'Comment on "{audit.announcement.title}": {audit.action.capitalize()}'
            ),
            "detail": audit.detail or "",
        })

    if start or end:
        dated = [(entry, _audit_local_date(entry["at"])) for entry in entries]
        entries = [
            entry for entry, day in dated
            if day is not None and (not start or day >= start) and (not end or day <= end)
        ]

    # Sort all entries by timestamp descending (newest first).
    entries.sort(key=lambda e: e["at"], reverse=True)

    return render(
        request,
        "core/audit_history.html",
        {
            "entries": entries[:AUDIT_DISPLAY_LIMIT],
            "total_matching": len(entries),
            "display_limit": AUDIT_DISPLAY_LIMIT,
            "filter_form": form,
            "is_filtered": bool(selected_type or start or end),
        },
        status=400 if form.is_bound and not form.is_valid() else 200,
    )


def _role_source_label(source):
    if source == "account_role_management":
        return "Administrator role change"
    if source and source.startswith("membership_review:"):
        return "Membership approval"
    if source == "system":
        return "System update"
    if source == "rejected_membership_reconciliation":
        return "Rejected membership access correction"
    return source or ""


def _membership_action_label(action):
    labels = {
        "submitted": "Application submitted",
        "approved": "Application approved",
        "rejected": "Application rejected",
    }
    return labels.get(action, action.capitalize() if action else "Event")


def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
@never_cache
def readiness(request):
    """Bounded database readiness; never return connection or credential details."""
    try:
        with timeout(3):
            connections["default"].get_database().command("ping")
    except (DatabaseError, PyMongoError):
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


def help_page(request):
    """SCRUM-50: FAQ and step-by-step guides; officer and admin guides by role."""
    from django.contrib.auth.views import redirect_to_login

    from .help_content import FAQ, guides_for

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    role = get_role(request.user)
    sections = guides_for({
        Role.MEMBER: True,
        Role.OFFICER: has_minimum_role(role, Role.OFFICER),
        Role.ADMIN: has_minimum_role(role, Role.ADMIN),
    })
    return render(request, "core/help.html", {"sections": sections, "faq": FAQ})
