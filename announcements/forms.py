"""
@brief      Manage announcement attachments.

@citation   Google Stitch was used to help write this code.
"""

# === IMPORTS
from django import forms
from django.core.validators import URLValidator
from django.utils import timezone

from committees.models import Committee

from .models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementComment,
    Category,
    Resource,
)


# === [CLASS] ANNOUNCEMENT FORM
class AnnouncementForm(forms.ModelForm):
    """Manage announcement forms."""
    committee = forms.ModelChoiceField(
        queryset=Committee.objects.none(),
        required=False,
        label="Audience",
        empty_label="All members",
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label="Select a category",
    )
    scheduled_for = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": (
                    "w-full text-sm bg-white border"
                    " border-slate-200 rounded-lg"
                    " px-3 py-2 text-slate-800"
                    " focus:ring-2 focus:ring-slate-800"
                    " focus:outline-none"
                )
            }
        ),
        help_text=(
            "Optional: select a future date and time to automatically"
            " schedule release."
        )
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance.pk is None:
            self.initial["scheduled_for"] = ""
        if user is not None:
            self.fields["committee"].queryset = (
                Committee.objects.filter(members__user=user)
                | Committee.objects.filter(pk=self.instance.committee_id)
            ).distinct()

    class Meta:
        """Define the metadata."""
        model = Announcement
        fields = [
            "title",
            "category",
            "committee",
            "is_pinned",
            "is_urgent",
            "comments_enabled",
            "content",
            "scheduled_for",
            "meeting_location",
            "meeting_virtual_url",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": (
                        "e.g., Mandatory General Body Meeting #3:"
                        " Spring Budget Review"
                    ),
                    "class": (
                        "w-full text-base font-medium bg-white"
                        " border border-slate-200 rounded-lg"
                        " px-3.5 py-2.5 text-slate-900"
                        " placeholder:text-slate-400"
                        " focus:ring-2 focus:ring-slate-800"
                        " focus:outline-none"
                    )
                }
            ),
            "committee": forms.Select(
                attrs={
                    "class": (
                        "w-full text-sm bg-white border"
                        " border-slate-200 rounded-lg px-3 py-2"
                        " text-slate-800 focus:ring-2"
                        " focus:ring-slate-800 focus:outline-none"
                    )
                }
            ),
            "content": forms.Textarea(
                    attrs={
                        "rows": 6,
                        "placeholder": (
                            "Write announcement details,"
                            " agenda items, voting procedures,"
                            " or guidelines..."
                        ),
                        "class": (
                            "w-full text-sm bg-white border"
                            " border-slate-200 rounded-lg p-3.5"
                            " text-slate-800 placeholder:text-slate-400"
                            " focus:ring-2 focus:ring-slate-800"
                            " focus:outline-none"
                        )
                    }
                ),
            "meeting_location": forms.TextInput(
                attrs={
                    "placeholder": "e.g., Student Union Auditorium (Rm 204)",
                    "class": (
                        "w-full text-sm bg-white border border-slate-200"
                        " rounded-lg px-3 py-2 text-slate-800"
                        " placeholder:text-slate-400 focus:ring-2"
                        " focus:ring-slate-800 focus:outline-none"
                    )
                }
            ),
            "meeting_virtual_url": forms.URLInput(
                attrs={
                    "placeholder": "https://zoom.us/j/... or Google Meet URL",
                    "class": (
                        "w-full text-sm bg-white border border-slate-200"
                        " rounded-lg px-3 py-2 text-slate-800"
                        " placeholder:text-slate-400 focus:ring-2"
                        " focus:ring-slate-800 focus:outline-none"
                    )
                }
            ),
            "is_pinned": forms.CheckboxInput(
                attrs={
                    "class": (
                        "w-4 h-4 rounded text-slate-900 border-slate-300"
                        " focus:ring-slate-800"
                    )
                }
            ),
            "is_urgent": forms.CheckboxInput(
                attrs={
                    "class": (
                        "w-4 h-4 rounded text-amber-600 border-slate-300"
                        " focus:ring-amber-500"
                    )
                }
            ),
        }


    # === PUBLIC METHODS
    def clean(self):
        """Clean the announcement."""
        cleaned_data = super().clean()
        scheduled_for = cleaned_data.get("scheduled_for")

        if scheduled_for and scheduled_for <= timezone.now():
            self.add_error(
                "scheduled_for",
                "Choose a date and time in the future.",
            )

        return cleaned_data


class AnnouncementCommentForm(forms.ModelForm):
    """Validate a member or officer announcement comment."""

    class Meta:
        model = AnnouncementComment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write a comment...",
                    "class": (
                        "w-full text-sm bg-white border border-slate-200"
                        " rounded-lg p-3 text-slate-800"
                        " focus:ring-2 focus:ring-slate-800 focus:outline-none"
                    ),
                }
            )
        }


# === [CLASS] ANNOUNCEMENT ATTACHMENT FORM
class AnnouncementAttachmentForm(forms.ModelForm):
    """Manage announcement attachements."""

    class Meta:
        """Manage the form metadata."""
        model = AnnouncementAttachment
        fields = ["file", "name"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Document display name (e.g. Agenda PDF)"
                    ),
                    "class": (
                        "text-xs border border-slate-200"
                        " rounded px-2.5 py-1.5 w-full text-slate-800"
                    )
                }
            ),
            "file": forms.FileInput(
                attrs={
                    "class": (
                        "text-xs text-slate-500 file:mr-2 file:py-1"
                        " file:px-2.5 file:rounded-md file:border-0"
                        " file:text-xs file:font-semibold"
                        " file:bg-slate-100 file:text-slate-700"
                        " hover:file:bg-slate-200 cursor-pointer"
                    )
                }
            )
        }


class ResourceForm(forms.ModelForm):
    """Validate a resource backed by either a safe URL or uploaded file."""

    remove_file = forms.BooleanField(required=False)
    file = forms.FileField(
        required=False,
        widget=forms.FileInput,
    )
    url = forms.URLField(
        required=False,
        validators=[URLValidator(schemes=["http", "https"])],
    )

    class Meta:
        model = Resource
        fields = ["title", "description", "category", "file", "url"]

    def clean(self):
        cleaned_data = super().clean()
        file = self.files.get("file")
        url = cleaned_data.get("url")
        has_existing_file = bool(self.instance and self.instance.file)

        if file and cleaned_data.get("remove_file"):
            raise forms.ValidationError(
                "Choose either a replacement file or removal of the existing file."
            )
        if file and url:
            raise forms.ValidationError(
                "Choose either a file or a link, not both."
            )
        if not file and not url and not (
            has_existing_file and not cleaned_data.get("remove_file")
        ):
            raise forms.ValidationError("Provide either a file or a link.")
        if file:
            try:
                file_size = file.size
            except OSError:
                file_size = 0
            if file_size > 25 * 1024 * 1024:
                self.add_error("file", "Files must be 25 MB or smaller.")
        return cleaned_data

    def save(self, commit=True):
        resource = super().save(commit=False)
        if self.cleaned_data.get("remove_file") or self.cleaned_data.get("url"):
            resource.file = ""
        if commit:
            resource.save()
        return resource
