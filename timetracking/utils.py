from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Tuple, Iterable

from django.apps import apps
from django.db import transaction
from django.utils.text import slugify

from .models import TrackedProject, TrackedTask


# ----- Duration helpers -----

def parse_duration_to_minutes(text: str) -> int:
    """Accepts "H:MM", "M", or "HHMM"-like shorthand; returns minutes (int).
    Examples: "1:30" -> 90, "45" -> 45, "2h" -> 120, "1h15" -> 75
    """
    s = (text or "").strip().lower().replace(" ", "")
    if not s:
        return 0
    # Explicit formats
    if ":" in s:
        h, m = s.split(":", 1)
        return int(h or 0) * 60 + int(m or 0)
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if "h" in s:
        h, m = s.split("h", 1)
        return int(h or 0) * 60 + int(m or 0)
    # Fallback raw minutes
    return int(s)


def round_for_display(minutes: int, step: int = 5) -> int:
    if step <= 1:
        return minutes
    # round to nearest step
    return int((minutes + step / 2) // step) * step


# ----- Week helpers -----

def iso_week_bounds(d: date | datetime) -> Tuple[date, date]:
    """Return (monday, next_monday) for the ISO week containing d."""
    if isinstance(d, datetime):
        d = d.date()
    monday = d - timedelta(days=(d.isoweekday() - 1))
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


# ----- Sync helpers (optional) -----
# Pull projects/tasks from an external app (defaults to 'projects.Project' and 'projects.Task').
# Uses apps.get_model to avoid hard FK/coupling. Stores only titles/slugs and optional external ids.

@transaction.atomic
def sync_from_source(
    project_model_label: str = "projects.Project",
    task_model_label: str = "projects.Task",
    project_filters: dict | None = None,
    task_filters: dict | None = None,
) -> dict:
    ProjectModel = apps.get_model(project_model_label)
    TaskModel = apps.get_model(task_model_label)

    p_qs = ProjectModel.objects.all()
    t_qs = TaskModel.objects.select_related("project").all()
    if project_filters:
        p_qs = p_qs.filter(**project_filters)
    if task_filters:
        t_qs = t_qs.filter(**task_filters)

    # Map existing for idempotent sync
    existing_projects = {p.external_ref: p for p in TrackedProject.objects.exclude(external_ref__isnull=True)}
    created_p = updated_p = 0

    # Upsert projects
    ref_to_tracked = {}
    for ext_p in p_qs:
        ext_ref = f"{ProjectModel._meta.label}:{ext_p.pk}"
        title = getattr(ext_p, "title", str(ext_p))
        tp = existing_projects.get(ext_ref)
        if tp:
            if tp.title != title or not tp.is_active:
                tp.title = title
                tp.is_active = True
                tp.save(update_fields=["title", "is_active", "updated_at"])
                updated_p += 1
        else:
            slug_base = slugify(title)[:50] or "project"
            tp = TrackedProject.objects.create(title=title, external_ref=ext_ref, slug=slug_base)
            created_p += 1
        ref_to_tracked[ext_p.pk] = tp

    # Upsert tasks
    existing_tasks: dict[tuple[int, str], TrackedTask] = {
        (t.project_id, t.title): t for t in TrackedTask.objects.select_related("project")
    }
    created_t = updated_t = 0
    for ext_t in t_qs:
        project = ref_to_tracked.get(ext_t.project_id)
        if not project:
            # Skip tasks whose project didn't pass filter
            continue
        title = getattr(ext_t, "title", str(ext_t))
        key = (project.id, title)
        tt = existing_tasks.get(key)
        if tt:
            if not tt.is_active:
                tt.is_active = True
                tt.save(update_fields=["is_active", "updated_at"])
                updated_t += 1
        else:
            TrackedTask.objects.create(project=project, title=title)
            created_t += 1

    return {
        "projects_created": created_p,
        "projects_updated": updated_p,
        "tasks_created": created_t,
        "tasks_updated": updated_t,
    }