"""Participation and engagement reports for leadership (FR-6.2, FR-6.3; SCRUM-64)."""

import csv
import io
import zipfile
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import Role, ROSTER_ROLES
from committees.models import Committee, CommitteeMember
from events.models import Attendance, Event, RSVP, RSVPResponse, member_since_by_user
from tasks.models import Task, TaskStatus

User = get_user_model()

# Characters that can trigger formula injection in spreadsheet software.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _escape_csv(value):
    """Prefix cells whose first character can trigger spreadsheet formulas."""
    s = str(value) if value is not None else ""
    if s and s[0] in _FORMULA_TRIGGERS:
        return "'" + s
    return s


class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Start date",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="End date",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before start date.")
        return cleaned


def _default_dates():
    today = timezone.localdate()
    return today - timedelta(days=30), today


def _build_report(start_date, end_date):
    """Return a dict of all report data for the given inclusive date range."""
    tz = timezone.get_current_timezone()

    # The range covers whole local days: from midnight at the start of
    # start_date up to (not including) midnight after end_date, so nothing
    # late on the end date is dropped.
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end_exclusive = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)

    # Events held: non-cancelled events in the range that have already started.
    # Upcoming events haven't been held yet, so they don't lower attendance.
    events_qs = Event.objects.filter(
        starts_at__gte=start_dt,
        starts_at__lt=min(end_exclusive, timezone.now()),
        cancelled=False,
    ).order_by("starts_at")
    events = list(events_qs)
    event_ids = [e.pk for e in events]

    # Tasks created in the range (all statuses).
    tasks_qs = Task.objects.filter(
        created_at__gte=start_dt,
        created_at__lt=end_exclusive,
    )

    today = timezone.localdate()

    # --- Per-event attendance data ---
    rsvp_going_counts = {}
    for rsvp in RSVP.objects.filter(event_id__in=event_ids, response=RSVPResponse.GOING):
        rsvp_going_counts[rsvp.event_id] = rsvp_going_counts.get(rsvp.event_id, 0) + 1

    attendance_records = list(Attendance.objects.filter(event_id__in=event_ids).select_related("user"))
    attended_by_event = {}
    for att in attendance_records:
        attended_by_event.setdefault(att.event_id, []).append(att.user_id)

    per_event = []
    for event in events:
        eid = event.pk
        per_event.append({
            "event": event,
            "rsvps_going": rsvp_going_counts.get(eid, 0),
            "attended": len(attended_by_event.get(eid, [])),
        })

    # --- Per-member data ---
    # Active roster members only.
    roster_users = list(
        User.objects.filter(profile__role__in=ROSTER_ROLES).order_by("username")
    )

    events_held = len(events)

    # Each member is only counted for events since their membership started
    # (their latest approval), matching the member's own attendance page.
    committee_memberships = list(CommitteeMember.objects.all())
    counted_users = {u.pk: u for u in roster_users}
    missing_ids = {cm.user_id for cm in committee_memberships} - set(counted_users)
    if missing_ids:
        counted_users.update({u.pk: u for u in User.objects.filter(pk__in=list(missing_ids))})
    since_by_user = member_since_by_user(counted_users.values())
    event_start = {e.pk: e.starts_at for e in events}

    held_by_user = {
        uid: sum(1 for e in events if e.starts_at >= since)
        for uid, since in since_by_user.items()
    }
    attended_by_user = {}
    for att in attendance_records:
        since = since_by_user.get(att.user_id)
        if since is not None and event_start[att.event_id] >= since:
            attended_by_user[att.user_id] = attended_by_user.get(att.user_id, 0) + 1

    # Task counts per member: tasks assigned to this user in the range.
    task_assigned = {}
    task_completed = {}
    task_overdue = {}
    for task in tasks_qs.select_related("assignee"):
        if task.assignee_id is None:
            continue
        uid = task.assignee_id
        task_assigned[uid] = task_assigned.get(uid, 0) + 1
        if task.status == TaskStatus.DONE:
            task_completed[uid] = task_completed.get(uid, 0) + 1
        if task.is_overdue:
            task_overdue[uid] = task_overdue.get(uid, 0) + 1

    per_member = []
    for user in roster_users:
        uid = user.pk
        attended = attended_by_user.get(uid, 0)
        member_held = held_by_user.get(uid, 0)
        pct = round(attended / member_held * 100, 1) if member_held > 0 else None
        per_member.append({
            "user": user,
            "attended": attended,
            "events_held": member_held,
            "attendance_pct": pct,
            "tasks_assigned": task_assigned.get(uid, 0),
            "tasks_completed": task_completed.get(uid, 0),
            "tasks_overdue": task_overdue.get(uid, 0),
        })

    # --- Per-committee data ---
    committees = list(Committee.objects.all().order_by("name"))

    # Map committee_id -> set of member user_ids.
    committee_member_ids = {}
    for cm in committee_memberships:
        committee_member_ids.setdefault(cm.committee_id, set()).add(cm.user_id)

    # Task counts per committee.
    ctask_total = {}
    ctask_completed = {}
    ctask_overdue = {}
    for task in tasks_qs:
        if task.committee_id is None:
            continue
        cid = task.committee_id
        ctask_total[cid] = ctask_total.get(cid, 0) + 1
        if task.status == TaskStatus.DONE:
            ctask_completed[cid] = ctask_completed.get(cid, 0) + 1
        if task.is_overdue:
            ctask_overdue[cid] = ctask_overdue.get(cid, 0) + 1

    per_committee = []
    for committee in committees:
        cid = committee.pk
        member_ids = committee_member_ids.get(cid, set())
        num_members = len(member_ids)

        # Attendance %: the members' attendances divided by the events each of
        # them could attend since their membership started.
        total_possible = sum(held_by_user.get(uid, 0) for uid in member_ids)
        if total_possible > 0:
            total_attended = sum(attended_by_user.get(uid, 0) for uid in member_ids)
            att_pct = round(total_attended / total_possible * 100, 1)
        else:
            att_pct = None

        per_committee.append({
            "committee": committee,
            "num_members": num_members,
            "attendance_pct": att_pct,
            "tasks_total": ctask_total.get(cid, 0),
            "tasks_completed": ctask_completed.get(cid, 0),
            "tasks_overdue": ctask_overdue.get(cid, 0),
        })

    return {
        "per_event": per_event,
        "per_member": per_member,
        "per_committee": per_committee,
        "events_held": events_held,
        "start_date": start_date,
        "end_date": end_date,
    }


@role_required(Role.OFFICER)
def report(request):
    start_default, end_default = _default_dates()

    if request.GET.get("start_date") or request.GET.get("end_date"):
        form = DateRangeForm(request.GET)
        if form.is_valid():
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            data = _build_report(start_date, end_date)
        else:
            data = None
    else:
        form = DateRangeForm(initial={"start_date": start_default, "end_date": end_default})
        data = _build_report(start_default, end_default)

    return render(request, "reports/report.html", {"form": form, "data": data})


def _validate_csv_range(request):
    """Validate the date range from request GET params.

    Returns (data, None) on success or (None, error_response) on failure.
    """
    start_default, end_default = _default_dates()
    if request.GET.get("start_date") or request.GET.get("end_date"):
        form = DateRangeForm(request.GET)
    else:
        form = DateRangeForm({"start_date": start_default, "end_date": end_default})

    if not form.is_valid():
        # Never silently export a different range than the one requested.
        errors = "; ".join(str(e) for errs in form.errors.values() for e in errs)
        return None, HttpResponseBadRequest(
            f"Invalid date range: {errors}", content_type="text/plain; charset=utf-8"
        )

    start_date = form.cleaned_data["start_date"]
    end_date = form.cleaned_data["end_date"]
    return _build_report(start_date, end_date), None


REPORT_TABLES = {"events": "Events", "members": "Members", "committees": "Committees"}


def _report_filename(name, start_date, end_date, extension="csv"):
    return f"orgflow-report-{name}-{start_date}_{end_date}.{extension}"


def _csv_text(rows):
    """Write rows to CSV text with formula escaping and a UTF-8 byte-order mark."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for cells in rows:
        writer.writerow([_escape_csv(c) for c in cells])
    # Byte-order mark so Excel reads accented names correctly.
    return "\ufeff" + buffer.getvalue()


def _account_details(users):
    """Return ({user_pk: profile}, {user_pk: status}) for the members CSV, in a few queries.

    Status describes actual account access: "active" uses the same rule as
    the dashboard's Active members count and task assignment
    (tasks.models.eligible_assignees); otherwise suspended (including a
    suspension still being applied), pending (a membership approval still
    updating) or disabled (the account is switched off).
    """
    from accounts.models import Profile
    from membership.models import MembershipApplication
    from tasks.models import eligible_assignees

    users = list(users)
    ids = [u.pk for u in users]
    profiles = {p.user_id: p for p in Profile.objects.filter(user_id__in=ids)}
    active_ids = set(eligible_assignees().values_list("pk", flat=True))
    pending_ids = set(
        MembershipApplication.objects.filter(user_id__in=ids, access_update_pending=True)
        .values_list("user_id", flat=True)
    )
    statuses = {}
    for user in users:
        profile = profiles.get(user.pk)
        if user.pk in active_ids:
            statuses[user.pk] = "active"
        elif profile and (profile.is_suspended or profile.suspension_update_pending):
            statuses[user.pk] = "suspended"
        elif user.pk in pending_ids:
            statuses[user.pk] = "pending"
        elif not user.is_active:
            statuses[user.pk] = "disabled"
        else:
            statuses[user.pk] = "inactive"
    return profiles, statuses


def _events_rows(data):
    tz = timezone.get_current_timezone()
    yield ("Event", "Date", "Start time", "Location", "RSVPs going", "Attended")
    for item in data["per_event"]:
        event = item["event"]
        local_dt = event.starts_at.astimezone(tz)
        yield (
            event.title,
            local_dt.strftime("%Y-%m-%d"),
            local_dt.strftime("%H:%M"),
            event.location,
            item["rsvps_going"],
            item["attended"],
        )


def _member_name(user):
    return user.get_full_name() or user.username


def _members_rows(data):
    yield ("Member", "Email", "Role", "Status", "Attended", "Events held", "Attendance %",
           "Tasks assigned", "Tasks completed", "Tasks overdue")
    items = sorted(data["per_member"], key=lambda item: (_member_name(item["user"]).casefold(), item["user"].pk))
    profiles, statuses = _account_details(item["user"] for item in items)
    for item in items:
        user = item["user"]
        profile = profiles.get(user.pk)
        pct = item["attendance_pct"]
        yield (
            _member_name(user),
            user.email,
            "Admin" if user.is_superuser else (profile.get_role_display() if profile else ""),
            statuses[user.pk],
            item["attended"],
            item["events_held"],
            "" if pct is None else pct,
            item["tasks_assigned"],
            item["tasks_completed"],
            item["tasks_overdue"],
        )


def _committees_rows(data):
    yield ("Committee", "Members", "Attendance %", "Tasks total", "Tasks completed", "Tasks overdue")
    for item in data["per_committee"]:
        pct = item["attendance_pct"]
        yield (
            item["committee"].name,
            item["num_members"],
            "" if pct is None else pct,
            item["tasks_total"],
            item["tasks_completed"],
            item["tasks_overdue"],
        )


_ROW_BUILDERS = {"events": _events_rows, "members": _members_rows, "committees": _committees_rows}


def _csv_response(table, data):
    response = HttpResponse(_csv_text(_ROW_BUILDERS[table](data)), content_type="text/csv; charset=utf-8")
    filename = _report_filename(table, data["start_date"], data["end_date"])
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _zip_response(data):
    """All three report CSVs in one ZIP file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in REPORT_TABLES:
            archive.writestr(
                _report_filename(table, data["start_date"], data["end_date"]),
                _csv_text(_ROW_BUILDERS[table](data)).encode("utf-8"),
            )
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    filename = _report_filename("all", data["start_date"], data["end_date"], extension="zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(Role.OFFICER)
def report_download(request):
    """Download one report CSV, or all three as a ZIP, for the selected range.

    The `report` parameter is "all" (default), "events", "members" or
    "committees". An unknown choice or invalid date range returns HTTP 400.
    """
    choice = request.GET.get("report", "all")
    if choice != "all" and choice not in REPORT_TABLES:
        return HttpResponseBadRequest(
            "Choose all, events, members or committees.", content_type="text/plain; charset=utf-8"
        )
    data, error = _validate_csv_range(request)
    if error:
        return error
    return _zip_response(data) if choice == "all" else _csv_response(choice, data)


@role_required(Role.OFFICER)
def report_csv_events(request):
    """Events CSV: one row per event held in the range."""
    data, error = _validate_csv_range(request)
    return error or _csv_response("events", data)


@role_required(Role.OFFICER)
def report_csv_members(request):
    """Members CSV: one row per roster member, sorted by name, with account status."""
    data, error = _validate_csv_range(request)
    return error or _csv_response("members", data)


@role_required(Role.OFFICER)
def report_csv_committees(request):
    """Committees CSV: one row per committee."""
    data, error = _validate_csv_range(request)
    return error or _csv_response("committees", data)
