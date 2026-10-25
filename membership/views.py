from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q, Prefetch
from committees.models import CommitteeMember
from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Profile, Role, get_role

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
    can_apply = get_role(request.user) == Role.APPLICANT and not has_pending and wait_until is None

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
    applications = MembershipApplication.objects.select_related("user", "reviewed_by")
    return render(
        request,
        "membership/application_list.html",
        {
            "pending": applications.filter(status=ApplicationStatus.PENDING),
            "reviewed": applications.exclude(status=ApplicationStatus.PENDING),
            "review_form": ReviewForm(),
            "retention_days": REJECTED_RETENTION.days,
        },
    )


@require_POST
@role_required(Role.OFFICER)
def review_application(request, pk):
    application = get_object_or_404(MembershipApplication, pk=pk)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(form.non_field_errors()) or "Choose approve or reject.")
    elif not application.is_pending:
        messages.error(request, "This application has already been reviewed.")
    else:
        approve = form.cleaned_data["decision"] == "approve"
        application.review(request.user, approve, form.cleaned_data["note"])
        if approve:
            messages.success(request, f"Application from {application.user.email} approved.")
        else:
            messages.success(
                request,
                f"Application from {application.user.email} rejected. They can sign in to see your reason and apply again.",
            )
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
    ).order_by("user__username")

    context = {
        "members": members,
        "search_query": search_query,
        "selected_role": selected_role,
        "role_choices": [
            (Role.MEMBER, "Member"),
            (Role.OFFICER, "Officer"),
            (Role.ADMIN, "Admin"),
        ],
    }

    return render(request, "membership/roster.html", context)
