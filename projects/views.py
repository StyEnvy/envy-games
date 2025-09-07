from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST, require_http_methods
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Q, Count, Prefetch, Max
import logging

from .forms import ProjectForm, TaskForm, QuickTaskForm, AddMemberForm, ProjectLinkFormSet
from .models import Project, Board, Column, Task, ProjectMembership 
from .utils import POSITION_STEP

from assetcatalog.models import Asset, AssetType

from accounts.models import UserRole
from accounts.views import RoleRequiredMixin, role_required, user_has_role

logger = logging.getLogger(__name__)

# --- helpers ---------------------------------------------------------------

def is_pm(user) -> bool:
    """Single source of truth: rely on accounts app to determine role."""
    return user_has_role(user, UserRole.PROJECT_MANAGER)


def _task_card_template(task: Task) -> str:
    return "projects/partials/roadmap_card.html" if task.is_roadmap_item else "projects/partials/task_card.html"


# --- Lists / detail --------------------------------------------------------

class ProjectListView(LoginRequiredMixin, ListView):
    """Shows projects (filterable by status/type; searchable). 'All' excludes hold/completed/archived."""
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 12

    # Hidden from the "All" view
    HIDDEN_IN_ALL = {"hold", "completed", "archived"}

    def get_paginate_by(self, queryset):
        # Allow ?per=12|24|48|96 (clamped)
        try:
            per = int(self.request.GET.get("per", 12))
        except (TypeError, ValueError):
            per = 12
        return max(6, min(per, 96))

    def get_queryset(self):
        qs = Project.objects.select_related("created_by", "created_by__profile")

        # Status filter
        status = (self.request.GET.get("status") or "").strip()
        valid_statuses = dict(Project.STATUS_CHOICES).keys()
        if status and status != "all" and status in valid_statuses:
            qs = qs.filter(status=status)
        else:
            # Default "All" view hides on-hold/completed/archived
            qs = qs.exclude(status__in=self.HIDDEN_IN_ALL)

        # Type filter
        ptype = (self.request.GET.get("type") or self.request.GET.get("project_type") or "").strip()
        if ptype and ptype != "all" and ptype in dict(Project.PROJECT_TYPE_CHOICES):
            qs = qs.filter(project_type=ptype)

        # Search
        q = (self.request.GET.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # Sorting
        sort = (self.request.GET.get("sort") or "new").strip()
        order_map = {
            "new": "-created_at",
            "old": "created_at",
            "title": "title",
            "title_desc": "-title",
        }
        order_field = order_map.get(sort, "-created_at")
        return qs.order_by(order_field, "-created_at", "title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # sanitize inputs
        status = self.request.GET.get("status", "all")
        ptype = (self.request.GET.get("type") or self.request.GET.get("project_type") or "all")
        q = (self.request.GET.get("q") or "")[:100]
        sort = (self.request.GET.get("sort") or "new")
        if sort not in {"new", "old", "title", "title_desc"}:
            sort = "new"
        try:
            per = int(self.request.GET.get("per", 12))
        except (TypeError, ValueError):
            per = 12
        per = max(6, min(per, 96))

        ctx["current_status"] = status
        ctx["current_type"] = ptype
        ctx["current_q"] = q
        ctx["current_sort"] = sort
        ctx["current_per"] = per
        ctx["status_choices"] = Project.STATUS_CHOICES
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        ctx["is_manager"] = is_pm(self.request.user)

        # boolean flags to avoid comparisons in templates
        ctx["sort_is_new"] = sort == "new"
        ctx["sort_is_old"] = sort == "old"
        ctx["sort_is_title"] = sort == "title"
        ctx["sort_is_title_desc"] = sort == "title_desc"

        ctx["per_is_12"] = per == 12
        ctx["per_is_24"] = per == 24
        ctx["per_is_48"] = per == 48
        ctx["per_is_96"] = per == 96

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

    def get_queryset(self):
        # Optimize with prefetch for boards and memberships
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "boards",
                Prefetch(
                    "memberships",
                    queryset=ProjectMembership.objects.filter(is_active=True)
                    .select_related("user", "user__profile", "added_by")
                ),
            )
            .select_related("created_by", "created_by__profile")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = self.object

        # Boards (prefetched)
        boards_by_type = {b.board_type: b for b in project.boards.all()}
        ctx["tasks_board"] = boards_by_type.get("tasks")
        ctx["roadmap_board"] = boards_by_type.get("roadmap")

        ctx["is_manager"] = is_pm(self.request.user)
        ctx["project_type_display"] = project.get_project_type_display()

        # Task stats (single aggregate)
        task_stats = project.tasks.aggregate(
            total=Count("id"),
            assigned_to_me=Count("id", filter=Q(assignee=self.request.user)),
            unassigned=Count("id", filter=Q(assignee=None)),
        )
        ctx["task_stats"] = task_stats

        # Members already prefetched
        ctx["members"] = project.memberships.all()
        ctx["add_member_form"] = AddMemberForm(project=project) if ctx["is_manager"] else None
        return ctx


class ProjectCreateView(RoleRequiredMixin, CreateView):
    """Create new project (Project Manager only)"""
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    required_roles = (UserRole.PROJECT_MANAGER,)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("projects:detail", kwargs={"slug": self.object.slug})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Create"
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        ctx.setdefault("links_formset", ProjectLinkFormSet(prefix="links"))
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        links_formset = ProjectLinkFormSet(request.POST, prefix="links")
        if form.is_valid() and links_formset.is_valid():
            with transaction.atomic():
                form.instance.created_by = request.user
                self.object = form.save()
                links_formset.instance = self.object
                links_formset.save()
            return redirect(self.get_success_url())
        # invalid -> re-render with errors
        return self.render_to_response(self.get_context_data(form=form, links_formset=links_formset))


class ProjectUpdateView(RoleRequiredMixin, UpdateView):
    """Edit project (Project Manager only)"""
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    slug_url_kwarg = "slug"
    required_roles = (UserRole.PROJECT_MANAGER,)

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            qs = qs.filter(created_by=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Edit"
        ctx["type_choices"] = Project.PROJECT_TYPE_CHOICES
        if self.request.method == "POST":
            ctx["links_formset"] = ProjectLinkFormSet(self.request.POST, instance=self.object, prefix="links")
        else:
            ctx["links_formset"] = ProjectLinkFormSet(instance=self.object, prefix="links")
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        links_formset = ProjectLinkFormSet(request.POST, instance=self.object, prefix="links")
        if form.is_valid() and links_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                links_formset.save()
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form, links_formset=links_formset))


# --- Boards ---------------------------------------------------------------

def _board_view_generic(request, slug, board_type):
    """Generic board view handler for both tasks and roadmap boards"""
    project = get_object_or_404(
        Project.objects.select_related("created_by", "created_by__profile"),
        slug=slug
    )
    
    board = get_object_or_404(
        Board.objects.prefetch_related(
            Prefetch(
                "columns",
                queryset=Column.objects.prefetch_related(
                    Prefetch(
                        "tasks",
                        queryset=Task.objects.select_related(
                            "assignee", "assignee__profile", "created_by"
                        ).order_by("position"),
                    )
                ).annotate(
                    task_count=Count('tasks')  # Add this annotation
                ).order_by("position"),
            )
        ),
        project=project,
        board_type=board_type,
    )

    template_map = {
        "tasks": "projects/board.html",
        "roadmap": "projects/roadmap.html",
    }

    context = {
        "project": project,
        "board": board,
        "columns": board.columns.all(),
        "is_manager": is_pm(request.user),
        "project_type_display": project.get_project_type_display(),
    }
    
    return render(request, template_map[board_type], context)

@login_required
def board_view(request, slug):
    """Interactive Tasks board with drag-drop"""
    return _board_view_generic(request, slug, "tasks")


@login_required
def roadmap_view(request, slug):
    """Roadmap board"""
    return _board_view_generic(request, slug, "roadmap")


# --- HTMX: tasks ----------------------------------------------------------

@login_required
@require_POST
def move_task(request, task_id):
    """Handle drag & drop task movement with midpoint positioning + JSON counts."""
    try:
        # Fetch with select_related for optimization
        task = get_object_or_404(
            Task.objects.select_related("column", "project", "assignee"),
            id=task_id
        )

        is_pm_flag = is_pm(request.user)
        if not is_pm_flag and task.assignee_id != request.user.id:
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=403)

        try:
            new_column_id = int(request.POST.get("column_id", 0))
            new_index = int(request.POST.get("position", 0))
            if new_column_id <= 0:
                raise ValueError("Invalid column ID")
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid parameters"}, status=400)

        old_column_id = task.column_id

        with transaction.atomic():
            # Verify column exists and belongs to same project
            new_column = get_object_or_404(
                Column.objects.select_related("board__project"),
                id=new_column_id,
            )
            if new_column.board.project_id != task.project_id:
                return JsonResponse({"ok": False, "error": "Invalid column"}, status=400)

            # Move into the new column
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

            # Check if we need rebalancing (positions getting too large)
            if siblings and siblings[-1].position > 1000000:
                # Rebalance all positions
                for idx, s in enumerate(siblings):
                    s.position = (idx + 1) * POSITION_STEP
                Task.objects.bulk_update(siblings, ["position"])

            # Calculate new position
            prev_pos = siblings[new_index - 1].position if 0 <= new_index - 1 < n else None
            next_pos = siblings[new_index].position if new_index < n else None

            if prev_pos is not None and next_pos is not None and prev_pos + 1 < next_pos:
                task.position = (prev_pos + next_pos) // 2
            elif prev_pos is not None:
                task.position = prev_pos + POSITION_STEP
            elif next_pos is not None:
                task.position = max(1, next_pos - POSITION_STEP)
            else:
                task.position = POSITION_STEP

            # Handle collisions by rebalancing
            if Task.objects.filter(column_id=new_column_id, position=task.position).exclude(pk=task.pk).exists():
                for idx, s in enumerate(siblings):
                    s.position = (idx + 1) * POSITION_STEP
                Task.objects.bulk_update(siblings, ["position"])
                task.position = (new_index + 1) * POSITION_STEP

            task.save(update_fields=["column_id", "position"])

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

    except Exception as e:
        logger.error(f"Error moving task {task_id}: {str(e)}")
        return JsonResponse({"ok": False, "error": "Internal server error"}, status=500)

@login_required
@role_required(UserRole.PROJECT_MANAGER)
@require_POST
def quick_add_task(request, column_id):
    """Quick-add task to a column (Project Manager only)"""
    try:
        column = get_object_or_404(
            Column.objects.select_related("board__project"),
            id=column_id,
        )

        form = QuickTaskForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                task = form.save(commit=False)
                task.project = column.board.project
                task.column = column
                task.created_by = request.user
                task.is_roadmap_item = column.board.board_type == "roadmap"

                # Set position to end
                max_pos = (
                    Task.objects.filter(column=column)
                    .select_for_update()
                    .aggregate(max_pos=Max("position"))["max_pos"] or 0
                )
                task.position = max_pos + POSITION_STEP
                
                # Check if rebalancing needed
                if task.position > 1000000:
                    from .utils import rebalance_column_positions
                    rebalance_column_positions(column_id)
                    task.position = POSITION_STEP  # Will be at the end after rebalance

                task.save()

            # Fetch with related data for rendering
            task.refresh_from_db()
            task = Task.objects.select_related(
                "assignee", "assignee__profile", "column"
            ).get(pk=task.pk)

            return render(
                request,
                _task_card_template(task),
                {
                    "task": task,
                    "is_manager": True,
                    "column": column,
                },
            )
        else:
            return HttpResponseBadRequest("Invalid form data")

    except Exception as e:
        logger.error(f"Error adding task to column {column_id}: {str(e)}")
        return HttpResponseBadRequest("Error creating task")

@login_required
@require_http_methods(["GET", "POST"])
def task_modal(request, task_id):
    """Load/save task edit modal"""
    task = get_object_or_404(
        Task.objects.select_related("assignee", "project", "column", "assignee__profile"),
        id=task_id,
    )
    is_pm_flag = is_pm(request.user)
    
    # Check view permissions for GET and POST
    can_view = is_pm_flag or task.assignee_id == request.user.id
    if not can_view:
        # Also check if user is a member of the project
        is_member = task.project.memberships.filter(
            user=request.user, is_active=True
        ).exists()
        if not is_member:
            return HttpResponse("Unauthorized", status=403)

    if request.method == "POST":
        # Only PM or assignee can edit
        if not is_pm_flag and task.assignee_id != request.user.id:
            return HttpResponse("Unauthorized", status=403)

        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save()
            return render(
                request,
                _task_card_template(task),
                {
                    "task": task,
                    "is_manager": is_pm_flag,
                    "column": task.column,
                },
            )
    else:
        form = TaskForm(instance=task)

    return render(
        request,
        "projects/partials/task_modal.html",
        {
            "form": form,
            "task": task,
            "is_manager": is_pm_flag,
            "can_edit": is_pm_flag or task.assignee_id == request.user.id,
        },
    )


@login_required
@role_required(UserRole.PROJECT_MANAGER)
@require_POST
def convert_to_task(request, task_id):
    """Convert roadmap item to task (Project Managers only)"""
    try:
        task = get_object_or_404(
            Task.objects.select_related("project", "column__board"),
            id=task_id
        )

        if not task.is_roadmap_item:
            return HttpResponseBadRequest("Not a roadmap item")

        if task.convert_to_task():
            return HttpResponse("")  # hx-swap="outerHTML" removes the card
        return HttpResponseBadRequest("Error converting task")

    except Exception as e:
        logger.error(f"Error converting task {task_id}: {str(e)}")
        return HttpResponseBadRequest("Conversion failed")


# --- Members ---------------------------------------------------------------

@login_required
@role_required(UserRole.PROJECT_MANAGER)
@require_http_methods(["GET", "POST"])
def add_member(request, slug):
    project = get_object_or_404(Project, slug=slug)

    if request.method == "GET":
        add_member_form = AddMemberForm(project=project)
        return render(request, "projects/partials/add_member_form.html", {
            "project": project,
            "add_member_form": add_member_form,
        })

    # POST
    add_member_form = AddMemberForm(request.POST, project=project)
    if add_member_form.is_valid():
        user = add_member_form.cleaned_data["user_id"]

        # already a member?
        if project.memberships.filter(user=user, is_active=True).exists():
            add_member_form.add_error("user_id", "User is already a member.")
        else:
            project.add_member(user, added_by=request.user)

    # Always return both: the members list (normal swap) and a refreshed form (OOB)
    members = project.memberships.filter(is_active=True).order_by("joined_at")
    html = render_to_string("projects/partials/members_list.html", {
        "members": members,
        "project": project,
        "is_manager": True,
    }, request=request)

    form_html = render_to_string("projects/partials/add_member_form.html", {
        "project": project,
        # fresh form after success; keep errors if invalid
        "add_member_form": AddMemberForm(project=project) if not add_member_form.errors else add_member_form,
        "oob": True,
    }, request=request)

    # Append OOB wrapper so only the form area is replaced alongside the list
    html += f'<div id="add-member-form" hx-swap-oob="true">{form_html}</div>'
    return HttpResponse(html)


@login_required
@role_required(UserRole.PROJECT_MANAGER)
@require_POST
def remove_member(request, slug, user_id):
    """Remove a member from the project (PM only)"""
    project = get_object_or_404(Project, slug=slug)

    # Don't allow removing the creator
    if project.created_by_id == user_id:
        return HttpResponseBadRequest("Cannot remove project creator")

    try:
        # Soft delete the membership
        membership = get_object_or_404(ProjectMembership, project=project, user_id=user_id)
        membership.is_active = False
        membership.save(update_fields=["is_active"])

        # Unassign any tasks from this user
        Task.objects.filter(project=project, assignee_id=user_id).update(assignee=None)

        # Return updated members list
        members = project.memberships.filter(is_active=True).order_by("joined_at")
        return render(
            request,
            "projects/partials/members_list.html",
            {
                "members": members,
                "project": project,
                "is_manager": True,
            },
        )

    except Exception as e:
        logger.error(f"Error removing member {user_id} from project {slug}: {str(e)}")
        return HttpResponseBadRequest("Failed to remove member")

## Asset catalog integration

class ProjectAssetListView(LoginRequiredMixin, ListView):
    """Project-scoped list of assets sourced from assetcatalog."""
    model = Asset
    template_name = "projects/project_asset_list.html"
    context_object_name = "assets"
    paginate_by = 12

    SORT_ALLOWLIST = {"created_at", "-created_at", "title", "-title", "updated_at", "-updated_at"}
    SORT_LABELS = {
        "-created_at": "Newest first",
        "created_at": "Oldest first",
        "title": "Title A–Z",
        "-title": "Title Z–A",
        "-updated_at": "Recently updated",
        "updated_at": "Least recently updated",
    }
    PER_CHOICES = (12, 24, 48, 96)

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, slug=kwargs["slug"])
        if not self.project.user_can_view(request.user):
            raise PermissionDenied("You do not have access to this project.")
        return super().dispatch(request, *args, **kwargs)

    def get_paginate_by(self, queryset):
        try:
            per = int(self.request.GET.get("per", self.paginate_by))
        except (TypeError, ValueError):
            per = self.paginate_by
        return max(6, min(per, 96))

    def get_queryset(self):
        qs = (
            Asset.objects.filter(projects=self.project)
            .select_related("current_version", "created_by")
            .prefetch_related("projects")
            .distinct()
        )

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q))

        atype = (self.request.GET.get("type") or "").strip()
        if atype and atype in dict(AssetType.choices):
            qs = qs.filter(asset_type=atype)

        sort = (self.request.GET.get("sort") or "-created_at").strip()
        if sort not in self.SORT_ALLOWLIST:
            sort = "-created_at"
        self._current_sort = sort
        return qs.order_by(sort, "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project"] = self.project

        st = (self.request.GET.get("type") or "")
        sort = getattr(self, "_current_sort", "-created_at")
        per = self.get_paginate_by(self.object_list)

        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_type"] = st
        ctx["sort"] = sort
        ctx["per"] = per

        ctx["asset_types_annot"] = [(val, label, (val == st)) for val, label in AssetType.choices]
        ctx["sort_options"] = [(val, self.SORT_LABELS[val], val == sort) for val in (
            "-created_at", "created_at", "title", "-title", "-updated_at", "updated_at"
        )]
        ctx["per_options"] = [(n, str(n), n == per) for n in self.PER_CHOICES]

        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        ctx["has_filters"] = bool(ctx["q"] or ctx["selected_type"] or self.request.GET.get("sort") or self.request.GET.get("per"))
        return ctx
