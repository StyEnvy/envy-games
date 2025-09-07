from django import forms
from django.db import models
from .models import TrackedProject, TrackedTask, TimeEntry
from .utils import parse_duration_to_minutes


class TimeEntryForm(forms.ModelForm):
    duration = forms.CharField(
        label="Duration",
        help_text="Minutes or H:MM (e.g., 90 or 1:30)",
        widget=forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "90 or 1:30"}),
    )

    class Meta:
        model = TimeEntry
        fields = ["project", "task", "work_date", "billable", "notes"]
        widgets = {
            "project": forms.Select(attrs={"class": "select select-bordered w-full", "id": "id_project"}),
            "task": forms.Select(attrs={"class": "select select-bordered w-full", "id": "id_task"}),
            "work_date": forms.DateInput(attrs={"type": "date", "class": "input input-bordered w-full"}),
            "billable": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes (what you worked on)…", "class": "textarea textarea-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Projects always ordered for usability
        self.fields["project"].queryset = TrackedProject.objects.order_by("title")

        # Prepopulate duration when editing
        if getattr(self.instance, "pk", None) and not self.is_bound:
            self.initial.setdefault("duration", self.instance.duration_minutes)

        def _to_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        project_id = None
        if self.is_bound:
            project_id = _to_int(self.data.get("project"))
        if project_id is None:
            project_id = _to_int(self.initial.get("project"))
        if project_id is None and getattr(self.instance, "pk", None):
            project_id = self.instance.project_id

        if project_id:
            qs = TrackedTask.objects.filter(project_id=project_id).order_by("title")
            # Ensure current task remains available when editing, even if inactive
            if getattr(self.instance, "pk", None) and self.instance.task_id:
                qs = TrackedTask.objects.filter(
                    models.Q(project_id=project_id) | models.Q(pk=self.instance.task_id)
                ).order_by("title")
            self.fields["task"].queryset = qs
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
