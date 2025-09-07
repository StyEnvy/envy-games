from django.conf import settings
from django.db import models, transaction
from django.db.models import UniqueConstraint

from .utils import unique_slugify, next_position_for_column

class Project(models.Model):
    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("active", "Active"),
        ("hold", "On Hold"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    PROJECT_TYPE_CHOICES = [
        ("game_unity", "Game - Unity"),
        ("game_ue", "Game - UE"),
        ("game_other", "Game - Other"),
        ("plugin", "Plugin"),
        ("mod", "Mod"),
        ("mcmod", "Minecraft Mod"),
        ("discord_bot", "Discord Bot"),
        ("software", "Software"),
        ("webapp", "Web/Webapp"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    version = models.CharField(max_length=20, default="0.1.0")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planning", db_index=True)
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES, default="software", db_index=True)
    description = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_projects",
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMembership",
        through_fields=("project", "user"),
        related_name="member_projects",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_type"]),
            models.Index(fields=["status", "project_type"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Only handle slug creation/uniqueness here
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        elif self.pk is None:
            # New instance with a manually set slug - ensure uniqueness
            self.slug = unique_slugify(self, self.slug)
        # For existing instances, only regenerate if there's a conflict
        elif Project.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
            self.slug = unique_slugify(self, self.slug)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("projects:detail", kwargs={"slug": self.slug})

    def user_can_view(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        # Django admin/staff can view
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        # Only PM or Developer may view
        try:
            from accounts.models import UserRole
            role = getattr(getattr(user, "profile", None), "role", None)
            return role in (UserRole.PROJECT_MANAGER, UserRole.DEVELOPER)
        except Exception:
            return False

    def user_can_edit(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        # Django admin/staff can edit
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        # Only PM may edit (developers cannot)
        try:
            from accounts.models import UserRole
            role = getattr(getattr(user, "profile", None), "role", None)
            return role == UserRole.PROJECT_MANAGER
        except Exception:
            return False

    def add_member(self, user, role=None, added_by=None):
        """
        Per-project roles removed; 'role' is ignored for backward compatibility.
        """
        membership, created = ProjectMembership.objects.get_or_create(
            project=self,
            user=user,
            defaults={"added_by": added_by or self.created_by},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save()
        return membership


class ProjectMembership(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    # Per-project role removed
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="memberships_added",
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project", "joined_at"]
        constraints = [
            UniqueConstraint(
                fields=["project", "user"],
                name="uq_projects_membership_project_user",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "user", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.project.title}"


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
        indexes = [
            models.Index(fields=["project", "is_roadmap_item"]),
            models.Index(fields=["assignee", "project"]),
            models.Index(fields=["column", "position"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title

    def _next_position_in_column(self):
        qs = Task.objects.select_for_update().filter(column=self.column)
        return next_position_for_column(qs)

    def clean(self):
        super().clean()
        # Auto-align task.project with column.board.project when a column is set
        if getattr(self, "column_id", None):
            board = getattr(self.column, "board", None)
            if board is not None:
                board_project_id = getattr(board, "project_id", None)
                if board_project_id and self.project_id != board_project_id:
                    self.project_id = board_project_id

    def save(self, *args, **kwargs):
        # Ensure project matches the column's board project even when not using ModelForms
        if getattr(self, "column_id", None):
            board = getattr(self.column, "board", None)
            board_project_id = getattr(board, "project_id", None) if board else None
            if board_project_id and self.project_id != board_project_id:
                self.project_id = board_project_id

        with transaction.atomic():
            if self.position is None:
                self.position = self._next_position_in_column()
            super().save(*args, **kwargs)

    def convert_to_task(self):
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
        self.position = None
        self.save()
        return True
