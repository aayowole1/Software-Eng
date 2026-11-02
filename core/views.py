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
from events.models import AttendanceAuditLog, Event
from meetings.models import DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication, next_application_allowed_at
from tasks.models import Task, TaskStatus


def dashboard(request):
    """The dashboard is public; signed-in users also see their own sections."""
    context = {"committees_public": Committee.objects.all()}
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
        if has_minimum_role(role, Role.OFFICER):
            context["pending_applications"] = MembershipApplication.objects.filter(
                status=ApplicationStatus.PENDING
            ).count()
            context["pending_drafts"] = MeetingDraft.objects.filter(status=DraftStatus.PENDING_REVIEW).count()
        if has_minimum_role(role, Role.MEMBER):
            assigned = Task.objects.visible_to(request.user).filter(assignee=request.user)
            context["my_tasks"] = assigned.exclude(status=TaskStatus.DONE).order_by("due_date", "-created_at")[:5]
            context["my_task_counts"] = {
                "total": assigned.count(),
                "completed": assigned.filter(status=TaskStatus.DONE).count(),
                "overdue": assigned.exclude(status=TaskStatus.DONE).filter(due_date__lt=timezone.localdate()).count(),
            }
    return render(request, "core/dashboard.html", context)


@role_required(Role.OFFICER)
def audit_history(request):
    """FR-09: Unified audit history for role, membership, attendance, and task changes."""
    entries = []

    # --- Role change history (from Profile.role_history) ---
    for profile in Profile.objects.select_related("user").order_by("user__username"):
        for entry in profile.role_history:
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
    for app in MembershipApplication.objects.select_related("user").order_by("-submitted_at"):
        for entry in app.history:
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
    for log in AttendanceAuditLog.objects.select_related("event", "user", "actor").order_by("-at"):
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
    for task in Task.objects.select_related("committee").order_by("-created_at"):
        for entry in task.history:
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

    # Sort all entries by timestamp descending (newest first).
    entries.sort(key=lambda e: e["at"], reverse=True)

    return render(request, "core/audit_history.html", {"entries": entries[:500]})


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
