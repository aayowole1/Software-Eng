"""Authorized task mutations with a single-document compare-and-set audit."""

from hashlib import sha256

from bson import BSON
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.utils import timezone

from meetings.models import DraftStatus, MeetingDraft

from .models import (
    Task, TaskStatus, can_claim_task, can_manage_tasks, can_update_task,
)


class TaskConflict(Exception):
    """The submitted version no longer matches the stored task."""


EDITABLE_FIELDS = {"title", "description", "committee", "assignee", "due_date", "priority", "status"}
# Leave substantial room below MongoDB's 16 MiB document limit for task fields
# and BSON overhead. Existing history is retained; a full history blocks writes.
MAX_HISTORY_BSON_BYTES = 8 * 1024 * 1024
DESCRIPTION_AUDIT_THRESHOLD = 240
DESCRIPTION_AUDIT_PREVIEW = 160


def _snapshot(task):
    return {
        "title": task.title,
        "description": task.description,
        "committee": str(task.committee_id) if task.committee_id else None,
        "assignee": str(task.assignee_id) if task.assignee_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "priority": str(task.priority),
        "status": str(task.status),
    }


def _audit_value(field, value):
    if field == "description" and isinstance(value, str) and len(value) > DESCRIPTION_AUDIT_THRESHOLD:
        return {
            "abbreviated": True,
            "preview": value[:DESCRIPTION_AUDIT_PREVIEW],
            "length": len(value),
            "sha256": sha256(value.encode("utf-8")).hexdigest(),
        }
    return value


def _validate_history_capacity(history):
    if len(BSON.encode({"history": history})) > MAX_HISTORY_BSON_BYTES:
        raise ValidationError(
            "Task history has reached its storage limit. This change was not saved. Contact an administrator."
        )


def _entry(actor, action, before, after):
    return {
        "at": timezone.now().isoformat(),
        "actor_id": str(actor.pk),
        "actor": actor.get_username(),
        "action": action,
        "changes": {
            key: {"from": _audit_value(key, before.get(key)), "to": _audit_value(key, value)}
            for key, value in after.items() if before.get(key) != value
        },
    }


def _validate_fields(fields):
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unsupported task fields: {', '.join(sorted(unknown))}.")


def _create(actor, fields, *, origin_key=None, source_action_item=None, action="created"):
    if not can_manage_tasks(actor):
        raise PermissionDenied("Only officers and admins can create or delegate tasks.")
    fields = dict(fields)
    version = fields.pop("version", None)
    if version not in (None, 0):
        raise ValidationError("A new task cannot have an existing version.")
    _validate_fields(fields)
    task = Task(created_by=actor, source_action_item=source_action_item, **fields)
    if origin_key is not None:
        task.origin_key = origin_key
    task.full_clean(validate_unique=False, validate_constraints=False)
    task.history = [_entry(actor, action, {}, _snapshot(task))]
    _validate_history_capacity(task.history)
    task.save(force_insert=True)
    return task


def create_task(actor, **fields):
    return _create(actor, fields)


def _current(actor, task, expected_version):
    try:
        current = Task.objects.visible_to(actor).get(pk=task.pk)
    except Task.DoesNotExist:
        raise PermissionDenied("You cannot access this task.") from None
    if type(expected_version) is not int or expected_version < 0:
        raise ValidationError({"version": "A valid task version is required. Reload the task."})
    if current.version != expected_version:
        raise TaskConflict("This task changed while you were working. Reload it before trying again.")
    return current


def _persist(actor, task, changes, expected_version, action):
    before = _snapshot(task)
    for name, value in changes.items():
        setattr(task, name, value)
    task.full_clean(validate_unique=False, validate_constraints=False)
    after = _snapshot(task)
    if before == after:
        return task
    entry = _entry(actor, action, before, after)
    history = [*task.history, entry]
    _validate_history_capacity(history)
    changed = {name for name in after if before[name] != after[name]}
    values = {
        name: getattr(task, name + "_id") if name in {"committee", "assignee"} else getattr(task, name)
        for name in changed
    }
    # A conditional update atomically writes the new state, version and audit
    # to this one document on standalone MongoDB. Stale requests write nothing.
    values.update(
        version=expected_version + 1,
        updated_at=timezone.now(),
        history=history,
    )
    updated = Task.objects.filter(pk=task.pk, version=expected_version).update(**values)
    if updated != 1:
        raise TaskConflict("This task changed while you were working. Reload it before trying again.")
    task.refresh_from_db()
    return task


def update_task(actor, task, changes, expected_version):
    changes = dict(changes)
    _validate_fields(changes)
    current = _current(actor, task, expected_version)
    if not can_update_task(actor, current):
        raise PermissionDenied("You cannot update this task.")
    if not can_manage_tasks(actor) and set(changes) - {"status"}:
        raise PermissionDenied("Assignees can update progress; officers manage task details and delegation.")
    return _persist(actor, current, changes, expected_version, "updated")


def claim_task(actor, task, expected_version):
    current = _current(actor, task, expected_version)
    if not can_claim_task(actor, current):
        raise PermissionDenied("Only a current committee member can claim an unfinished, unassigned committee task.")
    return _persist(actor, current, {"assignee": actor}, expected_version, "claimed")


def accepted_actions_for_import(draft):
    """One source of truth for the confirmation page and task creation."""
    items = draft.current_action_items
    if draft.review_item_intent is None:
        return [{"source": item, "description": item.description} for item in items.filter(accepted=True)]
    accepted = [item for item in draft.review_item_intent if item["accepted"]]
    sources = {str(item.pk): item for item in items.filter(pk__in=[item["id"] for item in accepted])}
    return [
        {"source": sources[item["id"]], "description": item["description"]}
        for item in accepted if item["id"] in sources
    ]


def import_action_items(actor, draft, **assignment_defaults):
    """Convert approved accepted items once, safely retrying a partial import.

    Each task's unique origin key is the idempotency guarantee. An interrupted
    batch can be retried without duplicating prior tasks or modifying them.
    """
    if not can_manage_tasks(actor):
        raise PermissionDenied("Only officers and admins can import approved meeting actions.")
    current = MeetingDraft.objects.get(pk=draft.pk)
    if current.status != DraftStatus.APPROVED:
        raise ValidationError("Only an approved meeting draft can create tasks.")
    if current.review_update_pending:
        raise ValidationError("Finish the recorded meeting review's action updates before creating tasks.")
    defaults = dict(assignment_defaults)
    if set(defaults) - {"committee", "assignee", "due_date", "priority"}:
        raise ValidationError("Choose only committee, assignee, due date and priority for imported tasks.")
    # Validate the complete assignment before creating any records, including
    # on an empty or already imported draft.
    candidate = Task(title="Meeting action", created_by=actor, **defaults)
    candidate.full_clean(validate_unique=False, validate_constraints=False)
    result = {"created": [], "existing": []}
    for approved in accepted_actions_for_import(current):
        item = approved["source"]
        key = f"meeting:{item.pk}"
        existing = Task.objects.filter(origin_key=key).first()
        if existing is not None:
            result["existing"].append(existing)
            continue
        description = approved["description"].strip()
        if not description:
            continue
        fields = {**defaults, "title": description[:200], "description": description, "status": TaskStatus.TODO}
        try:
            task = _create(actor, fields, origin_key=key, source_action_item=item, action="imported")
        except IntegrityError:
            # Another request imported the same source while this one was
            # validating. Only suppress the expected idempotency collision.
            existing = Task.objects.filter(origin_key=key).first()
            if existing is None:
                raise
            result["existing"].append(existing)
        else:
            result["created"].append(task)
    return result
