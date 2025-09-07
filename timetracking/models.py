from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.utils import timezone
from django.utils.text import slugify


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TrackedProject(TimestampedModel):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=255, unique=True, db_index=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)

    external_ref = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="External project id/slug (no FK).",
    )

    source_project_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Original projects.Project id (no FK).",
    )

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["title"], name="tt_idx_proj_title"),
            models.Index(fields=["is_active", "title"], name="tt_idx_proj_active_title"),
        ]

    def __str__(self) -> str:
        return self.title

    def _ensure_slug(self) -> None:
        if self.slug:
            return
        base = slugify(self.title) or "project"
        base = base[:120]
        for n in range(1, 50):
            cand = base if n == 1 else f"{base}-{n}"
            self.slug = cand
            try:
                super().save(force_insert=self._state.adding)
                return
            except IntegrityError:
                # Unique collision; try the next suffix.
                continue
        raise IntegrityError("Could not generate a unique slug for TrackedProject.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug and self._state.adding:
            self._ensure_slug()
            return
        super().save(*args, **kwargs)


class TrackedTask(TimestampedModel):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    project = models.ForeignKey(TrackedProject, on_delete=models.CASCADE, related_name="tasks")

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=255, db_index=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)

    external_ref = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="External task id/slug (no FK).",
    )

    source_task_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Original projects.Task id (no FK).",
    )

    class Meta:
        ordering = ["title", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "slug"], name="tt_uq_task_slug_per_project"),
            models.UniqueConstraint(fields=["project", "external_ref"], name="tt_uq_task_extref_per_project"),
        ]
        indexes = [
            models.Index(fields=["project", "title"], name="tt_idx_task_proj_title"),
            models.Index(fields=["project", "slug"], name="tt_idx_task_proj_slug"),
            models.Index(fields=["is_active", "project"], name="tt_idx_task_active_proj"),
        ]

    def __str__(self) -> str:
        return f"{self.project.title} — {self.title}"

    def _ensure_slug(self) -> None:
        if self.slug:
            return
        base = slugify(self.title) or "task"
        base = base[:180]
        for n in range(1, 50):
            cand = base if n == 1 else f"{base}-{n}"
            self.slug = cand
            try:
                super().save(force_insert=self._state.adding)
                return
            except IntegrityError:
                continue
        raise IntegrityError("Could not generate a unique slug for TrackedTask within project.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug and self._state.adding:
            self._ensure_slug()
            return
        super().save(*args, **kwargs)


class TimeEntry(TimestampedModel):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    project = models.ForeignKey(TrackedProject, on_delete=models.PROTECT, related_name="entries")
    task = models.ForeignKey(TrackedTask, on_delete=models.PROTECT, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_entries")

    work_date = models.DateField(default=timezone.localdate, db_index=True)
    duration_minutes = models.PositiveIntegerField(help_text="Exact minutes.")
    billable = models.BooleanField(default=False, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        indexes = [
            models.Index(fields=["project", "work_date"], name="tt_idx_entry_project_date"),
            models.Index(fields=["task", "work_date"], name="tt_idx_entry_task_date"),
            models.Index(fields=["user", "work_date"], name="tt_idx_entry_user_date"),
            models.Index(fields=["billable", "work_date"], name="tt_idx_entry_billable_date"),
            models.Index(fields=["project", "task", "work_date"], name="tt_idx_entry_proj_task_date"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(duration_minutes__gt=0), name="tt_chk_positive_minutes"),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.project.title}/{self.task.title} · {self.work_date} · {self.duration_minutes}m"

    def clean(self) -> None:
        if self.task_id and self.project_id and self.task.project_id != self.project_id:
            raise ValidationError({"task": "Task does not belong to the selected project."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.task_id and (not self.project_id or self.task.project_id != self.project_id):
            self.project_id = self.task.project_id
        super().save(*args, **kwargs)

    @property
    def hours(self) -> float:
        return self.duration_minutes / 60.0
