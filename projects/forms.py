from django import forms
from django.contrib.auth.models import User
from .models import Project, Task


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'version', 'status', 'project_type', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Enter project title'
            }),
            'version': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.1.0'
            }),
            'status': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'project_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 4,
                'placeholder': 'Describe the project...'
            }),
        }


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'task_type', 'assignee', 'priority']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Task title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Task description...'
            }),
            'task_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'assignee': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'priority': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active users as assignee options
        self.fields['assignee'].queryset = User.objects.filter(is_active=True)
        self.fields['assignee'].required = False
        self.fields['assignee'].empty_label = "Unassigned"


class QuickTaskForm(forms.ModelForm):
    """Simplified form for quick-adding tasks"""
    class Meta:
        model = Task
        fields = ['title', 'task_type', 'priority']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-sm input-bordered w-full',
                'placeholder': 'New task...',
                'hx-trigger': 'keyup[key==Enter]'
            }),
            'task_type': forms.Select(attrs={
                'class': 'select select-sm select-bordered'
            }),
            'priority': forms.Select(attrs={
                'class': 'select select-sm select-bordered'
            }),
        }
