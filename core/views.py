from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import Role, get_role, has_minimum_role
from committees.models import Committee, CommitteeMember
from events.models import Event
from meetings.models import DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication, next_application_allowed_at


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
    return render(request, "core/dashboard.html", context)


def health(request):
    return JsonResponse({"status": "ok"})
