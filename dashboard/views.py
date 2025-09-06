from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Q, Count, Case, When, IntegerField, OuterRef, Subquery, F, Value
)
from django.db.models.functions import Coalesce
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta

from projects.models import Project, Task
from accounts.models import UserRole
from audits.models import AuditLog, AuditAction


@login_required
def dashboard_view(request):
    """Dashboard view with To Do / In Progress / Pending Review sections + actor on recent activity"""
    user = request.user
    is_manager = (
        (hasattr(user, "profile") and user.profile.role == UserRole.PROJECT_MANAGER)
        or (callable(getattr(user, "has_role", None)) and user.has_role(UserRole.PROJECT_MANAGER))
    )

    # Active projects
    if is_manager:
        active_projects = (
            Project.objects.filter(status__in=["planning", "active"])
            .select_related("created_by")
            .annotate(
                total_tasks=Count("tasks"),
                my_tasks=Count(Case(When(tasks__assignee=user, then=1), output_field=IntegerField())),
                unassigned_tasks=Count(Case(When(tasks__assignee__isnull=True, then=1), output_field=IntegerField())),
            )
            .order_by("-updated_at")[:6]
        )
    else:
        active_projects = (
            Project.objects.filter(Q(created_by=user) | Q(tasks__assignee=user), status__in=["planning", "active"])
            .distinct()
            .select_related("created_by")
            .annotate(
                total_tasks=Count("tasks", distinct=True),
                my_tasks=Count(Case(When(tasks__assignee=user, then=1), output_field=IntegerField()), distinct=True),
            )
            .order_by("-updated_at")[:6]
        )

    # My assigned tasks (tasks board only)
    my_tasks = (
        Task.objects.filter(assignee=user, column__board__board_type="tasks")
        .select_related("project", "column", "created_by")
        .order_by("priority", "-created_at")
    )

    # Column-name heuristics
    todo_q = Q(column__name__iexact="To Do") | Q(column__name__iexact="Todo") | Q(column__name__icontains="backlog")
    inprog_q = (
        Q(column__name__iexact="In Progress")
        | Q(column__name__icontains="progress")
        | Q(column__name__iexact="Doing")
        | Q(column__name__iexact="WIP")
    )
    review_q = (
        Q(column__name__iexact="Review")
        | Q(column__name__iexact="In Review")
        | Q(column__name__iexact="Pending Review")
        | Q(column__name__icontains="review")
    )

    # Lists for the dashboard column
    todo_tasks = my_tasks.filter(todo_q).order_by("column__position", "position", "-updated_at")[:5]
    in_progress_tasks = my_tasks.filter(inprog_q).order_by("column__position", "position", "-updated_at")[:5]
    pending_review_tasks = my_tasks.filter(review_q).order_by("column__position", "position", "-updated_at")[:5]

    # Task statistics
    task_stats = {
        "total_assigned": my_tasks.count(),
        "high_priority": my_tasks.filter(priority="high").count(),
        "in_progress": my_tasks.filter(inprog_q).count(),
        "pending_review": my_tasks.filter(review_q).count(),
    }

    # Manager: unassigned high-priority items (open states)
    unassigned_urgent = []
    if is_manager:
        unassigned_urgent = (
            Task.objects.filter(
                assignee__isnull=True,
                priority="high",
                column__board__board_type="tasks",
            )
            .filter(todo_q | inprog_q)
            .select_related("project", "column")
            .order_by("-created_at")[:5]
        )

    # Recent activity (last 7 days) — annotate with latest AuditLog actor/action
    seven_days_ago = timezone.now() - timedelta(days=7)
    task_ct = ContentType.objects.get_for_model(Task)

    latest_logs = (
        AuditLog.objects.filter(content_type=task_ct, object_id=OuterRef("pk"))
        .order_by("-timestamp")
    )

    recent_activity = (
        Task.objects.filter(Q(created_at__gte=seven_days_ago) | Q(updated_at__gte=seven_days_ago))
        .annotate(
            last_actor=Coalesce(Subquery(latest_logs.values("user__username")[:1]), F("created_by__username")),
            # Default to code "update" (matches template conditions) rather than the human label.
            last_action=Coalesce(Subquery(latest_logs.values("action")[:1]), Value(AuditAction.UPDATE)),
        )
        .select_related("project", "assignee", "created_by")
        .order_by("-updated_at")
    )

    if not is_manager:
        user_projects = active_projects.values_list("id", flat=True)
        recent_activity = recent_activity.filter(
            Q(assignee=user) | Q(created_by=user) | Q(project__in=user_projects)
        )

    recent_activity = recent_activity[:10]

    # Roadmap items in review (manager only)
    roadmap_review = []
    if is_manager:
        roadmap_review = (
            Task.objects.filter(is_roadmap_item=True, column__name__icontains="review")
            .select_related("project", "created_by")
            .order_by("-created_at")[:5]
        )

    context = {
        "user": user,
        "is_manager": is_manager,
        "active_projects": active_projects,
        "todo_tasks": todo_tasks,
        "in_progress_tasks": in_progress_tasks,
        "pending_review_tasks": pending_review_tasks,
        "task_stats": task_stats,
        "unassigned_urgent": unassigned_urgent,
        "recent_activity": recent_activity,
        "roadmap_review": roadmap_review,
    }
    return render(request, "dashboard/dashboard.html", context)
