from __future__ import annotations

from typing import Optional

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction


def _project_active_from_status(status: Optional[str]) -> bool:
    return status != "archived"


@transaction.atomic
def on_project_saved(sender, instance, **kwargs):
    from .models import TrackedProject

    is_active = _project_active_from_status(getattr(instance, "status", None))
    defaults = {
        "title": instance.title,
        "is_active": is_active,
        "external_ref": getattr(instance, "slug", None),
    }

    try:
        tp, created = TrackedProject.objects.get_or_create(
            source_project_id=instance.pk,
            defaults=defaults,
        )
    except IntegrityError:
        tp = TrackedProject.objects.select_for_update().get(source_project_id=instance.pk)
        created = False

    if not created:
        update_fields = []
        if tp.title != instance.title:
            tp.title = instance.title
            update_fields.append("title")
        ext = getattr(instance, "slug", None)
        if tp.external_ref != ext:
            tp.external_ref = ext
            update_fields.append("external_ref")
        if tp.is_active != is_active:
            tp.is_active = is_active
            update_fields.append("is_active")

        if update_fields:
            tp.save(update_fields=update_fields)


@transaction.atomic
def on_project_deleted(sender, instance, **kwargs):
    from .models import TrackedProject, TrackedTask

    qs = TrackedProject.objects.filter(source_project_id=instance.pk)
    proj_id = qs.values_list("id", flat=True).first()
    qs.update(is_active=False)
    if proj_id:
        TrackedTask.objects.filter(project_id=proj_id).update(is_active=False)


@transaction.atomic
def on_task_saved(sender, instance, **kwargs):
    from .models import TrackedProject, TrackedTask

    Project = django_apps.get_model("projects", "Project")

    parent_project = getattr(instance, "project", None)
    if parent_project is None and hasattr(instance, "project_id"):
        parent_project = Project.objects.filter(pk=instance.project_id).first()
    if not parent_project:
        return

    # Ensure parent mirror exists / is current
    on_project_saved(Project, parent_project)
    tp = TrackedProject.objects.select_for_update().filter(source_project_id=parent_project.pk).first()
    if not tp:
        return

    is_active = _project_active_from_status(getattr(parent_project, "status", None))
    defaults = {
        "project": tp,
        "title": instance.title,
        "is_active": is_active,
        "external_ref": str(instance.pk),
    }

    try:
        tt, created = TrackedTask.objects.get_or_create(
            source_task_id=instance.pk,
            defaults=defaults,
        )
    except IntegrityError:
        tt = TrackedTask.objects.select_for_update().get(source_task_id=instance.pk)
        created = False

    if not created:
        update_fields = []
        if tt.project_id != tp.id:
            tt.project = tp
            update_fields.append("project")
        if tt.title != instance.title:
            tt.title = instance.title
            update_fields.append("title")
        ext = str(instance.pk)
        if tt.external_ref != ext:
            tt.external_ref = ext
            update_fields.append("external_ref")
        desired_active = is_active
        if tt.is_active != desired_active:
            tt.is_active = desired_active
            update_fields.append("is_active")

        if update_fields:
            tt.save(update_fields=update_fields)


@transaction.atomic
def on_task_deleted(sender, instance, **kwargs):
    from .models import TrackedTask

    TrackedTask.objects.filter(source_task_id=instance.pk).update(is_active=False)
