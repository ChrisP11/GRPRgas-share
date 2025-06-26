from django.apps import AppConfig


class GrprConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'GRPR'

class GRPRConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "GRPR"

    def ready(self):
        # Import signals so receivers are registered
        from . import signals   # noqa: F401