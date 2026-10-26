"""Task delegation and committee work (WBS 1.6).

Task changes and their audit entries share one MongoDB document. Mutations go
through tasks.services, which uses a version predicate instead of transactions.
"""

from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounts.models import Profile, ROSTER_ROLES, Role, has_minimum_role
from committees.models import CommitteeMember


class TaskStatus(models.TextChoices):
    TODO = "todo", "To do"
    IN_PROGRESS = "in_progress", "In progress"
    DONE = "done", "Done"


class TaskPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


def manual_origin_key():
    return f"manual:{uuid4()}"


def active_role(user):
    """Read current account state, including changes after a session was loaded."""
    # Membership imports account roles, so keep the recovery-state import local.
    from membership.models import MembershipApplication

    if not getattr(user, "is_authenticated", False) or user.pk is None:
        return None
    current = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    if current is None:
        return None
    if MembershipApplication.objects.filter(
        user_id=user.pk, access_update_pending=True
    ).exists():
        return None
    profile = Profile.objects.filter(user_id=user.pk).first()
    if profile is not None and (profile.is_suspended or profile.suspension_update_pending):
        return None
    if current.is_superuser:
        return Role.ADMIN
    if profile is None or profile.role not in ROSTER_ROLES:
        return None
    return profile.role


def can_manage_tasks(user):
    return has_minimum_role(active_role(user), Role.OFFICER)


def is_committee_member(user, committee_id):
    return bool(committee_id) and CommitteeMember.objects.filter(
        user_id=user.pk, committee_id=committee_id
    ).exists()


def can_update_task(user, task):
    role = active_role(user)
    if role is None:
        return False
    if has_minimum_role(role, Role.OFFICER):
        return True
    return task.assignee_id == user.pk and (
        task.committee_id is None or is_committee_member(user, task.committee_id)
    )


def can_claim_task(user, task):
    return (
        active_role(user) is not None
        and task.assignee_id is None
        and task.status != TaskStatus.DONE
        and is_committee_member(user, task.committee_id)
    )


def eligible_assignees(committee=None):
    """An assignment never restores suspended or departed members' authority."""
    from membership.models import MembershipApplication

    profiles = Profile.objects.filter(is_suspended=False).exclude(suspension_update_pending=True).filter(
        Q(role__in=ROSTER_ROLES) | Q(user__is_superuser=True)
    )
    user_ids = list(profiles.values_list("user_id", flat=True))
    pending_user_ids = list(
        MembershipApplication.objects.filter(access_update_pending=True).values_list("user_id", flat=True)
    )
    users = get_user_model().objects.filter(is_active=True, pk__in=user_ids).exclude(pk__in=pending_user_ids)
    if committee is not None:
        member_ids = list(
            CommitteeMember.objects.filter(committee=committee).values_list("user_id", flat=True)
        )
        users = users.filter(pk__in=member_ids)
    return users.order_by("username")


class TaskQuerySet(models.QuerySet):
    def visible_to(self, user):
        role = active_role(user)
        if role is None:
            return self.none()
        if has_minimum_role(role, Role.OFFICER):
            return self
        committee_ids = list(
            CommitteeMember.objects.filter(user_id=user.pk).values_list("committee_id", flat=True)
        )
        return self.filter(
            Q(committee_id__in=committee_ids)
            | Q(committee__isnull=True, assignee_id=user.pk)
        )


class Task(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    committee = models.ForeignKey(
        "committees.Committee", on_delete=models.PROTECT, null=True, blank=True,
        related_name="tasks",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO)
    version = models.PositiveIntegerField(default=0)
    history = models.JSONField(default=list, blank=True)
    source_action_item = models.ForeignKey(
        "meetings.ActionItem", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="imported_tasks",
    )
    # Nullable unique fields allow only one null in a normal MongoDB index.
    # Every manual task gets its own UUID; imports use the source item ID.
    origin_key = models.CharField(max_length=100, unique=True, default=manual_origin_key, editable=False)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return bool(
            self.due_date and self.due_date < timezone.localdate()
            and self.status != TaskStatus.DONE
        )

    def clean(self):
        super().clean()
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a task title."})
        if self.assignee_id and not eligible_assignees(self.committee).filter(pk=self.assignee_id).exists():
            raise ValidationError({
                "assignee": "Choose an active, unsuspended member of this committee, or leave it unassigned."
                if self.committee_id else "Choose an active, unsuspended organization member."
            })
