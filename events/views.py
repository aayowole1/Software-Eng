from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROSTER_ROLES, Role, get_role, has_minimum_role

from .models import RSVP, Attendance, Event, RSVPResponse

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
    """Replace the attendance list with the roster members ticked on the form."""
    event = get_object_or_404(Event, pk=pk)
    if event.cancelled:
        messages.error(request, "Attendance can't be recorded for a cancelled event.")
        return redirect("events:detail", pk=event.pk)
    ticked = set(request.POST.getlist("attended"))
    roster = {str(u.pk): u for u in roster_users()}
    attended = {roster[uid] for uid in ticked if uid in roster}
    existing = {a.user_id: a for a in event.attendance.all()}

    for user in attended:
        if user.pk not in existing:
            Attendance.objects.create(event=event, user=user, marked_by=request.user)
    attended_ids = {u.pk for u in attended}
    for user_id, record in existing.items():
        if user_id not in attended_ids:
            record.delete()

    messages.success(request, f"Attendance saved: {len(attended)} attended.")
    return redirect("events:detail", pk=event.pk)
