"""Cobro de un servicio completado (la parte de PagoService.pagar de la versión Java).

El pago es SIMULADO: no hay pasarela real. Se calcula la comisión de Cambell (3 %), el
neto que recibirá el trabajador, y el pago queda COMPLETADO.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from mensajeria.servicios import crear_notificacion
from solicitudes.models import EstadoSolicitud, Solicitud

from . import servicios
from .models import Pago
from .servicios import ErrorPago

CENTAVOS = Decimal("0.01")


def tasa_comision():
    return Decimal(str(settings.COMISION_PLATAFORMA))


def porcentaje_comision():
    """Para mostrarlo en pantalla: '3' (sin ceros sobrantes; con 0,035 daría '3.5')."""
    return format((tasa_comision() * 100).normalize(), "f")


def calcular_comision(monto):
    """Devuelve (comisión, neto) redondeados al centavo, con el redondeo de siempre (0,5 sube)."""
    monto = Decimal(monto)
    comision = (monto * tasa_comision()).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    neto = (monto - comision).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return comision, neto


@transaction.atomic
def pagar(solicitud_id, metodo_id, cliente):
    """El cliente paga una solicitud COMPLETADA. Si algo no cumple, lanza ErrorPago."""
    try:
        solicitud = Solicitud.objects.select_related("cliente", "trabajador").get(pk=solicitud_id)
    except Solicitud.DoesNotExist:
        raise ErrorPago("Solicitud no encontrada")

    if solicitud.cliente_id != cliente.id:
        raise ErrorPago("Solo el cliente que solicitó el servicio puede pagarlo.")

    existente = Pago.objects.filter(solicitud=solicitud).first()
    if existente and existente.estado != Pago.Estado.FALLIDO:
        raise ErrorPago("Esta solicitud ya fue pagada")

    if solicitud.estado != EstadoSolicitud.COMPLETADA:
        raise ErrorPago("El servicio debe estar completado para poder pagarlo")

    monto = solicitud.precio_ofertado
    if monto is None or monto <= 0:
        raise ErrorPago("Esta solicitud no tiene un precio ofertado, así que no se puede cobrar.")

    # Solo se aceptan métodos del propio cliente (en Java cualquier id valía).
    metodo = servicios.buscar_metodo_del_cliente(metodo_id, cliente)
    if metodo is None:
        raise ErrorPago("Selecciona un método de pago válido.")
    if metodo.tipo == metodo.Tipo.TARJETA and not servicios.es_tarjeta_vigente(
        metodo.mes_vencimiento, metodo.anio_vencimiento
    ):
        raise ErrorPago("La tarjeta seleccionada está vencida. Actualízala o agrega otra.")

    comision, neto = calcular_comision(monto)
    try:
        with transaction.atomic():
            pago, _ = Pago.objects.update_or_create(
                solicitud=solicitud,
                defaults={
                    "cliente": solicitud.cliente,
                    "trabajador": solicitud.trabajador,
                    "monto_total": monto,
                    "comision": comision,
                    "neto_trabajador": neto,
                    "metodo_pago": metodo,
                    "estado": Pago.Estado.COMPLETADO,
                    "fecha_pago": timezone.now(),
                },
            )
    except IntegrityError:
        # Dos pagos al mismo tiempo: el segundo choca con la regla "un pago por solicitud".
        raise ErrorPago("Esta solicitud ya fue pagada")

    if solicitud.trabajador is not None:
        crear_notificacion(
            solicitud.trabajador, "PAGO",
            f'El cliente pagó el servicio "{solicitud.descripcion}". '
            f"Recibirás $ {neto:.2f} (ya descontada la comisión).",
            solicitud,
        )
    return pago