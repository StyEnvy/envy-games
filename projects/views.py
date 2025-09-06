from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Q

from .models import (
    Project, Board, Column, Task, Attachment, POSITION_STEP
)
from .forms import ProjectForm, TaskForm, QuickTaskForm

# Import role utilities from accounts app
from accounts.models import UserRole
from accounts.views import RoleRequiredMixin, role_required


# --- helpers ---------------------------------------------------------------

def _is_manager(request) -> bool:
    """
    Prefer the same role system used by the decorators/mixins.
    Fallback to legacy profile flag for compatibility.
    """
    user = request.user
    try:
        return bool(getattr(user, "has_role")(UserRole.PROJECT_MANAGER))  # type: ignore[attr-defined]
    except Exception:
        return hasattr(user, "profile") and getattr(user.profile, "is_project_manager", False)


def _task_card_template(task: Task) -> str:
    return "projects/partials/roadmap_card.html" if task.is_roadmap_item else "projects/partials/task_card.html"


# --- Lists / detail --------------------------------------------------------

class ProjectListView(LoginRequiredMixin, ListView):
    """Shows all projects (filterable by status, project_type; searchable)"""
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 12

    def get_queryset(self):
        qs = Project.objects.select_related("created_by")

        # status filter (?status=planning|active|hold|completed|archived|all)
        status = self.request.GET.get("status")
        if status and status != "all":
            qs = qs.filter(status=status)

        # project_type filter; accept either ?type=... or ?project_type=...
        ptype = self.request.GET.get("type") or self.request.GET.get("project_type")
        if ptype and ptype != "all":
            qs = qs.filter(project_type=ptype)

        # search
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_status"] = self.request.GET.get("status", "all")
        ctx["current_type"] = (self.request.GET.get("type") or self.request.GET.get("project_type") or "all")
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Project.STATUS_CHOICES
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        ctx["is_manager"] = _is_manager(self.request)
        return ctx


class ProjectListMineView(ProjectListView):
    """Only projects created by me."""
    def get_queryset(self):
        return super().get_queryset().filter(created_by=self.request.user)


class ProjectListAllView(ProjectListView):
    """Alias for 'all' – base queryset already shows all."""
    pass


class ProjectDetailView(LoginRequiredMixin, DetailView):
    """Shows project info with links to boards"""
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = self.object

        # Use signal-created boards; don't mutate here.
        ctx["tasks_board"] = Board.objects.filter(project=project, board_type="tasks").first()
        ctx["roadmap_board"] = Board.objects.filter(project=project, board_type="roadmap").first()
        ctx["is_manager"] = _is_manager(self.request)
        ctx["project_type_display"] = project.get_project_type_display()
        ctx["task_stats"] = {
            "total": project.tasks.count(),
            "assigned_to_me": project.tasks.filter(assignee=self.request.user).count(),
            "unassigned": project.tasks.filter(assignee=None).count(),
        }
        return ctx


class ProjectCreateView(RoleRequiredMixin, CreateView):
    """Create new project (Project Manager only)"""
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    required_roles = (UserRole.PROJECT_MANAGER,)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        # Boards/columns will be created by the post_save signal.
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("projects:detail", kwargs={"slug": self.object.slug})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Create"
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        return ctx


class ProjectUpdateView(RoleRequiredMixin, UpdateView):
    """Edit project (Project Manager only)"""
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    slug_url_kwarg = "slug"
    required_roles = (UserRole.PROJECT_MANAGER,)

    def get_success_url(self):
        return reverse_lazy("projects:detail", kwargs={"slug": self.object.slug})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Edit"
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        return ctx


# --- Boards ---------------------------------------------------------------

@login_required
def board_view(request, slug):
    """Interactive Tasks board with drag-drop"""
    project = get_object_or_404(Project, slug=slug)
    board = get_object_or_404(Board, project=project, board_type="tasks")

    context = {
        "project": project,
        "board": board,
        "columns": board.columns.prefetch_related("tasks__assignee", "tasks__attachments").order_by("position"),
        "is_manager": _is_manager(request),
        "project_type_display": project.get_project_type_display(),
    }
    return render(request, "projects/board.html", context)


@login_required
def roadmap_view(request, slug):
    """Roadmap board"""
    project = get_object_or_404(Project, slug=slug)
    board = get_object_or_404(Board, project=project, board_type="roadmap")

    context = {
        "project": project,
        "board": board,
        "columns": board.columns.prefetch_related("tasks__assignee", "tasks__attachments").order_by("position"),
        "is_manager": _is_manager(request),
        "project_type_display": project.get_project_type_display(),
    }
    return render(request, "projects/roadmap.html", context)


# --- HTMX: tasks ----------------------------------------------------------

@login_required
@require_POST
def move_task(request, task_id):
    """Handle drag & drop task movement with midpoint positioning + JSON counts."""
    task = get_object_or_404(Task, id=task_id)

    is_manager = _is_manager(request)
    if not is_manager and task.assignee != request.user:
        return JsonResponse({"ok": False, "error": "Unauthorized"}, status=403)

    try:
        new_column_id = int(request.POST.get("column_id"))
        new_index = int(request.POST.get("position", 0))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Bad params"}, status=400)

    old_column_id = task.column_id

    with transaction.atomic():
        # Move into the new column (if changed) before computing neighbors
        if new_column_id != task.column_id:
            task.column_id = new_column_id

        # Lock siblings to compute a stable position
        siblings_qs = (
            Task.objects.select_for_update()
            .filter(column_id=new_column_id)
            .exclude(pk=task.pk)
            .order_by("position")
        )
        siblings = list(siblings_qs)
        n = len(siblings)

        # Neighbors **in the final ordering** (i.e., including the dragged item):
        # prev sits at index new_index-1 if that index exists in siblings,
        # next sits at index new_index if that index exists in siblings.
        prev_pos = siblings[new_index - 1].position if (new_index - 1) >= 0 and (new_index - 1) < n else None
        next_pos = siblings[new_index].position if new_index < n else None

        # Prefer a midpoint between neighbors to avoid reindexing
        if prev_pos is not None and next_pos is not None and prev_pos + 1 < next_pos:
            task.position = (prev_pos + next_pos) // 2
        elif prev_pos is not None and next_pos is None:
            # Dropped at the end
            task.position = prev_pos + POSITION_STEP
        elif prev_pos is None and next_pos is not None:
            # Dropped at the top
            task.position = max(0, next_pos - POSITION_STEP)
        else:
            # Only item in the column
            task.position = POSITION_STEP

        # If a rare collision occurs, rebalance siblings by POSITION_STEP, then place
        if Task.objects.filter(column_id=new_column_id, position=task.position).exclude(pk=task.pk).exists():
            for idx, s in enumerate(siblings):
                s.position = (idx + 1) * POSITION_STEP
            Task.objects.bulk_update(siblings, ["position"])
            task.position = (new_index + 1) * POSITION_STEP

        task.save()

    # Return updated counts so the client can update badges without a refresh
    resp = {
        "ok": True,
        "task_id": task.id,
        "from_column_id": old_column_id,
        "to_column_id": new_column_id,
        "to_count": Task.objects.filter(column_id=new_column_id).count(),
    }
    if old_column_id != new_column_id:
        resp["from_count"] = Task.objects.filter(column_id=old_column_id).count()
    return JsonResponse(resp)


@login_required
@role_required(UserRole.PROJECT_MANAGER)
def quick_add_task(request, column_id):
    """Quick-add task to a column (Project Manager only)"""
    column = get_object_or_404(Column, id=column_id)

    if request.method == "POST":
        form = QuickTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = column.board.project
            task.column = column
            task.created_by = request.user
            task.is_roadmap_item = column.board.board_type == "roadmap"
            task.save()

            return render(request, _task_card_template(task), {
                "task": task,
                "is_manager": True,
            })

    return HttpResponse("Error", status=400)


@login_required
def task_modal(request, task_id):
    """Load/save task edit modal"""
    task = get_object_or_404(Task, id=task_id)
    is_manager = _is_manager(request)

    if request.method == "POST":
        if not is_manager and task.assignee != request.user:
            return HttpResponse("Unauthorized", status=403)

        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return render(request, _task_card_template(task), {
                "task": task,
                "is_manager": is_manager,
            })
    else:
        form = TaskForm(instance=task)

    return render(request, "projects/partials/task_modal.html", {
        "form": form,
        "task": task,
        "is_manager": is_manager,
    })


@login_required
@require_POST
@role_required(UserRole.PROJECT_MANAGER)
def convert_to_task(request, task_id):
    """Convert roadmap item to task (Project Managers only)"""
    task = get_object_or_404(Task, id=task_id)

    if task.convert_to_task():
        # Return empty body with 200 so hx-swap="outerHTML" removes the roadmap card
        return HttpResponse("")
    return HttpResponse("Error converting task", status=400)


@login_required
@require_POST
def upload_attachment(request, task_id):
    """Upload file attachment to task"""
    task = get_object_or_404(Task, id=task_id)
    is_manager = _is_manager(request)

    if not is_manager and task.assignee != request.user:
        return HttpResponse("Unauthorized", status=403)

    if "file" in request.FILES:
        Attachment.objects.create(task=task, file=request.FILES["file"], uploaded_by=request.user)
        return render(request, _task_card_template(task), {
            "task": task,
            "is_manager": is_manager,
        })

    return HttpResponse("No file provided", status=400)
