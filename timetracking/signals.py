from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import TimeEntry


@receiver(pre_save, sender=TimeEntry)
def align_entry_project(sender, instance: TimeEntry, **kwargs):
    # Safety: ensure project aligns to task's project
    if instance.task and (not instance.project_id or instance.project_id != instance.task.project_id):
        instance.project = instance.task.project