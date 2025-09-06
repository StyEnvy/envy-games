from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Project, Board, Column, ProjectMembership
from .utils import DEFAULT_TASK_COLUMNS, DEFAULT_ROADMAP_COLUMNS


@receiver(post_save, sender=Project)
def create_default_boards(sender, instance: Project, created: bool, **kwargs):
    """
    On project creation, create default Tasks/Roadmap boards, columns,
    and add the creator as an active member (no per-project role).
    """
    if not created:
        return

    with transaction.atomic():
        tasks_board = Board.objects.create(
            project=instance,
            name="Tasks Board",
            board_type="tasks",
            is_active=True,
        )
        for col_name, position in DEFAULT_TASK_COLUMNS:
            Column.objects.create(board=tasks_board, name=col_name, position=position)

        roadmap_board = Board.objects.create(
            project=instance,
            name="Roadmap",
            board_type="roadmap",
            is_active=True,
        )
        for col_name, position in DEFAULT_ROADMAP_COLUMNS:
            Column.objects.create(board=roadmap_board, name=col_name, position=position)

        ProjectMembership.objects.get_or_create(
            project=instance,
            user=instance.created_by,
            defaults={"added_by": instance.created_by, "is_active": True},
        )
