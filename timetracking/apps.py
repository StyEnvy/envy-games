from django.apps import AppConfig
from django.apps import apps as django_apps
from django.db.models.signals import post_save, post_delete


class TimetrackingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "timetracking"

    def ready(self):
        from . import signals as tt_signals

        Project = django_apps.get_model("projects", "Project")
        Task = django_apps.get_model("projects", "Task")

        # Connect lazily after apps are loaded to avoid import cycles
        post_save.connect(tt_signals.on_project_saved, sender=Project, dispatch_uid="tt_project_saved")
        post_delete.connect(tt_signals.on_project_deleted, sender=Project, dispatch_uid="tt_project_deleted")
        post_save.connect(tt_signals.on_task_saved, sender=Task, dispatch_uid="tt_task_saved")
        post_delete.connect(tt_signals.on_task_deleted, sender=Task, dispatch_uid="tt_task_deleted")
