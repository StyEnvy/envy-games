from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Project


@receiver(post_save, sender=Project)
def provision_boards_and_columns(sender, instance: Project, created, **kwargs):
    if not created:
        return

    def _provision():
        Board = apps.get_model("tasks", "Board")
        Column = apps.get_model("tasks", "Column")
        Label = apps.get_model("tasks", "Label")

        with transaction.atomic():
            # Boards
            task_board = Board.objects.create(
                project=instance, name="Tasks", kind="task", is_default=True, order=1000
            )
            roadmap_board = Board.objects.create(
                project=instance, name="Roadmap", kind="roadmap", is_default=True, order=2000
            )

            # Columns (align with spec)
            Column.objects.bulk_create(
                [
                    Column(board=task_board, name="To Do", order=1000),
                    Column(board=task_board, name="Doing", order=2000),
                    Column(board=task_board, name="Review", order=3000),
                    Column(board=task_board, name="Done", order=4000),
                ]
            )
            Column.objects.bulk_create(
                [
                    Column(board=roadmap_board, name="Concept", order=1000),
                    Column(board=roadmap_board, name="In Review", order=2000),
                    Column(board=roadmap_board, name="Planned", order=3000),
                    Column(board=roadmap_board, name="Won't Do", order=4000),
                ]
            )

            # Seed common labels (extend anytime)
            Label.objects.get_or_create(project=instance, name="design", defaults={"color": "#a78bfa"})
            Label.objects.get_or_create(project=instance, name="art", defaults={"color": "#f472b6"})
            Label.objects.get_or_create(project=instance, name="code", defaults={"color": "#60a5fa"})
            Label.objects.get_or_create(project=instance, name="bug", defaults={"color": "#ef4444"})
            Label.objects.get_or_create(project=instance, name="feature", defaults={"color": "#22c55e"})

    transaction.on_commit(_provision)
