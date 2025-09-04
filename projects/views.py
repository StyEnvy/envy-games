from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, TemplateView, UpdateView
from django.urls import reverse_lazy
from django.db.models import Q, Count
from django.core.paginator import Paginator

from .forms import ProjectForm
from .models import Project
from tasks.models import Task


class ProjectHomeView(LoginRequiredMixin, TemplateView):
    template_name = "projects/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mine = Project.objects.open().owned_by(self.request.user)
        ctx.update(
            {
                "count_mine": mine.count(),
                "count_all": Project.objects.open().count(),
                "recent_mine": mine.order_by("-created_at")[:5].select_related("owner"),
                "recent_all": Project.objects.open().order_by("-created_at")[:5].select_related("owner"),
            }
        )
        return ctx


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 25

    # set via urls.py: "mine" or "all"
    scope = "mine"

    def get_queryset(self):
        qs = Project.objects.open().select_related("owner")

        if self.scope == "mine":
            qs = qs.owned_by(self.request.user)

        q = self.request.GET.get("q")
        type_ = self.request.GET.get("type")
        status = self.request.GET.get("status")

        if type_:
            qs = qs.filter(type=type_)
        if status:
            qs = qs.filter(status=status)
        qs = qs.search(q)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["scope"] = self.scope
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["current_type"] = self.request.GET.get("type", "")
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["TYPE_CHOICES"] = Project.TYPE_CHOICES
        ctx["STATUS_CHOICES"] = Project.STATUS_CHOICES
        return ctx


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("projects:list_mine")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        # Owner-only for now (flat ownership)
        return Project.objects.owned_by(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project: Project = self.object

        # Filters
        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        priority = (self.request.GET.get("priority") or "").strip()

        tasks_qs = (
            Task.objects.select_related("project", "assignee", "parent")
            .prefetch_related("labels")
            .filter(project=project)
        )
        if q:
            tasks_qs = tasks_qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if status:
            tasks_qs = tasks_qs.filter(status=status)
        if priority:
            tasks_qs = tasks_qs.filter(priority=priority)

        tasks_qs = tasks_qs.order_by("status", "-priority", "-id")

        paginator = Paginator(tasks_qs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        # counts by status
        status_counts_raw = (
            Task.objects.filter(project=project)
            .values("status")
            .annotate(n=Count("id"))
        )
        status_counts = {(row["status"] or ""): row["n"] for row in status_counts_raw}
        all_count = sum(status_counts.get(k, 0) for k in ("todo", "doing", "review", "done"))

        # Build options for selects (avoid inline comparisons in template)
        status_choices = getattr(Task, "STATUS_CHOICES", [])
        status_options = [
            {"value": str(v), "label": str(l), "selected": str(v) == status}
            for (v, l) in status_choices
        ]
        priority_options = [
            {"value": "1", "label": "P1", "selected": priority == "1"},
            {"value": "2", "label": "P2", "selected": priority == "2"},
            {"value": "3", "label": "P3", "selected": priority == "3"},
        ]

        ctx.update(
            {
                "q": q,
                "status_filter": status,
                "priority_filter": priority,
                "page_obj": page_obj,
                "tasks": page_obj.object_list,
                "status_counts": status_counts,
                "all_count": all_count,
                "status_options": status_options,
                "priority_options": priority_options,
                # chip booleans
                "status_all": status == "",
                "status_todo": status == "todo",
                "status_doing": status == "doing",
                "status_review": status == "review",
                "status_done": status == "done",
            }
        )
        return ctx


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "projects/project_form.html"

    def get_queryset(self):
        return Project.objects.owned_by(self.request.user)

    def get_success_url(self):
        return reverse_lazy("projects:detail", kwargs={"slug": self.object.slug})