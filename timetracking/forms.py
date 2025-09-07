from django import forms
from django.contrib.auth import get_user_model

from .models import TrackedProject, TrackedTask, TimeEntry
from .utils import parse_duration_to_minutes


class TrackedProjectForm(forms.ModelForm):
    class Meta:
        model = TrackedProject
        fields = ["title", "is_active", "external_ref"]


class TrackedTaskForm(forms.ModelForm):
    class Meta:
        model = TrackedTask
        fields = ["project", "title", "is_active", "external_ref"]


class TimeEntryForm(forms.ModelForm):
    duration = forms.CharField(
        label="Duration",
        help_text="Minutes or H:MM (e.g., 90 or 1:30)",
    )

    class Meta:
        model = TimeEntry
        fields = ["project", "task", "work_date", "billable", "notes"]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.TextInput(attrs={"maxlength": 255}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit tasks by selected/initial project (basic cascading behavior)
        project = None
        data = kwargs.get("data")
        if data and data.get("project"):
            project = data.get("project")
        elif self.instance and self.instance.pk:
            project = self.instance.project_id
        if project:
            self.fields["task"].queryset = TrackedTask.objects.filter(project_id=project)
        else:
            self.fields["task"].queryset = TrackedTask.objects.none()

    def clean_duration(self):
        value = self.cleaned_data.get("duration")
        try:
            minutes = parse_duration_to_minutes(value)
        except Exception:
            raise forms.ValidationError("Invalid duration format.")
        if minutes <= 0:
            raise forms.ValidationError("Duration must be greater than zero.")
        return minutes

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get("project")
        task = cleaned.get("task")
        if task and project and task.project_id != project.id:
            self.add_error("task", "Selected task does not belong to this project.")
        return cleaned

    def save(self, commit=True):
        obj: TimeEntry = super().save(commit=False)
        obj.duration_minutes = self.cleaned_data["duration"]
        if commit:
            obj.save()
        return obj