from django import forms
from .models import Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "type", "status", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "description": forms.Textarea(attrs={"class": "textarea textarea-bordered w-full min-h-32"}),
        }
        help_texts = {
            "name": "Unique project name; slug is generated automatically.",
        }
