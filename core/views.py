from django.http import JsonResponse
from django.db import DatabaseError, connections
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from pymongo import timeout
from pymongo.errors import PyMongoError
from django.shortcuts import render
from django.utils import timezone

from accounts.models import Role, get_role, has_minimum_role
from committees.models import Committee, CommitteeMember
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
