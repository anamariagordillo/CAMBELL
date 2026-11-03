from django.conf import settings
from django.db import models
from django.utils import timezone


class ReporteSeguridad(models.Model):
    class Estado(models.TextChoices):
        EN_REVISION = "EN_REVISION", "En revisión"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"
        DESCARTADO = "DESCARTADO", "Descartado"

    reportante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reportes_hechos"
    )
    reportado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reportes_recibidos"
    )
    motivo = models.CharField(max_length=1000)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.EN_REVISION)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "reportes_seguridad"
        ordering = ["-fecha"]
