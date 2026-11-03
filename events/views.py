from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Role, get_role, has_minimum_role

from .models import RSVP, Attendance, AttendanceAction, AttendanceAuditLog, Event, RSVPResponse

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
    return render(request, "events/event_form.html", {"form": form, "heading": "New event"})


@role_required(Role.OFFICER)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Event updated.")
        return redirect("events:detail", pk=event.pk)
    return render(request, "events/event_form.html", {"form": form, "heading": f"Edit “{event.title}”"})


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


@require_POST
@role_required(Role.OFFICER)
def event_attendance(request, pk):
    """Replace the attendance list with the roster members ticked on the form.

    Each change is written in two steps with a stable change_key so that a
    partial write (one step succeeds, the other fails) is safe to retry:

    Mark:   get_or_create Attendance (stable PK) → get_or_create audit log
    Unmark: get_or_create audit log first         → then delete Attendance

    Because both writes use the same Attendance PK as the idempotency anchor,
    retrying after either step failed produces exactly one audit entry and one
    attendance change with no duplicates.
    """
    event = get_object_or_404(Event, pk=pk)
    if event.cancelled:
        messages.error(request, "Attendance can't be recorded for a cancelled event.")
        return redirect("events:detail", pk=event.pk)
    ticked = set(request.POST.getlist("attended"))
    roster = {str(u.pk): u for u in roster_users()}
    attended = {roster[uid] for uid in ticked if uid in roster}
    existing = {a.user_id: a for a in event.attendance.all()}

    attended_ids = {u.pk for u in attended}

    for user in attended:
        if user.pk not in existing:
            # Step 1: ensure the Attendance record exists and get its stable PK.
            attendance, _ = Attendance.objects.get_or_create(
                event=event, user=user, defaults={"marked_by": request.user}
            )
            # Step 2: write the audit entry, idempotent via change_key.
            # If step 1 succeeded but step 2 failed on a prior attempt, the
            # same Attendance PK is returned by get_or_create, so the same
            # change_key is used and get_or_create finds the existing entry.
            AttendanceAuditLog.objects.get_or_create(
                change_key=f"mark:{attendance.pk}",
                defaults={
                    "event": event,
                    "user": user,
                    "action": AttendanceAction.MARKED,
                    "actor": request.user,
                },
            )

    for user_id, record in existing.items():
        if user_id not in attended_ids:
            # Step 1: write the audit entry before deleting so that a retry
            # (when the delete succeeded but the audit write failed) still has
            # the Attendance PK available to form the same change_key.
            AttendanceAuditLog.objects.get_or_create(
                change_key=f"unmark:{record.pk}",
                defaults={
                    "event": event,
                    "user_id": user_id,
                    "action": AttendanceAction.UNMARKED,
                    "actor": request.user,
                },
            )
            # Step 2: delete after the audit entry is safely persisted.
            record.delete()

    messages.success(request, f"Attendance saved: {len(attended)} attended.")
    return redirect("events:detail", pk=event.pk)
