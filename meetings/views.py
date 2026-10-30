from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import Role

from .models import REVIEW_DECISIONS, ActionItem, DraftStatus, MeetingDraft
from .stt import DeepgramTranscriber


_active_recordings = {}

# Meeting notes can contain sensitive organization information, so only
# officers and admins can see them (proposal section 2.4, limitation).


class MeetingNotesForm(forms.ModelForm):
    class Meta:
        model = MeetingDraft
        fields = ["title", "transcript", "notes"]
        labels = {"transcript": "Transcript", "notes": "Officer notes"}
        help_texts = {
            "notes": "Add context, corrections, or other notes for the summarizer.",
        }
        widgets = {
            "title": forms.TextInput(attrs={"style": "width: 100%; max-width: none;"}),
            "transcript": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={"rows": 6}),
        }


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decision",
        # No default: the reviewer must pick a decision deliberately.
        choices=[("", "Choose a decision…")] + [(d.value, d.label) for d in REVIEW_DECISIONS],
    )
    note = forms.CharField(label="Note (optional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    new_items = forms.CharField(
        label="Add action items (one per line)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


@role_required(Role.OFFICER)
def draft_list(request):
    return render(request, "meetings/draft_list.html", {"drafts": MeetingDraft.objects.all()})


@role_required(Role.OFFICER)
def draft_create(request):
    form = MeetingNotesForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        draft = form.save(commit=False)
        draft.created_by = request.user

        if not draft.title:
            draft.title = f"{timezone.now():%d %B, %Y} - Untitled Transcript"

        try:
            with transaction.atomic():
                draft.save()
                draft.generate()
        except (RuntimeError, ValueError) as error:
            messages.error(request, f"Could not generate the meeting summary: {error}")
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": "New meeting notes"},
            )
        messages.success(request, "Meeting submitted for review.")
        form = MeetingNotesForm(instance=draft)
    return render(request, "meetings/draft_form.html", {"form": form, "heading": "New meeting notes"})


@require_POST
@role_required(Role.OFFICER)
def transcribe_chunk(request):
    """Accept one browser PCM chunk and return the current transcript."""
    recording_id = request.headers.get("X-Recording-ID", "").strip()
    if not recording_id or len(recording_id) > 64:
        return JsonResponse({"error": "A valid recording ID is required."}, status=400)

    key = (request.user.pk, recording_id)
    transcriber = _active_recordings.get(key)
    if transcriber is None:
        try:
            transcriber = DeepgramTranscriber()
        except (FileNotFoundError, ImportError, OSError, RuntimeError) as error:
            return JsonResponse({"error": str(error)}, status=503)
        _active_recordings[key] = transcriber

    try:
        transcript = (
            transcriber.add_pcm(request.body)
            if request.body
            else transcriber.current_result()
        )
        if request.headers.get("X-Recording-Final") == "true":
            transcript = transcriber.finish()
            _active_recordings.pop(key, None)
    except (OSError, ValueError, RuntimeError) as error:
        transcriber.discard()
        _active_recordings.pop(key, None)
        return JsonResponse({"error": str(error)}, status=400)

    return JsonResponse({"transcript": transcript})


@role_required(Role.OFFICER)
def draft_detail(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    return render(
        request,
        "meetings/draft_detail.html",
        {
            "draft": draft,
            "items": draft.action_items.all(),
            "review_form": ReviewForm(),
            "can_review": draft.status == DraftStatus.PENDING_REVIEW,
            "can_revise": draft.status == DraftStatus.REVISION_REQUESTED,
        },
    )


@require_POST
@role_required(Role.OFFICER)
def draft_review(request, pk):
    """Record a decision. Reviewers can edit, untick, or add action items first (FR-12)."""
    draft = get_object_or_404(MeetingDraft, pk=pk)
    form = ReviewForm(request.POST)
    if draft.status != DraftStatus.PENDING_REVIEW:
        messages.error(request, "This draft is not pending review.")
        return redirect("meetings:detail", pk=draft.pk)
    if not form.is_valid():
        messages.error(request, "Choose a valid decision.")
        return redirect("meetings:detail", pk=draft.pk)

    for item in draft.action_items.all():
        text = request.POST.get(f"item-{item.pk}-description", item.description).strip()
        item.accepted = bool(text) and request.POST.get(f"item-{item.pk}-accepted") == "on"
        item.description = text or item.description
        item.save()
    next_position = draft.action_items.count()
    for offset, line in enumerate(l.strip() for l in form.cleaned_data["new_items"].splitlines() if l.strip()):
        ActionItem.objects.create(draft=draft, description=line, position=next_position + offset)

    draft.review(request.user, form.cleaned_data["decision"], form.cleaned_data["note"])
    messages.success(request, f"Draft marked {draft.get_status_display().lower()}.")
    return redirect("meetings:detail", pk=draft.pk)


@role_required(Role.OFFICER)
def draft_revise(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    if draft.status != DraftStatus.REVISION_REQUESTED:
        messages.error(request, "Only drafts with a revision request can be revised.")
        return redirect("meetings:detail", pk=draft.pk)
    form = MeetingNotesForm(request.POST or None, instance=draft)
    if request.method == "POST" and form.is_valid():
        draft.title = form.cleaned_data["title"]
        try:
            with transaction.atomic():
                draft.revise(form.cleaned_data["notes"], form.cleaned_data["transcript"])
        except (RuntimeError, ValueError) as error:
            messages.error(request, f"Could not generate the meeting summary: {error}")
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": f"Revise “{draft.title}”"},
            )
        messages.success(request, "Notes revised and AI draft regenerated.")
        return redirect("meetings:detail", pk=draft.pk)
    return render(request, "meetings/draft_form.html", {"form": form, "heading": f"Revise “{draft.title}”"})


@require_POST
@role_required(Role.ADMIN)
def draft_delete(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    draft.action_items.all().delete()
    draft.delete()
    messages.success(request, f"Draft “{draft.title}” deleted.")
    return redirect("meetings:list")
