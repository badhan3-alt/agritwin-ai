from django.apps import AppConfig


class NotebookConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notebook"

    def ready(self):
        from . import signals  # noqa: F401
