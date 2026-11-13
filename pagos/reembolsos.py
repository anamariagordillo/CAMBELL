"""Reembolsos simulados de pagos completados (ReembolsoService.java)."""
from django.utils import timezone

from mensajeria.servicios import crear_notificacion

from .models import Pago, Reembolso
from .servicios import ErrorPago


def listar_todos():
    return Reembolso.objects.select_related(
        "pago", "pago__cliente", "pago__solicitud"
    ).order_by("-fecha", "-id")


def pagos_completados():
    return (
        Pago.objects.filter(estado=Pago.Estado.COMPLETADO)
        .select_related("solicitud", "cliente", "trabajador")
        .order_by("-fecha_pago", "-id")
    )


def pagos_reembolsados():
    """Ids de los pagos que ya tienen un reembolso."""
    return set(Reembolso.objects.values_list("pago_id", flat=True))


def reembolsar(pago_id, motivo=None):
    """Marca el pago como reembolsado y avisa al cliente.

    El dinero no se mueve de verdad: igual que el resto de pagos, es una simulación.
    """
    try:
        pago = Pago.objects.select_related(
            "solicitud", "cliente", "trabajador"
        ).get(pk=pago_id)
    except Pago.DoesNotExist:
        raise ErrorPago("Pago no encontrado")

    if Reembolso.objects.filter(pago=pago).exists():
        raise ErrorPago("Este pago ya fue reembolsado")
    if pago.estado != Pago.Estado.COMPLETADO:
        raise ErrorPago("Solo se pueden reembolsar pagos completados.")

    reembolso = Reembolso.objects.create(
        pago=pago,
        monto=pago.monto_total,
        motivo=(motivo or "").strip()[:1000] or "Disputa justificada",
        estado=Reembolso.Estado.PROCESADO,
        fecha=timezone.now(),
    )

    pago.estado = Pago.Estado.REEMBOLSADO
    pago.save(update_fields=["estado"])

    crear_notificacion(
        pago.cliente, "PAGO",
        f"Se inició un reembolso de $ {reembolso.monto} por el servicio: "
        f"{pago.solicitud.descripcion}.",
        pago.solicitud,
    )
    return reembolso
