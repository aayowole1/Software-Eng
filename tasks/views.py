"""Permission-scoped task pages and explicit conversion of reviewed actions."""

from functools import wraps

from bson import ObjectId
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from accounts.models import Profile, ROSTER_ROLES
from committees.models import Committee, CommitteeMember
from meetings.models import DraftStatus, MeetingDraft

from .forms import TaskForm, TaskImportForm, TaskStatusForm
from .models import Task, TaskPriority, TaskStatus, eligible_assignees
from .services import (
    TaskConflict, can_claim_task, can_manage_tasks, can_update_task,
    claim_task, create_task, import_action_items, update_task,
)


def task_access(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        profile = Profile.objects.filter(user=request.user).first()
        if (
            not request.user.is_active
            or (profile and profile.is_suspended)
            or not (request.user.is_superuser or (profile and profile.role in ROSTER_ROLES))
        ):
            raise PermissionDenied("Tasks are available to active organization members.")
        return view(request, *args, **kwargs)
    return wrapped


def _require_manager(user):
    if not can_manage_tasks(user):
        raise PermissionDenied("Only officers and administrators can manage tasks.")


def _task(user, pk):
    return get_object_or_404(Task.objects.visible_to(user), pk=pk)


def _form_error(form, error):
    # Service validation can contain field names unavailable on a status/import form.
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            for message in errors:
                form.add_error(field if field in form.fields else None, message)
    else:
        for message in getattr(error, "messages", [str(error)]):
            form.add_error(None, message)


class TaskFilterForm(forms.Form):
    q = forms.CharField(label="Search tasks", required=False, max_length=200)
    committee = forms.ModelChoiceField(label="Committee", required=False, queryset=Committee.objects.none())
    status = forms.ChoiceField(required=False, choices=[("", "All statuses")] + list(TaskStatus.choices))
    priority = forms.ChoiceField(required=False, choices=[("", "All priorities")] + list(TaskPriority.choices))
    mine = forms.ChoiceField(label="Assigned to", required=False, choices=[("", "Everyone"), ("1", "Me")])
    overdue = forms.ChoiceField(label="Due dates", required=False, choices=[("", "All dates"), ("1", "Overdue")])

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        committees = Committee.objects.all()
        if not can_manage_tasks(user):
            ids = list(CommitteeMember.objects.filter(user=user).values_list("committee_id", flat=True))
            committees = committees.filter(pk__in=ids)
        self.fields["committee"].queryset = committees.order_by("name")


@require_http_methods(["GET"])
@task_access
@never_cache
def assignees(request):
    """Return the same eligible member choices used by the server-side forms."""
    _require_manager(request.user)
    committee = None
    committee_pk = request.GET.get("committee", "")
    if committee_pk:
        if not ObjectId.is_valid(committee_pk):
            raise Http404("Unknown committee.")
        committee = get_object_or_404(Committee, pk=committee_pk)
    return JsonResponse({"assignees": [
        {"id": str(user.pk), "label": user.email or user.username}
        for user in eligible_assignees(committee)
    ]})


@require_http_methods(["GET"])
@task_access
def task_list(request):
    visible = Task.objects.visible_to(request.user)
    counts = {
        "total": visible.count(),
        "completed": visible.filter(status=TaskStatus.DONE).count(),
        "overdue": visible.filter(due_date__lt=timezone.localdate()).exclude(status=TaskStatus.DONE).count(),
    }
    form = TaskFilterForm(request.user, request.GET)
    tasks = visible
    valid = form.is_valid()
    if valid:
        data = form.cleaned_data
        if data["q"]:
            tasks = tasks.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"]))
        for field in ("committee", "status", "priority"):
            if data[field]:
                tasks = tasks.filter(**{field: data[field]})
        if data["mine"]:
            tasks = tasks.filter(assignee=request.user)
        if data["overdue"]:
            tasks = tasks.filter(due_date__lt=timezone.localdate()).exclude(status=TaskStatus.DONE)
    else:
        tasks = tasks.none()
    page = Paginator(tasks.select_related("committee", "assignee").order_by("-created_at", "pk"), 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "tasks/task_list.html", {
        "filter_form": form, "page_obj": page, "counts": counts,
        "can_manage": can_manage_tasks(request.user), "query_string": params.urlencode(),
    }, status=200 if valid else 400)


def _display_history(task):
    labels = {"title": "Title", "description": "Description", "committee": "Committee", "assignee": "Assignee", "due_date": "Due date", "priority": "Priority", "status": "Status"}
    references = {"assignee": set(), "committee": set()}
    for entry in task.history:
        for field, change in entry.get("changes", {}).items():
            if field in references:
                references[field].update(value for value in change.values() if value and ObjectId.is_valid(str(value)))
    users = {str(user.pk): user.get_username() for user in get_user_model().objects.filter(pk__in=references["assignee"])}
    committees = {str(committee.pk): committee.name for committee in Committee.objects.filter(pk__in=references["committee"])}

    def display(field, value):
        if field == "assignee":
            return users.get(str(value), "Former member") if value else "Unassigned"
        if field == "committee":
            return committees.get(str(value), "Former committee") if value else "Organization"
        if field == "status":
            return dict(TaskStatus.choices).get(value, value or "None")
        if field == "priority":
            return dict(TaskPriority.choices).get(value, value or "None")
        return value if value is not None else "None"

    return [
        {**entry, "display_changes": [
            {"label": labels.get(field, field.replace("_", " ").capitalize()),
             "before": display(field, change.get("from")), "after": display(field, change.get("to"))}
            for field, change in entry.get("changes", {}).items()
        ]}
        for entry in task.history
    ]


def _detail(request, task, *, status_form=None, claim_error=None, response_status=200):
    return render(request, "tasks/task_detail.html", {
        "task": task, "can_manage": can_manage_tasks(request.user),
        "can_update": can_update_task(request.user, task), "can_claim": can_claim_task(request.user, task),
        "status_form": status_form if status_form is not None else TaskStatusForm(initial={"status": task.status, "version": task.version}),
        "claim_error": claim_error, "history_entries": _display_history(task),
    }, status=response_status)


@require_http_methods(["GET"])
@task_access
def task_detail(request, pk):
    return _detail(request, _task(request.user, pk))


@require_http_methods(["GET", "POST"])
@task_access
def task_create(request):
    _require_manager(request.user)
    initial = {}
    if request.method == "GET" and request.GET.get("committee"):
        committee_pk = request.GET["committee"]
        if not ObjectId.is_valid(committee_pk):
            raise Http404("Unknown committee.")
        initial["committee"] = get_object_or_404(Committee, pk=committee_pk)
    form = TaskForm(request.user, request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        data.pop("version", None)
        try:
            task = create_task(request.user, **data)
        except ValidationError as error:
            _form_error(form, error)
        else:
            messages.success(request, "Task created.")
            return redirect("tasks:detail", pk=task.pk)
    return render(request, "tasks/task_form.html", {"form": form, "heading": "New task"})


@require_http_methods(["GET", "POST"])
@task_access
def task_edit(request, pk):
    _require_manager(request.user)
    task = _task(request.user, pk)
    form = TaskForm(request.user, request.POST if request.method == "POST" else None, instance=task)
    response_status = 200
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        version = data.pop("version")
        task = _task(request.user, pk)
        try:
            update_task(request.user, task, data, expected_version=version)
        except TaskConflict:
            form.add_error(None, "This task changed while you were editing. Reload the task before trying again.")
            response_status = 409
        except ValidationError as error:
            _form_error(form, error)
        else:
            messages.success(request, "Task updated.")
            return redirect("tasks:detail", pk=task.pk)
    return render(request, "tasks/task_form.html", {"form": form, "heading": "Edit task", "task": task}, status=response_status)


@require_POST
@task_access
def task_update_status(request, pk):
    task = _task(request.user, pk)
    if not can_update_task(request.user, task):
        raise PermissionDenied("Only the assignee or an officer can update this task.")
    form = TaskStatusForm(request.POST)
    response_status = 400
    if form.is_valid():
        try:
            update_task(request.user, task, {"status": form.cleaned_data["status"]}, expected_version=form.cleaned_data["version"])
        except TaskConflict:
            form.add_error(None, "This task changed. Reload it before updating its status.")
            response_status = 409
        except ValidationError as error:
            _form_error(form, error)
        else:
            messages.success(request, "Task status updated.")
            return redirect("tasks:detail", pk=task.pk)
    task = _task(request.user, pk)
    return _detail(request, task, status_form=form, response_status=response_status)


@require_POST
@task_access
def task_claim(request, pk):
    task = _task(request.user, pk)
    form = forms.IntegerField(min_value=0)
    try:
        version = form.clean(request.POST.get("version"))
    except ValidationError:
        return _detail(request, task, claim_error="The task version is missing or invalid. Reload the task and try again.", response_status=400)
    try:
        claim_task(request.user, task, expected_version=version)
    except TaskConflict:
        return _detail(request, _task(request.user, pk), claim_error="This task changed or was claimed by someone else. Review its current assignment.", response_status=409)
    except ValidationError as error:
        return _detail(request, _task(request.user, pk), claim_error=" ".join(error.messages), response_status=400)
    messages.success(request, "Task assigned to you.")
    return redirect("tasks:detail", pk=task.pk)


@require_http_methods(["GET", "POST"])
@task_access
def import_draft(request, pk):
    _require_manager(request.user)
    draft = get_object_or_404(MeetingDraft, pk=pk)
    form = TaskImportForm(request.user, request.POST if request.method == "POST" else None)
    items = draft.action_items.filter(accepted=True)
    response_status = 200
    draft_error = None
    if draft.status != DraftStatus.APPROVED:
        draft_error = "Approve this meeting draft before creating tasks."
        response_status = 400
    elif request.method == "POST" and form.is_valid():
        try:
            result = import_action_items(request.user, draft, **form.cleaned_data)
        except TaskConflict:
            form.add_error(None, "The draft changed during conversion. Review it and try again.")
            response_status = 409
        except ValidationError as error:
            _form_error(form, error)
            response_status = 400
        else:
            messages.success(request, f"Created {len(result['created'])} task(s); {len(result['existing'])} already existed.")
            return redirect("tasks:list")
    return render(request, "tasks/import_draft.html", {"draft": draft, "items": items, "form": form, "draft_error": draft_error, "approved": draft.status == DraftStatus.APPROVED}, status=response_status)
