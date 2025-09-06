from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.decorators.http import require_POST
from django.http import HttpResponse
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
    """Shows all projects (filterable by status, searchable)"""
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 12

    def get_queryset(self):
        qs = Project.objects.select_related("created_by")

        status = self.request.GET.get("status")
        if status and status != "all":
            qs = qs.filter(status=status)

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_status"] = self.request.GET.get("status", "all")
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Project.STATUS_CHOICES
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
    }
    return render(request, "projects/roadmap.html", context)


# --- HTMX: tasks ----------------------------------------------------------

@login_required
@require_POST
def move_task(request, task_id):
    """Handle drag/drop task movement with safe gapped ordering."""
    task = get_object_or_404(Task, id=task_id)

    is_manager = _is_manager(request)
    if not is_manager and task.assignee != request.user:
        return HttpResponse("Unauthorized", status=403)

    new_column_id = request.POST.get("column_id")
    new_index = int(request.POST.get("position", 0))

    if not new_column_id:
        return HttpResponse("OK")

    new_column = get_object_or_404(Column, id=new_column_id)

    with transaction.atomic():
        # Move to new column (temporarily clear position to dodge unique constraint)
        task.column = new_column
        task.position = None
        task.save(update_fields=["column", "position"])

        # Rebuild an ordered list (excluding the task itself which has position=None)
        siblings = list(new_column.tasks.exclude(id=task.id).order_by("position", "id"))
        # Insert a placeholder at the target index
        if new_index < 0:
            new_index = 0
        if new_index > len(siblings):
            new_index = len(siblings)
        siblings.insert(new_index, task)

        # Try midpoint assignment to avoid reindexing
        def mid(a, b):
            return a + (b - a) // 2

        target_pos = None
        if new_index > 0 and new_index < len(siblings) - 1:
            prev_pos = siblings[new_index - 1].position
            next_pos = siblings[new_index + 1].position
            if prev_pos is not None and next_pos is not None and next_pos - prev_pos > 1:
                target_pos = mid(prev_pos, next_pos)
        elif new_index == 0 and len(siblings) > 1 and siblings[1].position is not None:
            next_pos = siblings[1].position
            # place before first; allow any non-negative int < next_pos
            target_pos = max(0, next_pos - POSITION_STEP // 2)
        elif new_index == len(siblings) - 1 and len(siblings) > 1 and siblings[-2].position is not None:
            prev_pos = siblings[-2].position
            target_pos = prev_pos + POSITION_STEP

        if target_pos is None:
            # Fallback: reindex all siblings with gapped spacing
            pos = 0
            for idx, s in enumerate(siblings):
                s.position = pos
                if s.id == task.id:
                    target_pos = pos
                pos += POSITION_STEP
            # bulk update (task included)
            for s in siblings:
                s.save(update_fields=["position"])

        else:
            task.position = target_pos
            task.save(update_fields=["position"])

    return HttpResponse("OK")


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
