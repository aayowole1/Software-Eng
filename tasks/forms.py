from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from committees.models import Committee

from .models import Task, TaskPriority, TaskStatus, can_manage_tasks, eligible_assignees


class AssignmentFieldsMixin:
    def _prepare_assignment_fields(self):
        self.fields["committee"].queryset = Committee.objects.all()
        self.fields["committee"].help_text = "Choose a committee to limit task visibility to its roster and officers."
        committee = getattr(self.instance, "committee", None) if hasattr(self, "instance") else None
        raw_committee = self.data.get(self.add_prefix("committee")) if self.is_bound else self.initial.get("committee")
        if raw_committee is not None:
            if isinstance(raw_committee, Committee):
                committee = raw_committee
            elif raw_committee:
                try:
                    committee = Committee.objects.filter(pk=raw_committee).first()
                except (ValueError, TypeError, ValidationError):
                    committee = None
            else:
                committee = None
        self.fields["assignee"].queryset = eligible_assignees(committee)
        self.fields["assignee"].label_from_instance = lambda user: user.email or user.username
        self.fields["assignee"].help_text = (
            "For a committee task, choose a current member of that committee. "
            "Leave unassigned to let a committee member claim it."
        )


class TaskForm(AssignmentFieldsMixin, forms.ModelForm):
    version = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)

    class Meta:
        model = Task
        fields = ["title", "description", "committee", "assignee", "due_date", "priority", "status"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, actor, *args, instance=None, **kwargs):
        self.actor = actor
        super().__init__(*args, instance=instance, **kwargs)
        if instance is not None and instance.pk:
            self.fields["version"].required = True
            self.initial["version"] = instance.version
        self._prepare_assignment_fields()

    def clean(self):
        cleaned = super().clean()
        if not can_manage_tasks(self.actor):
            raise forms.ValidationError("Only officers and admins can manage task details.")
        return cleaned


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=TaskStatus.choices)
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class TaskImportForm(AssignmentFieldsMixin, forms.Form):
    committee = forms.ModelChoiceField(queryset=Committee.objects.none(), required=False)
    assignee = forms.ModelChoiceField(queryset=get_user_model().objects.none(), required=False)
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    priority = forms.ChoiceField(choices=TaskPriority.choices, initial=TaskPriority.MEDIUM)

    def __init__(self, actor, *args, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        self._prepare_assignment_fields()

    def clean(self):
        cleaned = super().clean()
        if not can_manage_tasks(self.actor):
            raise forms.ValidationError("Only officers and admins can import meeting actions.")
        return cleaned
