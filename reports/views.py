"""Participation and engagement reports for leadership (FR-6.2, FR-6.3; SCRUM-64)."""

import csv
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import Role, ROSTER_ROLES
from committees.models import Committee, CommitteeMember
from events.models import Attendance, Event, RSVP, RSVPResponse
from tasks.models import Task, TaskStatus

User = get_user_model()

# Characters that can trigger formula injection in spreadsheet software.
_FORMULA_TRIGGERS = ("=", "+", "-", "@")


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

    attended_by_user = {}
    for att in attendance_records:
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
        pct = round(attended / events_held * 100, 1) if events_held > 0 else None
        per_member.append({
            "user": user,
            "attended": attended,
            "events_held": events_held,
            "attendance_pct": pct,
            "tasks_assigned": task_assigned.get(uid, 0),
            "tasks_completed": task_completed.get(uid, 0),
            "tasks_overdue": task_overdue.get(uid, 0),
        })

    # --- Per-committee data ---
    committees = list(Committee.objects.all().order_by("name"))

    # Map committee_id -> set of member user_ids.
    committee_member_ids = {}
    for cm in CommitteeMember.objects.select_related("committee"):
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

        # Attendance %: sum of each member's attendance, divided by (members × events_held).
        if events_held > 0 and num_members > 0:
            total_possible = events_held * num_members
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


def _build_chart_data(data):
    """Serialize the report data into a JSON-safe dict for Chart.js (SCRUM-37).

    Returns None when there is no data to display (form invalid or no events/committees).
    """
    if data is None:
        return None

    per_event = [
        {
            "title": item["event"].title,
            "rsvps_going": item["rsvps_going"],
            "attended": item["attended"],
        }
        for item in data["per_event"]
    ]

    per_committee = [
        {
            "name": item["committee"].name,
            "attendance_pct": item["attendance_pct"] if item["attendance_pct"] is not None else 0,
            "has_events": item["attendance_pct"] is not None,
            "tasks_total": item["tasks_total"],
            "tasks_completed": item["tasks_completed"],
            "tasks_overdue": item["tasks_overdue"],
        }
        for item in data["per_committee"]
    ]

    if not per_event and not per_committee:
        return None

    return {"per_event": per_event, "per_committee": per_committee}


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

    chart_data = _build_chart_data(data)
    return render(request, "reports/report.html", {
        "form": form,
        "data": data,
        "chart_data": chart_data,
    })


@role_required(Role.OFFICER)
def report_csv(request):
    start_default, end_default = _default_dates()
    if request.GET.get("start_date") or request.GET.get("end_date"):
        form = DateRangeForm(request.GET)
    else:
        form = DateRangeForm({"start_date": start_default, "end_date": end_default})

    if not form.is_valid():
        # Never silently export a different range than the one requested.
        errors = "; ".join(str(e) for errs in form.errors.values() for e in errs)
        return HttpResponseBadRequest(
            f"Invalid date range: {errors}", content_type="text/plain; charset=utf-8"
        )

    start_date = form.cleaned_data["start_date"]
    end_date = form.cleaned_data["end_date"]
    data = _build_report(start_date, end_date)

    response = HttpResponse(content_type="text/csv")
    filename = f"participation_report_{start_date}_{end_date}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    def row(*cells):
        writer.writerow([_escape_csv(c) for c in cells])

    row("section", "name", "metric", "value")

    # Events section
    row("events", "summary", "events_held", data["events_held"])
    for item in data["per_event"]:
        name = item["event"].title
        row("event", name, "rsvps_going", item["rsvps_going"])
        row("event", name, "attended", item["attended"])

    # Per-member section
    for item in data["per_member"]:
        name = item["user"].get_full_name() or item["user"].username
        row("member", name, "attended", item["attended"])
        row("member", name, "events_held", item["events_held"])
        row("member", name, "attendance_pct", item["attendance_pct"] if item["attendance_pct"] is not None else "N/A")
        row("member", name, "tasks_assigned", item["tasks_assigned"])
        row("member", name, "tasks_completed", item["tasks_completed"])
        row("member", name, "tasks_overdue", item["tasks_overdue"])

    # Per-committee section
    for item in data["per_committee"]:
        name = item["committee"].name
        row("committee", name, "num_members", item["num_members"])
        row("committee", name, "attendance_pct", item["attendance_pct"] if item["attendance_pct"] is not None else "N/A")
        row("committee", name, "tasks_total", item["tasks_total"])
        row("committee", name, "tasks_completed", item["tasks_completed"])
        row("committee", name, "tasks_overdue", item["tasks_overdue"])

    return response
