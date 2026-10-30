import logging

from bson import ObjectId
from django import forms
from django.contrib import messages
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import Role

from .models import REVIEW_DECISIONS, ActionItem, DraftStatus, MeetingDraft, MeetingReviewConflict
from .stt import DeepgramTranscriber


_active_recordings = {}
logger = logging.getLogger(__name__)

# Meeting notes can contain sensitive organization information, so only
# officers and admins can see them (proposal section 2.4, limitation).


class MeetingNotesForm(forms.ModelForm):
    expected_generation = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)

    class Meta:
        model = MeetingDraft
        fields = ["title", "notes"]
        labels = {"notes": "Meeting notes"}
        help_texts = {
            "notes": 'Put action items on their own line starting with "Action:", "TODO:" or "- [ ]".',
        }
        widgets = {
            "title": forms.TextInput(attrs={"style": "width: 100%; max-width: none;"}),
            "notes": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["expected_generation"] = self.instance.generation_token or ""


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
    form = MeetingNotesForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        draft = form.save(commit=False)
        draft.created_by = request.user
        # Reserve this attempt's ID before any write. Provider generation runs
        # before the insert, and force_insert cannot update an existing draft.
        draft.pk = ObjectId()

        if not draft.title:
            draft.title = f"{timezone.now():%d %B, %Y} - Untitled Transcript"

        try:
            draft.generate(force_insert=True)
        except (RuntimeError, ValueError, DatabaseError):
            if _cleanup_created_draft(draft):
                message = "The meeting could not be created. No new draft was retained. Please try submitting again."
            else:
                message = (
                    "The meeting's creation could not be confirmed. Review Meeting drafts before retrying. "
                    "A completed draft or unpublished action data may remain; ask an officer for help if needed."
                )
            messages.error(request, message)
            return render(
                request,
                "meetings/draft_form.html",
                {"form": form, "heading": "New meeting notes"},
                status=503,
            )
        messages.success(request, "Meeting created.")
        return redirect("meetings:detail", pk=draft.pk)
    return render(request, "meetings/draft_form.html", {"form": form, "heading": "New meeting notes"})


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
            "items": draft.current_action_items,
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
        draft.review(
            request.user, form.cleaned_data["decision"], form.cleaned_data["note"],
            item_intent=item_intent, expected_generation=form.cleaned_data["expected_generation"],
        )
    except MeetingReviewConflict:
        messages.error(
            request,
            "The meeting status changed during review. Reload the draft before trying again. "
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
    return redirect("meetings:detail", pk=draft.pk)


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
                form.cleaned_data["notes"], title=form.cleaned_data["title"],
                expected_generation=form.cleaned_data["expected_generation"],
            )
        except MeetingReviewConflict:
            messages.error(request, "This meeting changed during revision. Reload it before trying again.")
            return redirect("meetings:detail", pk=draft.pk)
        except (RuntimeError, ValueError, DatabaseError):
            messages.error(
                request,
                "The revised generation could not be confirmed. Reload the meeting before retrying. "
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
