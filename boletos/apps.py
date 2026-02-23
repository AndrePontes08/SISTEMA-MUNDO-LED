from django.apps import AppConfig


class BoletoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "boletos"
    verbose_name = "Sistema de Boletos"

    def ready(self):
        """Executado quando o app está pronto"""
        pass

