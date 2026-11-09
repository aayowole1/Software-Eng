from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q, Prefetch
from committees.models import CommitteeMember
from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Profile, Role, get_role
from officer_applications.models import OfficerApplication

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


class OfficerApplicationForm(forms.ModelForm):
    class Meta:
        model = OfficerApplication
        fields = ["statement"]
        labels = {"statement": "Why do you want to become an officer?"}
        widgets = {"statement": forms.Textarea(attrs={"rows": 4})}


@role_required(Role.MEMBER)
def apply_for_officer(request):
    applications = OfficerApplication.objects.filter(user=request.user)
    pending = applications.filter(status=ApplicationStatus.PENDING)
    is_member = get_role(request.user) == Role.MEMBER
    form = OfficerApplicationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not is_member:
            raise PermissionDenied("Only members can apply to become an officer.")
        if pending.exists():
            messages.error(request, "You already have a pending officer application.")
            return redirect("membership:apply_for_officer")
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            try:
                application.save()
            except DatabaseError:
                messages.error(request, "Submission could not be confirmed. Check your applications before trying again.")
            else:
                messages.success(request, "Officer application submitted. An admin will review it.")
            return redirect("membership:apply_for_officer")
    return render(request, "membership/apply_for_officer.html", {
        "form": form, "applications": applications,
        "can_apply": is_member and not pending.exists(),
    })


@require_POST
@role_required(Role.ADMIN)
def review_officer_application(request, pk):
    application = get_object_or_404(OfficerApplication, pk=pk)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(form.non_field_errors()) or "Choose approve or reject.")
    else:
        approve = form.cleaned_data["decision"] == "approve"
        try:
            application.review(request.user, approve, form.cleaned_data["note"])
        except ValueError as error:
            messages.error(request, str(error))
        except DatabaseError:
            messages.error(request, "The review could not be confirmed. Reload the queue and finish the approval if it is still pending.")
        else:
            messages.success(request, "Officer application approved." if approve else "Officer application rejected.")
    return redirect("membership:application_list")


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
    """Display member and officer applications in one review queue."""

    search_query = request.GET.get("q", "").strip()[:100]
    selected_status = request.GET.get("status", "").strip().lower()
    selected_type = request.GET.get("type", "")
    if selected_type not in {"member", "officer"}:
        selected_type = ""
    applications = [
        model.objects.select_related("user", "reviewed_by")
        for application_type, model in (
            ("member", MembershipApplication), ("officer", OfficerApplication),
        )
        if not selected_type or application_type == selected_type
    ]

    # Count all applications before applying filters.
    application_counts = {
        "all": sum(queryset.count() for queryset in applications),
        **{
            status: sum(queryset.filter(status=status).count() for queryset in applications)
            for status in ApplicationStatus.values
        },
    }

    # Search by applicant username or email.
    if search_query:
        search = Q(user__username__icontains=search_query) | Q(user__email__icontains=search_query)
        applications = [queryset.filter(search) for queryset in applications]

    valid_statuses = {
        ApplicationStatus.PENDING,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    }

    # Only permit supported application status values.
    if selected_status in valid_statuses:
        applications = [queryset.filter(status=selected_status) for queryset in applications]
    else:
        selected_status = ""

    pending = sorted(
        (item for queryset in applications for item in queryset.filter(status=ApplicationStatus.PENDING)),
        key=lambda item: (item.submitted_at, item.pk), reverse=True,
    )
    reviewed = sorted(
        (item for queryset in applications for item in queryset.exclude(status=ApplicationStatus.PENDING)),
        key=lambda item: (item.submitted_at, item.pk), reverse=True,
    )

    context = {
        "pending": pending,
        "reviewed": reviewed,
        "search_query": search_query,
        "selected_status": selected_status,
        "selected_type": selected_type,
        "can_review_officer": get_role(request.user) == Role.ADMIN,
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



@role_required(Role.MEMBER)
def roster(request):
    """Display the member roster with search, role, and committee information."""

    search_query = request.GET.get("q", "").strip()[:100]
    selected_role = request.GET.get("role", "").strip().lower()

    members = Profile.objects.filter(
        role__in=ROSTER_ROLES
    ).select_related("user")

    # Search members by username or email.
    if search_query:
        members = members.filter(
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    # Only allow valid roster roles as filters.
    if selected_role in ROSTER_ROLES:
        members = members.filter(role=selected_role)
    else:
        selected_role = ""

    # Retrieve committee memberships efficiently.
    committee_memberships = CommitteeMember.objects.select_related("committee")

    members = members.prefetch_related(
        Prefetch(
            "user__committee_memberships",
            queryset=committee_memberships,
        )
    ).order_by("user__username", "pk")

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
