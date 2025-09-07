from django.apps import AppConfig

class TimetrackingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "timetracking"

    def ready(self):
        # Import signals to ensure they register
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Do not hard-crash app on import-time issues
            pass