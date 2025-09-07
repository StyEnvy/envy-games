from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .forms import TrackedProjectForm, TrackedTaskForm, TimeEntryForm
from .models import TrackedProject, TrackedTask, TimeEntry
from .permissions import is_pm, is_dev, can_edit_entry
from .utils import iso_week_bounds, round_for_display


# ----- Projects -----

class ProjectListCreateView(LoginRequiredMixin, ListView):
    model = TrackedProject
    template_name = "timetracking/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        qs = TrackedProject.objects.all()
        q = self.request.GET.get("q")
        active = self.request.GET.get("active")
        if q:
            qs = qs.filter(title__icontains=q)
        if active in {"true", "false"}:
            qs = qs.filter(is_active=(active == "true"))
        return qs

    def post(self, request, *args, **kwargs):
        if not (is_pm(request.user) or request.user.is_superuser):
            return HttpResponseForbidden()
        form = TrackedProjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Project created.")
        else:
            messages.error(request, "Could not create project.")
        return redirect("timetracking:project_list")


class ProjectUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = TrackedProject
    form_class = TrackedProjectForm
    template_name = "timetracking/project_form.html"
    success_url = reverse_lazy("timetracking:project_list")

    def test_func(self):
        user = self.request.user
        return user.is_superuser or is_pm(user)


# ----- Tasks -----

class TaskListCreateView(LoginRequiredMixin, View):
    template_name = "timetracking/task_list.html"

    def get(self, request, project_id):
        project = get_object_or_404(TrackedProject, pk=project_id)
        q = request.GET.get("q")
        tasks = project.tasks.all()
        if q:
            tasks = tasks.filter(title__icontains=q)
        form = TrackedTaskForm(initial={"project": project})
        return render(request, self.template_name, {"project": project, "tasks": tasks, "form": form})

    def post(self, request, project_id):
        project = get_object_or_404(TrackedProject, pk=project_id)
        if not (is_pm(request.user) or request.user.is_superuser or is_dev(request.user)):
            return HttpResponseForbidden()
        form = TrackedTaskForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Task created.")
        else:
            messages.error(request, "Could not create task.")
        return redirect("timetracking:task_list", project_id=project.id)


class TaskUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = TrackedTask
    form_class = TrackedTaskForm
    template_name = "timetracking/task_form.html"

    def get_success_url(self):
        return reverse("timetracking:task_list", args=[self.object.project_id])

    def test_func(self):
        user = self.request.user
        return user.is_superuser or is_pm(user)


# ----- Time Entries -----

class EntryListView(LoginRequiredMixin, ListView):
    model = TimeEntry
    template_name = "timetracking/entry_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["projects"] = TrackedProject.objects.order_by("title")
        # If a project filter is present, limit tasks accordingly for UX
        proj = self.request.GET.get("project")
        if proj:
            ctx["tasks"] = TrackedTask.objects.filter(project_id=proj).order_by("title")
        else:
            ctx["tasks"] = TrackedTask.objects.none()
        return ctx
    
    def get_queryset(self):
        qs = TimeEntry.objects.select_related("project", "task", "user")
        project = self.request.GET.get("project")
        task = self.request.GET.get("task")
        user = self.request.GET.get("user")
        date_from = self.request.GET.get("from")
        date_to = self.request.GET.get("to")
        if project:
            qs = qs.filter(project_id=project)
        if task:
            qs = qs.filter(task_id=task)
        if user:
            qs = qs.filter(user_id=user)
        if date_from:
            qs = qs.filter(work_date__gte=date_from)
        if date_to:
            qs = qs.filter(work_date__lte=date_to)
        return qs


class EntryCreateView(LoginRequiredMixin, CreateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = "timetracking/entry_form.html"

    def get_initial(self):
        initial = super().get_initial()
        # Allow preselect project/task via query params
        p = self.request.GET.get("project")
        t = self.request.GET.get("task")
        if p:
            initial["project"] = p
        if t:
            initial["task"] = t
        initial["work_date"] = timezone.now().date()
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Entry added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("timetracking:entry_list")


class EntryUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = "timetracking/entry_form.html"

    def test_func(self):
        obj: TimeEntry = self.get_object()
        return can_edit_entry(self.request.user, obj.user_id)

    def form_valid(self, form):
        messages.success(self.request, "Entry updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("timetracking:entry_list")


class EntryDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = TimeEntry
    template_name = "timetracking/entry_confirm_delete.html"
    success_url = reverse_lazy("timetracking:entry_list")

    def test_func(self):
        obj: TimeEntry = self.get_object()
        return can_edit_entry(self.request.user, obj.user_id)


# ----- Weekly Reports -----

@login_required
def weekly_report(request):
    today = timezone.localdate()
    week_start_str = request.GET.get("week_start")
    if week_start_str:
        try:
            y, m, d = map(int, week_start_str.split("-"))
            base = date(y, m, d)
        except Exception:
            base = today
    else:
        base = today

    start, end = iso_week_bounds(base)

    qs = TimeEntry.objects.filter(work_date__gte=start, work_date__lt=end)
    project_id = request.GET.get("project")
    if project_id:
        qs = qs.filter(project_id=project_id)

    # Aggregations
    by_project = (
        qs.values("project__id", "project__title")
        .annotate(total=Sum("duration_minutes"))
        .order_by("project__title")
    )
    by_task = (
        qs.values("task__id", "task__title", "project__title")
        .annotate(total=Sum("duration_minutes"))
        .order_by("project__title", "task__title")
    )
    by_user = (
        qs.values("user__id", "user__username")
        .annotate(total=Sum("duration_minutes"))
        .order_by("user__username")
    )

    def _round(group):
        for g in group:
            g["total_display"] = round_for_display(g["total"], step=5)
        return group

    context = {
        "week_start": start,
        "week_end": end - timezone.timedelta(days=1),
        "by_project": _round(list(by_project)),
        "by_task": _round(list(by_task)),
        "by_user": _round(list(by_user)),
        "projects": TrackedProject.objects.order_by("title"),
    }
    return render(request, "timetracking/weekly_report.html", context)


@login_required
def weekly_report_csv(request):
    import csv
    today = timezone.localdate()
    start, end = iso_week_bounds(today)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename=weekly_report_{start}.csv"

    qs = (
        TimeEntry.objects.filter(work_date__gte=start, work_date__lt=end)
        .select_related("project", "task", "user")
        .order_by("project__title", "task__title", "user__username", "work_date")
    )

    writer = csv.writer(response)
    writer.writerow(["Date", "Project", "Task", "User", "Minutes", "Billable", "Notes"])
    for e in qs:
        writer.writerow([
            e.work_date, e.project.title, e.task.title, e.user.username,
            e.duration_minutes, "yes" if e.billable else "no", e.notes or "",
        ])
    return response