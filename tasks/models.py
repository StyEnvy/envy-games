from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Validators
HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$",
    message="Color must be a hex value like #RRGGBB or #RRGGBBAA.",
)


class Board(models.Model):
    KIND_CHOICES = [("task", "Task"), ("roadmap", "Roadmap")]
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="boards")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    is_default = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1000)

    class Meta:
        indexes = [models.Index(fields=["project", "kind", "order"])]

    def clean(self):
        if self.is_default and Board.objects.filter(
            project=self.project, kind=self.kind, is_default=True
        ).exclude(pk=self.pk).exists():
            raise ValidationError("Only one default board per (project, kind) is allowed.")

    def __str__(self):
        return f"{self.project} / {self.name}"


class Column(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    name = models.CharField(max_length=120)
    wip_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=1000)

    class Meta:
        unique_together = [("board", "name")]
        ordering = ["order"]

    def __str__(self):
        return f"{self.board} / {self.name}"

    # Soft WIP (indicator only)
    def wip_exceeded(self) -> bool:
        if not self.wip_limit:
            return False
        return self.cards.count() > self.wip_limit


class Label(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="labels")
    name = models.CharField(max_length=60)
    color = models.CharField(max_length=9, blank=True, validators=[HEX_COLOR_VALIDATOR])

    class Meta:
        unique_together = [("project", "name")]

    def __str__(self):
        return f"{self.project.slug}:{self.name}"


class Task(models.Model):
    """Underlying work item (idea/epic/task). Placed on boards via Card."""
    KIND_CHOICES = [("task", "Task"), ("idea", "Idea"), ("epic", "Epic")]
    PRIORITY_CHOICES = [(1, "P1"), (2, "P2"), (3, "P3")]
    STATUS_CHOICES = [("todo", "To Do"), ("doing", "Doing"), ("review", "Review"), ("done", "Done")]

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="tasks")

    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default="task")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)

    # execution fields (Task board)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, blank=True)
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, null=True, blank=True)
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")

    # planning fields (Roadmap board, ICE)
    impact = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    confidence = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    ease = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    score = models.PositiveIntegerField(default=0)  # impact*confidence*ease

    # optional hierarchy (epic -> tasks)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    labels = models.ManyToManyField(Label, blank=True, related_name="tasks")

    order_hint = models.PositiveIntegerField(default=1000)  # fallback sort when not on a board
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["project", "kind", "order_hint"])]
        constraints = [
            # ICE ranges when provided (NULLs allowed)
            models.CheckConstraint(
                check=models.Q(impact__isnull=True) | models.Q(impact__gte=1, impact__lte=5),
                name="task_impact_1_5_or_null",
            ),
            models.CheckConstraint(
                check=models.Q(confidence__isnull=True) | models.Q(confidence__gte=1, confidence__lte=5),
                name="task_confidence_1_5_or_null",
            ),
            models.CheckConstraint(
                check=models.Q(ease__isnull=True) | models.Q(ease__gte=1, ease__lte=5),
                name="task_ease_1_5_or_null",
            ),
        ]

    def validate_for_board_kind(self, kind: str):
        if kind == "task":
            if not self.status or self.priority is None:
                raise ValidationError("Task board placement requires status and priority.")
        if kind == "roadmap":
            if not all(v is not None for v in [self.impact, self.confidence, self.ease]):
                raise ValidationError("Roadmap placement requires impact, confidence, and ease (1–5).")

    def clean(self):
        # Enforce parent and child belong to the same project
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError("Task cannot be its own parent.")
            if self.parent and self.parent.project_id != self.project_id:
                raise ValidationError("Parent task must belong to the same project.")

            # Prevent ancestry cycles
            seen = set()
            current = self.parent
            # Limit depth traversal defensively
            for _ in range(0, 256):
                if current is None:
                    break
                if current.pk == self.pk or current.pk in seen:
                    raise ValidationError("Cyclic parent relationship detected.")
                seen.add(current.pk)
                current = current.parent

        return super().clean()

    def save(self, *args, **kwargs):
        if self.kind in {"idea", "epic"}:
            i = self.impact or 0
            c = self.confidence or 0
            e = self.ease or 0
            self.score = i * c * e
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class CardQuerySet(models.QuerySet):
    def with_joins(self):
        return (
            self.select_related("item", "board", "column", "project")
            .prefetch_related("item__labels")
        )


class CardManager(models.Manager):
    def get_queryset(self):
        # Default to eager-loading to avoid N+1 in common board views
        return CardQuerySet(self.model, using=self._db).with_joins()

    def with_joins(self):
        return self.get_queryset().with_joins()


class Card(models.Model):
    """Placement of a Task on a specific Board/Column (supports multiple placements)."""
    item = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="cards")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="cards")
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="cards")
    column = models.ForeignKey(Column, on_delete=models.PROTECT, related_name="cards")
    order = models.PositiveIntegerField(default=1000)

    # Optional roadmap metadata (display-only)
    version_label = models.CharField(max_length=64, blank=True)  # e.g., "0.4.0", "Alpha", "Q4"

    objects = CardManager()

    class Meta:
        indexes = [models.Index(fields=["project", "board", "column", "order"])]
        constraints = [
            models.UniqueConstraint(fields=["item", "board"], name="uniq_item_per_board"),
        ]

    def clean(self):
        if self.board and self.project_id != self.board.project_id:
            raise ValidationError("Card.project must equal Board.project.")
        if self.column and self.column.board_id != self.board_id:
            raise ValidationError("Card.column must belong to Card.board.")
        if self.item and self.board:
            self.item.validate_for_board_kind(self.board.kind)

    def move_to(self, *, column: "Column | None" = None, order: int | None = None):
        if column and column.board_id != self.board_id:
            raise ValidationError("Cannot move card to a column on a different board.")
        if column:
            self.column = column
        if order is not None:
            self.order = order
        self.full_clean()
        self.save()

    def __str__(self):
        return f"{self.item.title} @ {self.board.name} / {self.column.name}"

    def __str__(self):
        return f"{self.item.title} @ {self.board.name} / {self.column.name}"


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1000)

    def __str__(self):
        return self.title


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.created_by} on {self.task_id}"


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/%Y/%m/")
    size_bytes = models.BigIntegerField()
    mime_type = models.CharField(max_length=120)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} ({self.size_bytes} bytes)"


# Service: make a board the sole default for its (project, kind)
def make_default_board(board_id: int) -> Board:
    """
    Atomically make the given board the sole default in its (project, kind) group.
    Uses SELECT ... FOR UPDATE to avoid races. Keep this in a service layer.
    """
    with transaction.atomic():
        # Lock the target board row
        board = (
            Board.objects.select_for_update()
            .select_related("project")
            .get(pk=board_id)
        )

        # Lock peer boards in same (project, kind) group and clear their defaults
        peers = (
            Board.objects.select_for_update()
            .filter(project=board.project, kind=board.kind, is_default=True)
            .exclude(pk=board.pk)
        )
        if peers.exists():
            peers.update(is_default=False)

        # Set this board as default
        board.is_default = True
        board.full_clean()
        board.save(update_fields=["is_default"])
        return board
