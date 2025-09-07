from django.core.management.base import BaseCommand, CommandError

from timetracking.utils import sync_from_source


class Command(BaseCommand):
    help = "Sync TrackedProject/TrackedTask from external Project/Task models using apps.get_model"

    def add_arguments(self, parser):
        parser.add_argument("--project-model", default="projects.Project")
        parser.add_argument("--task-model", default="projects.Task")

    def handle(self, *args, **options):
        project_model = options["project_model"]
        task_model = options["task_model"]
        try:
            result = sync_from_source(project_model, task_model)
        except Exception as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(
            f"Synced projects/tasks: {result}"
        ))