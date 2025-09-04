from typing import Optional
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from .models import Task, Label
from projects.models import Project

UserModel = get_user_model()

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = (
            "title",
            "kind",
            "status",
            "priority",
            "assignee",
            "impact",
            "confidence",
            "ease",
            "parent",
            "labels",
            "description",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "labels": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, project: Optional[Project] = None, user: Optional[AbstractBaseUser] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.user = user

        # Limit assignee to active users
        self.fields["assignee"].queryset = UserModel.objects.filter(is_active=True).order_by("username")

        # Scope M2M and parent to the current project
        if project is not None:
            self.fields["labels"].queryset = Label.objects.filter(project=project).order_by("name")
            qs = Task.objects.filter(project=project).exclude(pk=self.instance.pk).order_by("title")
            self.fields["parent"].queryset = qs

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        if kind == "task":
            if not cleaned.get("status"):
                self.add_error("status", "Status is required for Task items.")
            if cleaned.get("priority") is None:
                self.add_error("priority", "Priority is required for Task items.")
        if kind in {"idea", "epic"}:
            for fld in ("impact", "confidence", "ease"):
                if cleaned.get(fld) is None:
                    self.add_error(fld, "Required for Idea/Epic.")
        return cleaned
