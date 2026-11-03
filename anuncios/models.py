from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class Anuncio(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PUBLICADO = "PUBLICADO", "Publicado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(max_length=1000)
    imagen = models.FileField(
        upload_to="anuncios/", null=True, blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    motivo_rechazo = models.CharField(max_length=500, blank=True)
    aliado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="anuncios"
    )
    fecha_creacion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "anuncios"
        ordering = ["-fecha_creacion"]
