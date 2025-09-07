from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TrackedProject(TimestampedModel):
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True, blank=True)
    is_active = models.BooleanField(default=True)
    external_ref = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Optional reference to external project id/slug (no FK)."
    )

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:50] or "project"
            slug = base
            n = 2
            while TrackedProject.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class TrackedTask(TimestampedModel):
    project = models.ForeignKey(TrackedProject, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=255, db_index=True, blank=True)
    is_active = models.BooleanField(default=True)
    external_ref = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Optional reference to external task id/slug (no FK)."
    )

    class Meta:
        ordering = ["project__title", "title"]
        constraints = [
            models.UniqueConstraint(fields=["project", "title"], name="uniq_task_per_project_title"),
        ]
        indexes = [
            models.Index(fields=["project", "title"], name="idx_task_proj_title"),
        ]

    def __str__(self) -> str:
        return f"{self.project.title} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:60] or "task"
            cand = base
            n = 2
            while TrackedTask.objects.filter(project=self.project, slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base}-{n}"
                n += 1
            self.slug = cand
        super().save(*args, **kwargs)


class TimeEntry(TimestampedModel):
    project = models.ForeignKey(TrackedProject, on_delete=models.CASCADE, related_name="entries")
    task = models.ForeignKey(TrackedTask, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_entries")

    work_date = models.DateField(default=timezone.now)
    duration_minutes = models.PositiveIntegerField(help_text="Exact minutes; reports can display rounded")
    billable = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        indexes = [
            models.Index(fields=["project", "work_date"], name="idx_entry_project_date"),
            models.Index(fields=["task", "work_date"], name="idx_entry_task_date"),
            models.Index(fields=["user", "work_date"], name="idx_entry_user_date"),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.project.title}/{self.task.title} · {self.work_date} · {self.duration_minutes}m"

    def clean(self):
        # Defensive: ensure consistency between project and task
        if self.task and self.project and self.task.project_id != self.project_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({"task": "Task does not belong to selected project."})

    def save(self, *args, **kwargs):
        # Auto-align project to task's project if not provided (or mismatched)
        if self.task and (not self.project_id or self.task.project_id != self.project_id):
            self.project_id = self.task.project_id
        super().save(*args, **kwargs)