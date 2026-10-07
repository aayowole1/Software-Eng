from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.models import Role, get_role, has_minimum_role
from committees.models import CommitteeMember
from meetings.models import DraftStatus, MeetingDraft
from membership.models import ApplicationStatus, MembershipApplication


def home(request):
    """Public landing page."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    role = get_role(request.user)
    context = {
        "role": role,
        "latest_application": MembershipApplication.objects.filter(user=request.user).first(),
        "committees": CommitteeMember.objects.filter(user=request.user).select_related("committee"),
    }
    if has_minimum_role(role, Role.OFFICER):
        context["pending_applications"] = MembershipApplication.objects.filter(
            status=ApplicationStatus.PENDING
        ).count()
        context["pending_drafts"] = MeetingDraft.objects.filter(status=DraftStatus.PENDING_REVIEW).count()
    return render(request, "core/dashboard.html", context)


def health(request):
    return JsonResponse({"status": "ok"})
