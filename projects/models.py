from django.conf import settings
from django.db import models, transaction
from django.db.models import Max, UniqueConstraint
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify


SLUG_MAX_TRIES = 50
POSITION_STEP = 100


def unique_slugify(instance, base_value, slug_field_name="slug"):
    """
 Based on `base_value`, generate a unique slug for `instance`.
 Appends -2, -3, ... if needed. Bounded by SLUG_MAX_TRIES.
    """
    base_slug = slugify(base_value)[:50] or "project"
    Model = instance.__class__
    slug_field = slug_field_name
    slug = base_slug
    n = 2
    while Model.objects.filter(**{slug_field: slug}).exclude(pk=instance.pk).exists() and n <= SLUG_MAX_TRIES:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


class Project(models.Model):
    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("active", "Active"),
        ("hold", "On Hold"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    version = models.CharField(max_length=20, default="0.1.0")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planning")
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Only handle slug; avoid creating related rows here
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        else:
            # Keep slug unique if title change introduces a collision
            self.slug = unique_slugify(self, self.slug)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("projects:detail", kwargs={"slug": self.slug})


class Board(models.Model):
    BOARD_TYPE_CHOICES = [
        ("tasks", "Tasks"),
        ("roadmap", "Roadmap"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="boards")
    name = models.CharField(max_length=100)
    board_type = models.CharField(max_length=20, choices=BOARD_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["project", "board_type"],
                name="uniq_project_boardtype",
            )
        ]

    def __str__(self):
        return f"{self.project.title} - {self.name}"


class Column(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            UniqueConstraint(
                fields=["board", "position"],
                name="uniq_board_position",
            )
        ]

    def __str__(self):
        return f"{self.board.name} - {self.name}"


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ("feature", "Feature"),
        ("bug", "Bug"),
        ("task", "Task"),
        ("idea", "Idea"),
    ]

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default="task")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    column = models.ForeignKey(Column, on_delete=models.PROTECT, related_name="tasks")
    # Use nullable position; None triggers "append to end"
    position = models.PositiveIntegerField(null=True, blank=True)
    is_roadmap_item = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "-created_at"]
        constraints = [
            UniqueConstraint(
                fields=["column", "position"],
                name="uniq_column_task_position",
                violation_error_message="A task already occupies this position in the column.",
            )
        ]

    def __str__(self):
        return self.title

    def _next_position_in_column(self):
        # Lock tasks in this column to avoid race conditions (MariaDB/InnoDB)
        qs = Task.objects.select_for_update().filter(column=self.column)
        max_pos = qs.aggregate(maxp=Max("position"))["maxp"]
        return (max_pos or 0) + POSITION_STEP

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.position is None:
                self.position = self._next_position_in_column()
            super().save(*args, **kwargs)

    def convert_to_task(self):
        """
        Convert a roadmap item to a regular task.
        Moves it to the Tasks board's first column by position.
        """
        if not self.is_roadmap_item:
            return False

        tasks_board = self.project.boards.filter(board_type="tasks").first()
        if not tasks_board:
            return False

        first_column = tasks_board.columns.order_by("position").first()
        if not first_column:
            return False

        self.column = first_column
        self.is_roadmap_item = False
        self.position = None  # trigger re-append at end
        self.save()
        return True


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="task_attachments/%Y/%m/%d/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.task.title} - {self.file.name}"

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name)


# --- default board/column setup via post_save to avoid side effects in save() ---

# NOTE: keep constant names to avoid refactors elsewhere.
DEFAULT_KANBAN_COLUMNS = [
    ("To Do", 0),
    ("In Progress", 100),
    ("Review", 200),
    ("Done", 300),
]
DEFAULT_ROADMAP_COLUMNS = [
    ("Ideas", 0),
    ("Planned", 100),
    ("Approved", 200),
    ("Rejected", 300),
]


@receiver(post_save, sender=Project)
def create_default_boards(sender, instance, created, **kwargs):
    """
    When a new Project is created, also create the default Tasks and Roadmap boards with columns.
    """
    if created:
        with transaction.atomic():
            tasks_board = Board.objects.create(
                project=instance,
                name="Tasks Board",
                board_type="tasks",
                is_active=True,
            )
            for col_name, position in DEFAULT_KANBAN_COLUMNS:
                Column.objects.create(board=tasks_board, name=col_name, position=position)

            roadmap_board = Board.objects.create(
                project=instance,
                name="Roadmap",
                board_type="roadmap",
                is_active=True,
            )
            for col_name, position in DEFAULT_ROADMAP_COLUMNS:
                Column.objects.create(board=roadmap_board, name=col_name, position=position)
