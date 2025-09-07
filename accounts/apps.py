from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Ensure signal receivers are registered in all runtimes
        from . import models  # noqa: F401
