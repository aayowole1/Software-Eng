from hashlib import sha256
import json

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import role_required
from accounts.models import Role
from tasks.models import Task, TaskStatus, eligible_assignees
from tasks.services import can_manage_tasks

from .models import Committee, CommitteeMember, CommitteeRole

User = get_user_model()


class CommitteeForm(forms.ModelForm):
    class Meta:
        model = Committee
        fields = ["name", "description"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        matches = Committee.objects.filter(name__iexact=name)
        if self.instance.pk:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise forms.ValidationError("A committee with this name already exists.")
        return name


class CommitteeEditForm(CommitteeForm):
    revision = forms.CharField(widget=forms.HiddenInput)


class CommitteeMemberRoleForm(forms.Form):
    role = forms.ChoiceField(label="Committee role", choices=CommitteeRole.choices)
    revision = forms.CharField(widget=forms.HiddenInput)


EDIT_SALT = "committees.edit.v1"
MEMBER_ROLE_SALT = "committees.member-role.v1"


def _digest(values):
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _revision(obj, values, salt):
    # Store a fixed-size fingerprint instead of repeating a long description.
    return signing.dumps({"id": str(obj.pk), "snapshot": _digest(values)}, salt=salt)


def _check_revision(form, obj, values, salt):
    try:
        original = signing.loads(form.cleaned_data["revision"], salt=salt, max_age=86400)
    except signing.BadSignature:
        form.add_error(None, "This form expired or is invalid. Reload before trying again.")
        return 400
    if not isinstance(original, dict) or original.get("id") != str(obj.pk):
        form.add_error(None, "This form does not match the selected record. Reload before trying again.")
        return 400
    if original.get("snapshot") != _digest(values):
        form.add_error(None, "This record changed while you were editing. Reload before trying again.")
        return 409
    return None


def _committee_values(committee):
    return {"name": committee.name, "description": committee.description}


def _member_values(membership):
    return {
        "committee_id": str(membership.committee_id), "user_id": str(membership.user_id),
        "role": membership.role,
    }


def _require_current_manager(user):
    # Recheck effective database state even if a previously loaded request user
    # still looks active; a committee Chair is not an organization Officer.
    if not can_manage_tasks(user):
        raise PermissionDenied("Only active officers and admins can manage committees.")


class AddMemberForm(forms.Form):
    user = forms.ModelChoiceField(label="Member", queryset=User.objects.none())
    role = forms.ChoiceField(label="Committee role", choices=CommitteeRole.choices, initial=CommitteeRole.MEMBER)

    def __init__(self, committee, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = list(committee.members.values_list("user_id", flat=True))
        # Committee membership uses the same effective-access eligibility as delegation.
        self.fields["user"].queryset = (
            eligible_assignees(None)
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
    return _render_detail(request, committee)


def _render_detail(request, committee, *, role_form=None, role_user_id=None, status=200):
    visible_tasks = Task.objects.visible_to(request.user).filter(committee=committee)
    can_manage = can_manage_tasks(request.user)
    roster = list(committee.members.select_related("user"))
    if can_manage:
        for membership in roster:
            membership.role_form = role_form if membership.user_id == role_user_id else CommitteeMemberRoleForm(
                initial={
                    "role": membership.role,
                    "revision": _revision(membership, _member_values(membership), MEMBER_ROLE_SALT),
                },
                auto_id=f"member-role-{membership.pk}-%s",
            )
    return render(
        request,
        "committees/committee_detail.html",
        {
            "committee": committee,
            "roster": roster,
            "role_target_missing": role_form is not None and not any(
                membership.user_id == role_user_id for membership in roster
            ),
            "add_form": AddMemberForm(committee),
            "can_manage_committee": can_manage,
            "can_see_tasks": can_manage or committee.members.filter(user=request.user).exists(),
            "task_counts": {
                "total": visible_tasks.count(),
                "completed": visible_tasks.filter(status=TaskStatus.DONE).count(),
                "overdue": visible_tasks.exclude(status=TaskStatus.DONE).filter(due_date__lt=timezone.localdate()).count(),
            },
        },
        status=status,
    )


@require_http_methods(["GET", "POST"])
@role_required(Role.OFFICER)
def committee_edit(request, pk):
    _require_current_manager(request.user)
    committee = get_object_or_404(Committee, pk=pk)
    form = CommitteeEditForm(
        request.POST if request.method == "POST" else None, instance=committee,
        initial={"revision": _revision(committee, _committee_values(committee), EDIT_SALT)},
    )
    status = 200
    if request.method == "POST":
        status = 400
        if form.is_valid():
            # ModelForm validation mutates its instance. Reload the stored values
            # before comparing the original fingerprint or building the CAS.
            current = get_object_or_404(Committee, pk=pk)
            before = _committee_values(current)
            status = _check_revision(form, current, before, EDIT_SALT)
            if status is None:
                after = {field: form.cleaned_data[field] for field in before}
                if before == after:
                    messages.info(request, "No committee changes were needed.")
                    return redirect("committees:detail", pk=pk)
                try:
                    changed = Committee.objects.filter(pk=pk, **before).update(**after)
                except IntegrityError:
                    form.add_error("name", "A committee with this name already exists.")
                    status = 400
                except DatabaseError:
                    form.add_error(None, "The update could not be confirmed. Reload the committee before retrying.")
                    status = 503
                else:
                    if changed == 1:
                        messages.success(request, "Committee updated.")
                        return redirect("committees:detail", pk=pk)
                    form.add_error(None, "This committee changed while you were editing. Reload before trying again.")
                    status = 409
    return render(request, "committees/committee_form.html", {
        "form": form, "committee": committee, "editing": True,
    }, status=status)


@require_POST
@role_required(Role.OFFICER)
def update_member_role(request, pk, user_pk):
    _require_current_manager(request.user)
    committee = get_object_or_404(Committee, pk=pk)
    membership = get_object_or_404(CommitteeMember, committee=committee, user_id=user_pk)
    form = CommitteeMemberRoleForm(request.POST, auto_id=f"member-role-{membership.pk}-%s")
    status = 400
    if form.is_valid():
        # Changing a committee label cannot restore a departed/suspended account
        # or bypass an unfinished membership/suspension access update.
        if not eligible_assignees(committee).filter(pk=user_pk).exists():
            form.add_error(None, "Choose a current active, unsuspended organization member before changing this committee role.")
        else:
            status = _check_revision(form, membership, _member_values(membership), MEMBER_ROLE_SALT)
            if status is None:
                role = form.cleaned_data["role"]
                if role == membership.role:
                    messages.info(request, "No committee role change was needed.")
                    return redirect("committees:detail", pk=pk)
                try:
                    changed = CommitteeMember.objects.filter(
                        pk=membership.pk, committee_id=pk, user_id=user_pk, role=membership.role,
                    ).update(role=role)
                except DatabaseError:
                    form.add_error(None, "The role update could not be confirmed. Reload the roster before retrying.")
                    status = 503
                else:
                    if changed == 1:
                        messages.success(request, "Committee role updated. Organization authority is unchanged.")
                        return redirect("committees:detail", pk=pk)
                    form.add_error(None, "This membership changed while you were editing. Reload before trying again.")
                    status = 409
    return _render_detail(request, committee, role_form=form, role_user_id=user_pk, status=status)


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
