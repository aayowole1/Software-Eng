"""
@brief      Manage announcement attachments.

@citation   Google Stitch was used to help write this code.
"""

# === IMPORTS
from django import forms

from .models import Announcement, AnnouncementAttachment, Category

# === [CLASS] ANNOUNCEMENT FORM
class AnnouncementForm(forms.ModelForm):
    """Manage announcement forms."""
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

    class Meta:
        """Define the metadata."""
        model = Announcement
        fields = [
            "title",
            "category",
            "status",
            "is_pinned",
            "is_urgent",
            "content",
            "scheduled_for",
            "meeting_location",
            "meeting_virtual_url",
            "target_reach",
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
            "category": forms.Select(
                attrs={
                    "class": (
                        "w-full text-sm bg-white border"
                        " border-slate-200 rounded-lg px-3 py-2"
                        " text-slate-800 focus:ring-2"
                        " focus:ring-slate-800 focus:outline-none"
                    )
                }
            ),
            "status": forms.Select(
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
            "target_reach": forms.NumberInput(
                attrs={
                    "class": (
                        "w-32 text-sm bg-white border border-slate-200"
                        " rounded-lg px-3 py-2 text-slate-800 focus:ring-2"
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
        status = cleaned_data.get("status")
        scheduled_for = cleaned_data.get("scheduled_for")

        if status == "scheduled" and not scheduled_for:
            self.add_error(
                "scheduled_for",
                "You must specify a date and time for scheduled announcements.",
            )

        return cleaned_data


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
