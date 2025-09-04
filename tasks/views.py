from typing import Any, Dict
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Task
from .forms import TaskForm
from projects.models import Project

class ProjectScopedMixin(LoginRequiredMixin):
    project: Project

    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get("project_slug")
        if slug:
            self.project = get_object_or_404(Project.objects.select_related("owner"), slug=slug)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if hasattr(self, "project"):
            ctx["project"] = self.project
        return ctx


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 20

    def get_queryset(self):
        return (
            Task.objects.select_related("project", "assignee", "parent")
            .prefetch_related("labels")
            .filter(project__owner=self.request.user)
            .order_by("-id")
        )


class ProjectTaskListView(ProjectScopedMixin, ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 20

    def get_queryset(self):
        return (
            Task.objects.select_related("project", "assignee", "parent")
            .prefetch_related("labels")
            .filter(project=self.project)
            .order_by("status", "-priority", "-id")
        )


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return (
            Task.objects.select_related("project", "assignee", "parent")
            .prefetch_related("labels", "children", "subtasks", "comments")
            .filter(project__owner=self.request.user)
        )


class TaskCreateView(ProjectScopedMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def get_form_kwargs(self) -> Dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["project"] = getattr(self, "project", None)
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TaskForm):
        form.instance.project = self.project
        form.instance.created_by = self.request.user
        # Optional default for status on "task" kind
        if form.instance.kind == "task" and not form.instance.status:
            form.instance.status = "todo"
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tasks:task_detail", kwargs={"pk": self.object.pk})


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def get_queryset(self):
        return Task.objects.filter(project__owner=self.request.user)

    def get_form_kwargs(self) -> Dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.object.project
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("tasks:task_detail", kwargs={"pk": self.object.pk})
