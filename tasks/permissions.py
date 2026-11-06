"""Committee Chair authority is limited to task management in that committee."""

from committees.models import Committee, CommitteeMember, CommitteeRole

from .models import active_role, can_manage_tasks, can_update_task as can_update_assigned_task


def manageable_committees(user):
    if can_manage_tasks(user):
        return Committee.objects.all()
    if active_role(user) is None:
        return Committee.objects.none()
    committee_ids = list(CommitteeMember.objects.filter(
        user_id=user.pk, role=CommitteeRole.CHAIR,
    ).values_list("committee_id", flat=True))
    return Committee.objects.filter(pk__in=committee_ids)


def can_create_tasks(user):
    return can_manage_tasks(user) or manageable_committees(user).exists()


def can_manage_committee_tasks(user, committee):
    if can_manage_tasks(user):
        return True
    committee_id = getattr(committee, "pk", committee)
    return bool(committee_id) and manageable_committees(user).filter(pk=committee_id).exists()


def can_manage_task_details(user, task):
    return can_manage_committee_tasks(user, task.committee_id)


def can_update_task(user, task):
    return can_manage_task_details(user, task) or can_update_assigned_task(user, task)
