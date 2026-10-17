from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import Role

from .models import REVIEW_DECISIONS, ActionItem, DraftStatus, MeetingDraft

# Meeting notes can contain sensitive organization information, so only
# officers and admins can see them (proposal section 2.4, limitation).


class MeetingNotesForm(forms.ModelForm):
    class Meta:
        model = MeetingDraft
        fields = ["title", "notes"]
        labels = {"notes": "Meeting notes"}
        help_texts = {
            "notes": 'Put action items on their own line starting with "Action:", "TODO:" or "- [ ]".',
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 12})}
        required = {"title": False, "notes": False}


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
        draft.save()
        draft.generate()
        messages.success(request, "AI draft generated. Review it before anything is saved as a task.")
        return redirect("meetings:detail", pk=draft.pk)
    return render(request, "meetings/draft_form.html", {"form": form, "heading": "New meeting notes"})


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
        draft.revise(form.cleaned_data["notes"])
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
