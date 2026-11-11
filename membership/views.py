import csv

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Prefetch
from committees.models import CommitteeMember
from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Profile, Role, get_role

from .emails import send_application_approved, send_application_rejected
from .models import (
    REJECTED_RETENTION,
    ApplicationStatus,
    MembershipApplication,
    next_application_allowed_at,
)


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = MembershipApplication
        fields = ["statement"]
        labels = {"statement": "Why do you want to join?"}


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    note = forms.CharField(
        label="Reason (required when rejecting)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") == "reject" and not (cleaned.get("note") or "").strip():
            raise forms.ValidationError("Give a reason when rejecting. The applicant will see it.")
        return cleaned


@login_required
def apply(request):
    """Applicants submit an application and can see the status of past ones."""
    applications = MembershipApplication.objects.filter(user=request.user)
    has_pending = applications.filter(status=ApplicationStatus.PENDING).exists()
    # After a rejection there's a short wait before applying again.
    wait_until = next_application_allowed_at(request.user)
    has_access_update = applications.filter(access_update_pending=True).exists()
    can_apply = get_role(request.user) == Role.APPLICANT and not has_pending and not has_access_update and wait_until is None

    form = ApplicationForm(request.POST or None)
    if request.method == "POST":
        if not can_apply:
            if wait_until is not None:
                messages.error(request, "You can't apply again yet. Please try after the time shown below.")
            else:
                messages.error(request, "You cannot submit a new application right now.")
            return redirect("membership:apply")
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            application.save()
            messages.success(request, "Application submitted. An officer will review it.")
            return redirect("membership:apply")

    return render(
        request,
        "membership/apply.html",
        {"form": form, "applications": applications, "can_apply": can_apply, "wait_until": wait_until},
    )



@role_required(Role.OFFICER)
def application_list(request):
    """Display membership applications with search and status filtering."""

    search_query = request.GET.get("q", "").strip()[:100]
    selected_status = request.GET.get("status", "").strip().lower()

    applications = MembershipApplication.objects.select_related(
        "user", "reviewed_by"
    )

    # Count all applications before applying filters.
    application_counts = {
        "all": applications.count(),
        "pending": applications.filter(
            status=ApplicationStatus.PENDING
        ).count(),
        "approved": applications.filter(
            status=ApplicationStatus.APPROVED
        ).count(),
        "rejected": applications.filter(
            status=ApplicationStatus.REJECTED
        ).count(),
    }

    # Search by applicant username or email.
    if search_query:
        applications = applications.filter(
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    valid_statuses = {
        ApplicationStatus.PENDING,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    }

    # Only permit supported application status values.
    if selected_status in valid_statuses:
        applications = applications.filter(status=selected_status)
    else:
        selected_status = ""

    pending = applications.filter(
        status=ApplicationStatus.PENDING
    )

    reviewed = applications.exclude(
        status=ApplicationStatus.PENDING
    )

    context = {
        "pending": pending,
        "reviewed": reviewed,
        "search_query": search_query,
        "selected_status": selected_status,
        "application_counts": application_counts,
        "review_form": ReviewForm(),
        "retention_days": REJECTED_RETENTION.days,
    }

    return render(
        request,
        "membership/application_list.html",
        context,
    )



@require_POST
@role_required(Role.OFFICER)
def review_application(request, pk):
    application = get_object_or_404(
        MembershipApplication,
        pk=pk,
    )

    form = ReviewForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            " ".join(form.non_field_errors())
            or "Choose approve or reject.",
        )

    elif not application.is_pending:
        messages.error(
            request,
            "This application has already been reviewed.",
        )

    else:
        approve = form.cleaned_data["decision"] == "approve"

        try:
            application.review(
                request.user,
                approve,
                form.cleaned_data["note"],
            )

        except ValueError as error:
            messages.error(request, str(error))
            return redirect("membership:application_list")

        except DatabaseError:
            _access_update_failure(request, application)
            return redirect("membership:application_list")

        if approve:
            messages.success(
                request,
                f"Application from {application.user.email} approved.",
            )
            send_application_approved(application)
        else:
            messages.success(
                request,
                f"Application from {application.user.email} rejected. "
                "They can sign in to see your reason and apply again.",
            )
            send_application_rejected(application)

    return redirect("membership:application_list")


def _access_update_failure(request, application):
    """Describe persisted state, never assume a decision save succeeded."""
    try:
        application.refresh_from_db()
    except DatabaseError:
        messages.error(request, "Could not confirm the review update. Check the application list before trying again.")
        return
    if application.status != ApplicationStatus.PENDING and application.access_update_pending:
        messages.error(request, "The decision was recorded, but account access is still pending. Use Finish account access under Reviewed Applications to retry.")
    else:
        messages.error(request, "Could not complete the review update. Check the application list and account access before trying again.")


@require_POST
@role_required(Role.OFFICER)
def finish_review_access(request, pk):
    application = get_object_or_404(MembershipApplication, pk=pk)
    try:
        application.complete_access_update()
    except ValueError as error:
        messages.error(request, str(error))
    except DatabaseError:
        _access_update_failure(request, application)
    else:
        messages.success(request, "Account access update completed. The original review decision is unchanged.")
    return redirect("membership:application_list")



def _filter_roster_members(search_query, selected_role):
    """Return a filtered, ordered queryset of roster Profile objects.

    Both the roster page and the CSV export use this so the two always show
    the same set of members.
    """
    members = Profile.objects.filter(role__in=ROSTER_ROLES).select_related("user")

    if search_query:
        members = members.filter(
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    if selected_role in ROSTER_ROLES:
        members = members.filter(role=selected_role)

    committee_memberships = CommitteeMember.objects.select_related("committee")
    members = members.prefetch_related(
        Prefetch("user__committee_memberships", queryset=committee_memberships)
    ).order_by("user__username", "pk")

    return members


@role_required(Role.MEMBER)
def roster(request):
    """Display the member roster with search, role, and committee information."""

    search_query = request.GET.get("q", "").strip()[:100]
    selected_role = request.GET.get("role", "").strip().lower()
    if selected_role not in ROSTER_ROLES:
        selected_role = ""

    members = _filter_roster_members(search_query, selected_role)

    # Filter and paginate before fetching profiles/committee memberships. Large
    # rosters should not render every member on each request (SCRUM-80).
    page = Paginator(members, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "members": page.object_list,
        "page_obj": page,
        "query_string": params.urlencode(),
        "search_query": search_query,
        "selected_role": selected_role,
        "role_choices": [
            (Role.MEMBER, "Member"),
            (Role.OFFICER, "Officer"),
            (Role.ADMIN, "Admin"),
        ],
    }

    return render(request, "membership/roster.html", context)



def _account_status(profile, active_ids, pending_access_ids):
    """The account's actual access, for the roster CSV.

    "active" uses the same rule as the dashboard's Active members count and
    task assignment (tasks.models.eligible_assignees). Otherwise the status
    says why the account can't be used: suspended (or a suspension still
    being applied), pending (a membership approval still updating) or
    disabled (the account is switched off).
    """
    if profile.user_id in active_ids:
        return "active"
    if profile.is_suspended or profile.suspension_update_pending:
        return "suspended"
    if profile.user_id in pending_access_ids:
        return "pending"
    if not profile.user.is_active:
        return "disabled"
    return "inactive"


@role_required(Role.ADMIN)
def export_roster_csv(request):
    """Download the current roster as a CSV file (Admins only, FR-2.4).

    The status column is active, suspended, pending or disabled; see
    _account_status.
    """
    # Imported here to keep the shared import lines unchanged (other open
    # PRs add imports next to them).
    from core.csv_safe import escape_csv_cell
    from tasks.models import eligible_assignees

    search_query = request.GET.get("q", "").strip()[:100]
    selected_role = request.GET.get("role", "").strip().lower()
    if selected_role not in ROSTER_ROLES:
        selected_role = ""

    members = _filter_roster_members(search_query, selected_role)
    active_ids = set(eligible_assignees().values_list("pk", flat=True))
    pending_access_ids = set(
        MembershipApplication.objects.filter(access_update_pending=True).values_list("user_id", flat=True)
    )

    # Dates use the organization's time zone, matching the roster page.
    today = timezone.localdate().strftime("%Y-%m-%d")
    filename = f"orgflow-roster-{today}.csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["username", "email", "role", "committees", "date_joined", "status"])

    for profile in members:
        committee_names = ";".join(
            cm.committee.name
            for cm in profile.user.committee_memberships.all()
        )
        status = _account_status(profile, active_ids, pending_access_ids)
        date_joined = timezone.localtime(profile.created_at).strftime("%Y-%m-%d")
        writer.writerow([
            escape_csv_cell(profile.user.username),
            escape_csv_cell(profile.user.email or ""),
            escape_csv_cell(profile.get_role_display()),
            escape_csv_cell(committee_names),
            escape_csv_cell(date_joined),
            escape_csv_cell(status),
        ])

    return response


@role_required(Role.MEMBER)
def member_detail(request, pk):
    """Display a roster member and their committee participation."""

    member = get_object_or_404(
        Profile.objects.select_related("user"),
        pk=pk,
        role__in=ROSTER_ROLES,
    )

    committee_memberships = (
        CommitteeMember.objects.filter(user=member.user)
        .select_related("committee")
        .order_by("committee__name")
    )

    context = {
        "member": member,
        "committee_memberships": committee_memberships,
    }

    return render(request, "membership/member_detail.html", context)
