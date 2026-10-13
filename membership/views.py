from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Profile, Role, get_role

from .models import ApplicationStatus, MembershipApplication


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = MembershipApplication
        fields = ["statement"]
        labels = {"statement": "Why do you want to join?"}


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    note = forms.CharField(label="Note (optional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))


@login_required
def apply(request):
    """Applicants submit an application and can see the status of past ones."""
    applications = MembershipApplication.objects.filter(user=request.user)
    has_pending = applications.filter(status=ApplicationStatus.PENDING).exists()
    can_apply = get_role(request.user) == Role.APPLICANT and not has_pending

    form = ApplicationForm(request.POST or None)
    if request.method == "POST":
        if not can_apply:
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
        {"form": form, "applications": applications, "can_apply": can_apply},
    )


@role_required(Role.OFFICER)
def application_list(request):
    applications = MembershipApplication.objects.select_related("user", "reviewed_by")
    return render(
        request,
        "membership/application_list.html",
        {
            "pending": applications.filter(status=ApplicationStatus.PENDING),
            "approved": applications.filter(status=ApplicationStatus.APPROVED),
            "review_form": ReviewForm(),
        },
    )


@require_POST
@role_required(Role.OFFICER)
def review_application(request, pk):
    application = get_object_or_404(MembershipApplication, pk=pk)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose approve or reject.")
    elif not application.is_pending:
        messages.error(request, "This application has already been reviewed.")
    else:
        approve = form.cleaned_data["decision"] == "approve"
        email = application.user.email
        application.review(request.user, approve, form.cleaned_data["note"])
        if approve:
            messages.success(request, f"Application from {email} approved.")
        else:
            messages.success(request, f"Application from {email} rejected and removed. They can apply again.")
    return redirect("membership:application_list")


@role_required(Role.MEMBER)
def roster(request):
    members = (
        Profile.objects.filter(role__in=ROSTER_ROLES)
        .select_related("user")
        .order_by("user__username")
    )
    return render(request, "membership/roster.html", {"members": members})
