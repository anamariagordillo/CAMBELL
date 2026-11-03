from django.conf import settings
from django.db import models
from django.utils import timezone


class MetodoPago(models.Model):
    class Tipo(models.TextChoices):
        TARJETA = "TARJETA", "Tarjeta"
        NEQUI = "NEQUI", "Nequi"
        EFECTIVO = "EFECTIVO", "Efectivo"

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="metodos_pago"
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    titular = models.CharField(max_length=100)
    # Solo se guarda el numero enmascarado (por ejemplo **** 1234), nunca el completo.
    numero_enmascarado = models.CharField(max_length=30)
    mes_vencimiento = models.PositiveSmallIntegerField(null=True, blank=True)
    anio_vencimiento = models.PositiveSmallIntegerField(null=True, blank=True)
    fecha_registro = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "metodos_pago"


class Pago(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        COMPLETADO = "COMPLETADO", "Completado"
        FALLIDO = "FALLIDO", "Fallido"
        REEMBOLSADO = "REEMBOLSADO", "Reembolsado"

    class EstadoTransferencia(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        TRANSFERIDO = "TRANSFERIDO", "Transferido"
        FALLIDO = "FALLIDO", "Fallido"

    solicitud = models.OneToOneField(
        "solicitudes.Solicitud", on_delete=models.CASCADE, related_name="pago"
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pagos_realizados"
    )
    trabajador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pagos_recibidos"
    )
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    comision = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    neto_trabajador = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metodo_pago = models.ForeignKey(
        MetodoPago, on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos"
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha_pago = models.DateTimeField(null=True, blank=True)
    estado_transferencia = models.CharField(
        max_length=12, choices=EstadoTransferencia.choices, default=EstadoTransferencia.PENDIENTE
    )
    fecha_transferencia = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pagos"


class Reembolso(models.Model):
    class Estado(models.TextChoices):
        PROCESADO = "PROCESADO", "Procesado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    pago = models.OneToOneField(Pago, on_delete=models.CASCADE, related_name="reembolso")
    monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    motivo = models.CharField(max_length=1000)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PROCESADO)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "reembolsos"


class Suscripcion(models.Model):
    class Plan(models.TextChoices):
        PREMIUM = "PREMIUM", "Premium"

    trabajador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suscripciones"
    )
    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.PREMIUM)
    activa = models.BooleanField(default=False)
    renovacion_automatica = models.BooleanField(default=True)
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_vencimiento = models.DateTimeField()

    class Meta:
        db_table = "suscripciones"
