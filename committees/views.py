from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Role
from tasks.models import Task, TaskStatus
from tasks.services import can_manage_tasks

from .models import Committee, CommitteeMember, CommitteeRole

User = get_user_model()


class CommitteeForm(forms.ModelForm):
    class Meta:
        model = Committee
        fields = ["name", "description"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Committee.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("A committee with this name already exists.")
        return name


class AddMemberForm(forms.Form):
    user = forms.ModelChoiceField(label="Member", queryset=User.objects.none())
    role = forms.ChoiceField(label="Committee role", choices=CommitteeRole.choices, initial=CommitteeRole.MEMBER)

    def __init__(self, committee, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = list(committee.members.values_list("user_id", flat=True))
        # Only people on the organization roster can join a committee.
        self.fields["user"].queryset = (
            User.objects.filter(profile__role__in=ROSTER_ROLES)
            .exclude(pk__in=existing)
            .order_by("username")
        )
        self.fields["user"].label_from_instance = lambda u: u.email or u.username


@role_required(Role.MEMBER)
def committee_list(request):
    return render(request, "committees/committee_list.html", {"committees": Committee.objects.all()})


@role_required(Role.OFFICER)
def committee_create(request):
    form = CommitteeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        committee = form.save(commit=False)
        committee.created_by = request.user
        committee.save()
        # The creator chairs the new committee.
        CommitteeMember.objects.create(committee=committee, user=request.user, role=CommitteeRole.CHAIR)
        messages.success(request, f"Committee “{committee.name}” created.")
        return redirect("committees:detail", pk=committee.pk)
    return render(request, "committees/committee_form.html", {"form": form})


@role_required(Role.MEMBER)
def committee_detail(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    visible_tasks = Task.objects.visible_to(request.user).filter(committee=committee)
    return render(
        request,
        "committees/committee_detail.html",
        {
            "committee": committee,
            "roster": committee.members.select_related("user"),
            "add_form": AddMemberForm(committee),
            "can_see_tasks": can_manage_tasks(request.user) or committee.members.filter(user=request.user).exists(),
            "task_counts": {
                "total": visible_tasks.count(),
                "completed": visible_tasks.filter(status=TaskStatus.DONE).count(),
                "overdue": visible_tasks.exclude(status=TaskStatus.DONE).filter(due_date__lt=timezone.localdate()).count(),
            },
        },
    )


@require_POST
@role_required(Role.ADMIN)
def committee_delete(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    # Let Django collect the cascade before changing the roster. A protected
    # task must leave both the committee and its memberships intact.
    try:
        committee.delete()
    except ProtectedError:
        messages.error(request, "Move this committee's tasks or clear their committee assignment before deleting the committee.")
        return redirect("committees:detail", pk=committee.pk)
    messages.success(request, f"Committee “{committee.name}” deleted.")
    return redirect("committees:list")


@require_POST
@role_required(Role.OFFICER)
def add_member(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    form = AddMemberForm(committee, request.POST)
    if form.is_valid():
        user = form.cleaned_data["user"]
        CommitteeMember.objects.create(committee=committee, user=user, role=form.cleaned_data["role"])
        messages.success(request, f"{user.email} added to {committee.name}.")
    else:
        messages.error(request, "Choose a roster member who is not already on this committee.")
    return redirect("committees:detail", pk=committee.pk)


@require_POST
@role_required(Role.OFFICER)
def remove_member(request, pk, user_pk):
    committee = get_object_or_404(Committee, pk=pk)
    membership = get_object_or_404(CommitteeMember, committee=committee, user_id=user_pk)
    membership.delete()
    messages.success(request, f"{membership.user.email} removed from {committee.name}.")
    return redirect("committees:detail", pk=committee.pk)
