from django.apps import AppConfig

class TransporteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'transporte'
    def ready(self):
        from . import signals  # noqa  (registra las señales)