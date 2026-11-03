from django.conf import settings
from django.db import models
from django.utils import timezone


class Mensaje(models.Model):
    solicitud = models.ForeignKey(
        "solicitudes.Solicitud", on_delete=models.CASCADE, related_name="mensajes"
    )
    emisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mensajes_enviados"
    )
    contenido = models.TextField(max_length=2000)
    fecha = models.DateTimeField(default=timezone.now)
    leido = models.BooleanField(default=False)

    class Meta:
        db_table = "mensajes"
        ordering = ["fecha"]


class Notificacion(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones"
    )
    tipo = models.CharField(max_length=50)
    mensaje = models.CharField(max_length=500)
    leido = models.BooleanField(default=False)
    fecha = models.DateTimeField(default=timezone.now)
    solicitud = models.ForeignKey(
        "solicitudes.Solicitud", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notificaciones",
    )

    class Meta:
        db_table = "notificaciones"
        ordering = ["-fecha"]


class DispositivoNotificacion(models.Model):
    """Token FCM de un dispositivo del usuario (notificaciones push, fase 5)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dispositivos"
    )
    fcm_token = models.CharField(max_length=500)
    fecha_registro = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dispositivos_notificacion"
