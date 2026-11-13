from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Role, get_role, has_minimum_role

from .models import (
    RSVP, Attendance, AttendanceAction, AttendanceAuditLog, AttendanceAuditStatus, Event, RSVPResponse,
)

User = get_user_model()

DATETIME_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "starts_at", "ends_at", "location", "description"]
        labels = {"starts_at": "Starts", "ends_at": "Ends (optional)"}
        widgets = {
            "starts_at": DATETIME_WIDGET,
            "ends_at": DATETIME_WIDGET,
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "The end time must be after the start time.")
        return cleaned


def roster_users():
    return User.objects.filter(profile__role__in=ROSTER_ROLES).order_by("username")


@role_required(Role.MEMBER)
def event_list(request):
    now = timezone.now()
    events = Event.objects.all()
    my_rsvps = dict(
        RSVP.objects.filter(user=request.user).values_list("event_id", "response")
    )
    upcoming = [(e, my_rsvps.get(e.pk)) for e in events.filter(starts_at__gte=now)]
    past = list(events.filter(starts_at__lt=now).order_by("-starts_at"))
    return render(request, "events/event_list.html", {"upcoming": upcoming, "past": past})


@role_required(Role.OFFICER)
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        event.save()
        messages.success(request, f"Event “{event.title}” created.")
        return redirect("events:detail", pk=event.pk)
    return render(
        request,
        "events/event_form.html",
        {"form": form, "heading": "New event", "editing": False},
    )


@role_required(Role.OFFICER)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Event updated.")
        return redirect("events:detail", pk=event.pk)
    return render(
        request,
        "events/event_form.html",
        {"form": form, "heading": f"Edit “{event.title}”", "editing": True, "event": event},
    )


@require_POST
@role_required(Role.OFFICER)
def event_cancel(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.is_upcoming:
        messages.error(request, "Only upcoming events can be cancelled.")
        return redirect("events:detail", pk=event.pk)
    event.cancelled = True
    event.save(update_fields=["cancelled"])
    messages.success(request, f"Event “{event.title}” cancelled.")
    return redirect("events:detail", pk=event.pk)


@role_required(Role.MEMBER)
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    my_rsvp = RSVP.objects.filter(event=event, user=request.user).first()
    rsvps = event.rsvps.select_related("user").order_by("user__username")
    context = {
        "event": event,
        "my_rsvp": my_rsvp,
        "going_count": rsvps.filter(response=RSVPResponse.GOING).count(),
        "not_going_count": rsvps.filter(response=RSVPResponse.NOT_GOING).count(),
        "attended_count": event.attendance.count(),
    }
    if has_minimum_role(get_role(request.user), Role.OFFICER):
        attended_ids = set(event.attendance.values_list("user_id", flat=True))
        responses = {r.user_id: r.get_response_display() for r in rsvps}
        context["rsvps"] = rsvps
        context["attendance_rows"] = [
            (u, u.pk in attended_ids, responses.get(u.pk, "No response")) for u in roster_users()
        ]
    return render(request, "events/event_detail.html", context)


@require_POST
@role_required(Role.MEMBER)
def event_rsvp(request, pk):
    event = get_object_or_404(Event, pk=pk)
    response = request.POST.get("response")
    if response not in RSVPResponse.values:
        messages.error(request, "Choose going or not going.")
    elif not event.accepts_rsvps:
        messages.error(request, "This event is no longer taking RSVPs.")
    else:
        RSVP.objects.update_or_create(event=event, user=request.user, defaults={"response": response})
        messages.success(request, f"RSVP saved: {RSVPResponse(response).label}.")
    return redirect("events:detail", pk=event.pk)


def _ensure_mark_entry(event, attendance):
    """Write the completed "marked present" entry for an Attendance record if it is missing.

    The entry credits the officer who originally marked the member
    (Attendance.marked_by) at the original time (Attendance.marked_at), so a
    repair on a later save never credits the officer who happens to retry.
    """
    AttendanceAuditLog.objects.get_or_create(
        change_key=f"mark:{attendance.pk}",
        defaults={
            "event": event,
            "user_id": attendance.user_id,
            "action": AttendanceAction.MARKED,
            "actor_id": attendance.marked_by_id,
            "at": attendance.marked_at,
            "status": AttendanceAuditStatus.COMPLETED,
        },
    )


@require_POST
@role_required(Role.OFFICER)
def event_attendance(request, pk):
    """Replace the attendance list with the roster members ticked on the form.

    Attendance and its audit entries are separate MongoDB documents, so each
    change is written in steps that are safe to retry after a partial write.
    A stable change_key anchored to the Attendance PK keeps retries from
    duplicating entries:

    Mark:   get_or_create Attendance (stable PK), then get_or_create the
            completed audit entry. A repaired entry credits the original
            Attendance.marked_by at Attendance.marked_at, not the officer
            who retried.
    Unmark: first restore the mark entry if an earlier save failed to write
            it, then get_or_create a *pending* audit entry, delete the
            Attendance record, and mark the entry completed.

    Pending removals left by an interrupted save are resolved first: if the
    Attendance record is gone, the delete happened and the entry is completed;
    if the record still exists and the member is now ticked again, the removal
    never happened and the pending entry is discarded.
    """
    event = get_object_or_404(Event, pk=pk)
    if event.cancelled:
        messages.error(request, "Attendance can't be recorded for a cancelled event.")
        return redirect("events:detail", pk=event.pk)
    ticked = set(request.POST.getlist("attended"))
    roster = {str(u.pk): u for u in roster_users()}
    attended = {roster[uid] for uid in ticked if uid in roster}
    attended_ids = {u.pk for u in attended}
    existing = {a.user_id: a for a in event.attendance.all()}
    existing_pks = {str(a.pk) for a in existing.values()}

    # Resolve pending removals from an earlier save that did not finish.
    pending_removals = AttendanceAuditLog.objects.filter(
        event=event, action=AttendanceAction.UNMARKED, status=AttendanceAuditStatus.PENDING,
    )
    for log in pending_removals:
        attendance_pk = (log.change_key or "").partition(":")[2]
        if attendance_pk not in existing_pks:
            # The Attendance record was deleted; only the status update failed.
            log.status = AttendanceAuditStatus.COMPLETED
            log.save(update_fields=["status"])
        elif log.user_id in attended_ids:
            # The delete never happened and the member is being kept present.
            log.delete()
        # Otherwise the member is still being removed; the loop below finishes it.

    for user in attended:
        attendance = existing.get(user.pk)
        if attendance is None:
            attendance, _ = Attendance.objects.get_or_create(
                event=event, user=user, defaults={"marked_by": request.user}
            )
        # Runs for existing records too, so a retry can repair a missing entry.
        _ensure_mark_entry(event, attendance)

    for user_id, record in existing.items():
        if user_id in attended_ids:
            continue
        # Restore a missing "marked present" entry before recording the removal,
        # so unchecking a member never loses the original mark from the history.
        _ensure_mark_entry(event, record)
        log, _ = AttendanceAuditLog.objects.get_or_create(
            change_key=f"unmark:{record.pk}",
            defaults={
                "event": event,
                "user_id": user_id,
                "action": AttendanceAction.UNMARKED,
                "actor": request.user,
                "status": AttendanceAuditStatus.PENDING,
            },
        )
        record.delete()
        if log.status != AttendanceAuditStatus.COMPLETED:
            log.status = AttendanceAuditStatus.COMPLETED
            log.save(update_fields=["status"])

    messages.success(request, f"Attendance saved: {len(attended)} attended.")
    return redirect("events:detail", pk=event.pk)
