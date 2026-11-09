import logging

from bson import ObjectId
from django import forms
from django.contrib import messages
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import Role

from .models import REVIEW_DECISIONS, ActionItem, DraftStatus, MeetingDraft, MeetingReviewConflict
from .stt import DeepgramTranscriber


_active_recordings = {}
logger = logging.getLogger(__name__)


def _action_item_parts(description):
    parts = {}
    current_key = None
    for segment in description.removeprefix("Action:").strip().split(";"):
        key, separator, value = segment.partition("=")
        key = key.strip().lower()
        if separator and key in {"owner", "task", "due", "priority"}:
            current_key = key
            parts[key] = value.strip()
        elif current_key is not None:
            parts[current_key] += ";" + segment
    return {key: value.strip() for key, value in parts.items()}

# Meeting notes can contain sensitive organization information, so only
# officers and admins can see them (proposal section 2.4, limitation).


class MeetingNotesForm(forms.ModelForm):
    expected_generation = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)

    class Meta:
        model = MeetingDraft
        fields = ["title", "transcript", "notes"]
        labels = {"transcript": "Transcript", "notes": "Officer notes"}
        help_texts = {
            "notes": "Add context, corrections, or other notes for the summarizer.",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={"style": "width: 100%; max-width: none;", "placeholder": "Enter Title Here"}
            ),
            "transcript": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={"rows": 6, "placeholder": "Add Notes Here"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.initial["expected_generation"] = self.instance.generation_token or ""

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("notes", "").strip() and not cleaned_data.get("transcript", "").strip():
            raise forms.ValidationError("Add officer notes or record audio before submitting.")
        return cleaned_data


class ReviewForm(forms.Form):
    expected_generation = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)
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
    initial = request.session.get("meeting_processing") if request.method == "GET" else None
    form = MeetingNotesForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        draft = form.save(commit=False)
        draft.created_by = request.user
        draft.pk = ObjectId()
        if not draft.title:
            draft.title = f"{timezone.now():%d %B, %Y} - Untitled Notes"
        try:
            draft.generate(force_insert=True)
        except (RuntimeError, ValueError, DatabaseError):
            try:
                published = MeetingDraft.objects.filter(
                    pk=draft.pk,
                    created_by=request.user,
                    generation_token=draft.generation_token,
                ).first()
            except DatabaseError:
                published = None
            if published is not None:
                messages.warning(request, "The notes were saved, but confirmation was delayed. Review the draft below.")
                return redirect("meetings:detail", pk=published.pk)
            if _cleanup_created_draft(draft):
                message = "The notes could not be created. No new draft was retained. Please try submitting again."
            else:
                message = (
                    "The notes' creation could not be confirmed. Review Notes drafts before retrying. "
                    "A completed draft or unpublished action data may remain; ask an officer for help if needed."
                )
            messages.error(request, message)
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": "Take notes"},
                status=503,
            )
        messages.success(request, "Notes created.")
        return redirect("meetings:detail", pk=draft.pk)
    return render(request, "meetings/draft_form.html", {"form": form, "heading": "Take notes"})


def _create_draft(user, data):
    draft = MeetingDraft(
        title=data.get("title", ""),
        transcript=data.get("transcript", ""),
        notes=data.get("notes", ""),
        created_by=user,
        pk=ObjectId(),
    )
    if not draft.title:
        draft.title = f"{timezone.now():%d %B, %Y} - Untitled Notes"
    try:
        draft.generate(force_insert=True)
    except (RuntimeError, ValueError, DatabaseError):
        _cleanup_created_draft(draft)
        raise
    return draft


@role_required(Role.OFFICER)
def meeting_processing(request):
    if request.method == "POST":
        form = MeetingNotesForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": "Take notes"},
                status=400,
            )
        request.session["meeting_processing"] = {
            "title": form.cleaned_data["title"],
            "transcript": form.cleaned_data["transcript"],
            "notes": form.cleaned_data["notes"],
        }
        request.session.save()
        return redirect("meetings:processing")
    return redirect("meetings:create")


@role_required(Role.OFFICER)
def meeting_processing_page(request):
    if "meeting_processing" not in request.session:
        return redirect("meetings:create")
    return render(request, "meetings/processing.html")


@require_POST
@role_required(Role.OFFICER)
def meeting_process(request):
    data = request.session.get("meeting_processing")
    if not data:
        return JsonResponse({"error": "This notes processing request has expired."}, status=400)
    if not data.get("transcript", "").strip() and not data.get("notes", "").strip():
        return JsonResponse(
            {"error": "No audio was found. Record audio or add officer notes before submitting."},
            status=422,
        )
    try:
        draft = _create_draft(request.user, data)
    except (RuntimeError, ValueError, DatabaseError):
        return JsonResponse({"error": "The notes could not be processed. Please return and try again."}, status=503)
    del request.session["meeting_processing"]
    request.session.save()
    return JsonResponse({"redirect": reverse("meetings:detail", args=[draft.pk])})


def _cleanup_created_draft(draft):
    """Clean exact unpublished action staging; never delete a visible draft."""
    cleaned = draft.cleanup_unpublished_generation()
    if not cleaned:
        logger.error("Meeting creation cleanup could not be confirmed; operator recovery is required.")
    return cleaned


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
    except ValueError as error:
        transcriber.discard()
        _active_recordings.pop(key, None)
        return JsonResponse({"error": str(error)}, status=400)
    except (OSError, RuntimeError) as error:
        transcriber.discard()
        _active_recordings.pop(key, None)
        return JsonResponse({"error": str(error)}, status=503)

    return JsonResponse({"transcript": transcript})


@role_required(Role.OFFICER)
def draft_detail(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    return render(
        request,
        "meetings/draft_detail.html",
        {
            "draft": draft,
            "items": draft.current_action_items,
            "review_items": [
                {"item": item, "parts": _action_item_parts(item.description)}
                for item in draft.current_action_items
            ],
            "review_form": ReviewForm(initial={"expected_generation": draft.generation_token or ""}),
            "can_review": draft.status == DraftStatus.PENDING_REVIEW and not draft.review_update_pending,
            "can_revise": draft.status == DraftStatus.REVISION_REQUESTED and not draft.review_update_pending,
            "can_finish_review": draft.review_update_pending,
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

    item_intent = []
    for item in draft.current_action_items:
        text = request.POST.get(f"item-{item.pk}-description", item.description).strip()
        item_intent.append({
            "id": str(item.pk), "description": text or item.description,
            "accepted": bool(text) and request.POST.get(f"item-{item.pk}-accepted") == "on",
        })
    for line in (line.strip() for line in form.cleaned_data["new_items"].splitlines() if line.strip()):
        item_intent.append({"id": str(ObjectId()), "description": line, "accepted": True})

    try:
        draft.notes = request.POST.get("notes", draft.notes)
        draft.save(update_fields=["notes"])
        draft.review(
            request.user, form.cleaned_data["decision"], form.cleaned_data["note"],
            item_intent=item_intent, expected_generation=form.cleaned_data["expected_generation"],
        )
    except MeetingReviewConflict:
        messages.error(
            request,
            "The notes status changed during review. Reload the draft before trying again. "
            "No action-item changes from this review were saved.",
        )
        return redirect("meetings:detail", pk=draft.pk)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("meetings:detail", pk=draft.pk)
    except DatabaseError:
        messages.error(
            request,
            "The review could not be confirmed complete. Reload the draft and use Finish review "
            "if action updates are unfinished. Task conversion stays unavailable until they finish.",
        )
        return redirect("meetings:detail", pk=draft.pk)
    messages.success(request, f"Draft marked {draft.get_status_display().lower()}.")
    return redirect("meetings:list")


@require_POST
@role_required(Role.OFFICER)
def draft_finish_review(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    try:
        draft.complete_review_update()
    except ValueError as error:
        messages.error(request, str(error))
    except DatabaseError:
        messages.error(
            request,
            "The saved review could not be confirmed complete. Reload the draft and retry "
            "Finish review if action updates are still unfinished.",
        )
    else:
        messages.success(request, "The saved review's action updates are complete.")
    return redirect("meetings:detail", pk=draft.pk)


@role_required(Role.OFFICER)
def draft_revise(request, pk):
    draft = get_object_or_404(MeetingDraft, pk=pk)
    if draft.status != DraftStatus.REVISION_REQUESTED:
        messages.error(request, "Only drafts with a revision request can be revised.")
        return redirect("meetings:detail", pk=draft.pk)
    if draft.review_update_pending:
        messages.error(request, "Finish the recorded action-item review before revising notes.")
        return redirect("meetings:detail", pk=draft.pk)
    form = MeetingNotesForm(request.POST or None, instance=draft)
    if request.method == "POST" and form.is_valid():
        try:
            draft.revise(
                form.cleaned_data["notes"], transcript=form.cleaned_data["transcript"],
                title=form.cleaned_data["title"] or form.initial["title"],
                expected_generation=form.cleaned_data["expected_generation"],
            )
        except MeetingReviewConflict:
            messages.error(request, "These notes changed during revision. Reload them before trying again.")
            return redirect("meetings:detail", pk=draft.pk)
        except (RuntimeError, ValueError, DatabaseError):
            messages.error(
                request,
                "The revised generation could not be confirmed. Reload the notes before retrying. "
                "The published action set has not been removed.",
            )
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": f"Revise “{draft.title}”"},
                status=503,
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
