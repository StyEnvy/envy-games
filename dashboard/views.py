from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Case, When, IntegerField
from django.utils import timezone
from datetime import timedelta

from projects.models import Project, Task, Board
from accounts.models import UserRole


@login_required
def dashboard_view(request):
    """Enhanced dashboard view with comprehensive project and task overview"""
    
    user = request.user
    is_manager = (
        hasattr(user, 'profile') and 
        user.profile.role == UserRole.PROJECT_MANAGER
    )
    
    # Active projects (either created by user or user has tasks in)
    if is_manager:
        # Managers see all active projects
        active_projects = Project.objects.filter(
            status__in=['planning', 'active']
        ).select_related('created_by').annotate(
            total_tasks=Count('tasks'),
            my_tasks=Count(
                Case(
                    When(tasks__assignee=user, then=1),
                    output_field=IntegerField()
                )
            ),
            unassigned_tasks=Count(
                Case(
                    When(tasks__assignee__isnull=True, then=1),
                    output_field=IntegerField()
                )
            )
        ).order_by('-updated_at')[:6]
    else:
        # Developers see projects they're involved in
        active_projects = Project.objects.filter(
            Q(created_by=user) | Q(tasks__assignee=user),
            status__in=['planning', 'active']
        ).distinct().select_related('created_by').annotate(
            total_tasks=Count('tasks', distinct=True),
            my_tasks=Count(
                Case(
                    When(tasks__assignee=user, then=1),
                    output_field=IntegerField()
                ),
                distinct=True
            )
        ).order_by('-updated_at')[:6]
    
    # My assigned tasks (across all projects)
    my_tasks = Task.objects.filter(
        assignee=user,
        column__board__board_type='tasks'
    ).select_related(
        'project', 
        'column',
        'created_by'
    ).order_by('priority', '-created_at')
    
    # Separate tasks by column status
    todo_tasks = my_tasks.filter(column__name='To Do')[:5]
    in_progress_tasks = my_tasks.filter(column__name='In Progress')[:5]
    review_tasks = my_tasks.filter(column__name='Review')[:5]
    
    # Task statistics
    task_stats = {
        'total_assigned': my_tasks.count(),
        'high_priority': my_tasks.filter(priority='high').count(),
        'in_progress': in_progress_tasks.count(),
        'pending_review': review_tasks.count(),
    }
    
    # For managers: unassigned high-priority tasks
    unassigned_urgent = []
    if is_manager:
        unassigned_urgent = Task.objects.filter(
            assignee__isnull=True,
            priority='high',
            column__board__board_type='tasks',
            column__name__in=['To Do', 'In Progress']
        ).select_related('project', 'column').order_by('-created_at')[:5]
    
    # Recent activity (tasks created or updated in last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_activity = Task.objects.filter(
        Q(created_at__gte=seven_days_ago) | Q(updated_at__gte=seven_days_ago)
    ).select_related(
        'project',
        'assignee',
        'created_by'
    ).order_by('-updated_at')
    
    if not is_manager:
        # Developers see only their tasks or tasks in their projects
        user_projects = active_projects.values_list('id', flat=True)
        recent_activity = recent_activity.filter(
            Q(assignee=user) | 
            Q(created_by=user) | 
            Q(project__in=user_projects)
        )
    
    recent_activity = recent_activity[:10]
    
    # Roadmap items in review (for managers)
    roadmap_review = []
    if is_manager:
        roadmap_review = Task.objects.filter(
            is_roadmap_item=True,
            column__name='In Review'
        ).select_related('project', 'created_by').order_by('-created_at')[:5]
    
    context = {
        'user': user,
        'is_manager': is_manager,
        'active_projects': active_projects,
        'todo_tasks': todo_tasks,
        'in_progress_tasks': in_progress_tasks,
        'review_tasks': review_tasks,
        'task_stats': task_stats,
        'unassigned_urgent': unassigned_urgent,
        'recent_activity': recent_activity,
        'roadmap_review': roadmap_review,
    }
    
    return render(request, 'dashboard/dashboard.html', context)