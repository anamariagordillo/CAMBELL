"""Ingresos del trabajador: lo que ha recibido, y los filtros por fechas del reporte."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import Pago
from .servicios import ErrorPago

CENTAVOS = Decimal("0.01")


def historial_trabajador(trabajador):
    """Todos los pagos del trabajador (de cualquier estado), del más reciente al más antiguo."""
    return (
        Pago.objects.filter(trabajador=trabajador)
        .select_related("solicitud", "cliente")
        .order_by("-fecha_pago", "-id")
    )


def ingresos_trabajador(trabajador):
    """Total NETO acumulado: solo cuentan los pagos COMPLETADOS (no los reembolsados)."""
    total = Pago.objects.filter(
        trabajador=trabajador, estado=Pago.Estado.COMPLETADO
    ).aggregate(total=Sum("neto_trabajador"))["total"]
    return (total or Decimal("0")).quantize(CENTAVOS)


def pagos_en_rango(trabajador, desde=None, hasta=None):
    """Pagos COMPLETADOS entre dos fechas (ambas incluidas, el día 'hasta' completo)."""
    pagos = (
        Pago.objects.filter(
            trabajador=trabajador, estado=Pago.Estado.COMPLETADO, fecha_pago__isnull=False
        )
        .select_related("solicitud", "cliente")
    )
    if desde is not None:
        pagos = pagos.filter(fecha_pago__gte=timezone.make_aware(datetime.combine(desde, time.min)))
    if hasta is not None:
        siguiente = hasta + timedelta(days=1)
        pagos = pagos.filter(fecha_pago__lt=timezone.make_aware(datetime.combine(siguiente, time.min)))
    return pagos.order_by("-fecha_pago", "-id")


def rango_permitido(trabajador, hoy=None):
    """Del día en que se registró el trabajador hasta hoy."""
    hoy = hoy or timezone.localdate()
    if trabajador.fecha_registro:
        return timezone.localtime(trabajador.fecha_registro).date(), hoy
    return hoy, hoy


def normalizar_rango(desde, hasta, inicio, hoy):
    """Ajusta las fechas al rango permitido; si quedan al revés, lanza ErrorPago."""
    if desde and desde < inicio:
        desde = inicio
    if desde and desde > hoy:
        desde = hoy
    if hasta and hasta > hoy:
        hasta = hoy
    if hasta and hasta < inicio:
        hasta = inicio
    if desde and hasta and desde > hasta:
        raise ErrorPago(
            "El rango de fechas es inválido: la fecha 'desde' no puede ser posterior a 'hasta'."
        )
    return desde, hasta