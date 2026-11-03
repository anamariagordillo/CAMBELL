from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class CategoriaServicio(models.TextChoices):
    PLOMERIA = "PLOMERIA", "Plomería"
    ELECTRICIDAD = "ELECTRICIDAD", "Electricidad"
    CERRAJERIA = "CERRAJERIA", "Cerrajería"
    ELECTRODOMESTICOS = "ELECTRODOMESTICOS", "Electrodomésticos"
    AIRE_ACONDICIONADO = "AIRE_ACONDICIONADO", "Aire acondicionado / Refrigeración"
    CARPINTERIA = "CARPINTERIA", "Carpintería"


class EstadoSolicitud(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    ACEPTADA = "ACEPTADA", "Aceptada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    COMPLETADA = "COMPLETADA", "Completada"
    CANCELADA = "CANCELADA", "Cancelada"
    NO_ATENDIDA = "NO_ATENDIDA", "No atendida"


class Urgencia(models.TextChoices):
    BAJA = "BAJA", "Baja"
    MEDIA = "MEDIA", "Media"
    ALTA = "ALTA", "Alta"


class Solicitud(models.Model):
    descripcion = models.TextField()
    zona = models.CharField(max_length=200, blank=True)
    localidad = models.CharField(max_length=100, blank=True)
    barrio = models.CharField(max_length=100, blank=True)
    categoria = models.CharField(max_length=30, choices=CategoriaServicio.choices)
    precio_ofertado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    estado = models.CharField(
        max_length=20, choices=EstadoSolicitud.choices, default=EstadoSolicitud.PENDIENTE
    )

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="solicitudes_como_cliente"
    )
    trabajador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitudes_como_trabajador",
    )

    calificacion = models.PositiveSmallIntegerField(null=True, blank=True)
    comentario = models.CharField(max_length=500, blank=True)
    evidencia = models.FileField(upload_to="evidencias/", null=True, blank=True)
    codigo_finalizacion = models.CharField(max_length=10, blank=True)
    motivo_rechazo = models.CharField(max_length=500, blank=True)
    metodo_pago = models.ForeignKey(
        "pagos.MetodoPago", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitudes",
    )
    direccion_especifica = models.CharField(max_length=255, blank=True)

    # Campos que alimenta la IA de recomendacion (fases siguientes)
    urgencia = models.CharField(max_length=10, choices=Urgencia.choices, default=Urgencia.MEDIA)
    resumen_ia = models.TextField(blank=True)
    confianza_ia = models.FloatField(null=True, blank=True)

    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True)
    fecha_ultima_reasignacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "solicitudes"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Solicitud #{self.pk} ({self.get_categoria_display()})"


class Calificacion(models.Model):
    solicitud = models.OneToOneField(
        Solicitud, on_delete=models.CASCADE, related_name="calificacion_detalle"
    )
    puntuacion = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "calificaciones"
