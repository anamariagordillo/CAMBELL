"""Reglas de negocio de las solicitudes (equivale a SolicitudService.java)."""
import secrets

from django.db import transaction
from django.utils import timezone

from usuarios.models import EstadoVerificacion, Rol

from .models import EstadoSolicitud, Solicitud
from .observadores import EventoSolicitud, TipoEvento, notificador

# Sin letras ni números que se confunden entre sí (0/O, 1/I).
CARACTERES_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ErrorSolicitud(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle a la persona."""


def generar_codigo():
    """Código de 6 caracteres que el cliente le dicta al trabajador para cerrar el servicio."""
    return "".join(secrets.choice(CARACTERES_CODIGO) for _ in range(6))


def componer_zona(localidad, barrio):
    partes = [p.strip() for p in (barrio, localidad) if p and p.strip()]
    partes.append("Bogotá")
    return ", ".join(partes)


def _buscar(solicitud_id):
    try:
        return Solicitud.objects.select_related("cliente", "trabajador").get(pk=solicitud_id)
    except Solicitud.DoesNotExist:
        raise ErrorSolicitud("Solicitud no encontrada")


def _exigir_trabajador_aprobado(trabajador, accion):
    if trabajador is None or trabajador.rol != Rol.TRABAJADOR:
        raise ErrorSolicitud(f"Solo un trabajador puede {accion} solicitudes.")
    if trabajador.estado_verificacion != EstadoVerificacion.APROBADO:
        raise ErrorSolicitud(f"Debes tener la verificación APROBADA para {accion} solicitudes.")


def crear_solicitud(cliente, **datos):
    """Crea una solicitud PENDIENTE con su código de finalización."""
    solicitud = Solicitud(cliente=cliente, **datos)
    solicitud.estado = EstadoSolicitud.PENDIENTE
    solicitud.codigo_finalizacion = generar_codigo()
    solicitud.fecha_creacion = timezone.now()
    if not (solicitud.zona or "").strip():
        solicitud.zona = componer_zona(solicitud.localidad, solicitud.barrio)
    solicitud.save()
    notificador.notificar(EventoSolicitud(TipoEvento.CREADA, solicitud))
    return solicitud


@transaction.atomic
def aceptar(solicitud_id, trabajador):
    """Un trabajador aprobado toma la solicitud. Si dos la aceptan a la vez, solo gana uno."""
    _exigir_trabajador_aprobado(trabajador, "aceptar")

    # Una sola operación en la base de datos: "si sigue pendiente y sin dueño, asígnala".
    afectadas = Solicitud.objects.filter(
        pk=solicitud_id, estado=EstadoSolicitud.PENDIENTE, trabajador__isnull=True
    ).update(estado=EstadoSolicitud.ACEPTADA, trabajador=trabajador)

    if afectadas == 0:
        if not Solicitud.objects.filter(pk=solicitud_id).exists():
            raise ErrorSolicitud("Solicitud no encontrada")
        raise ErrorSolicitud("Esta solicitud ya no está disponible.")

    solicitud = _buscar(solicitud_id)
    notificador.notificar(EventoSolicitud(TipoEvento.ACEPTADA, solicitud))
    return solicitud


def rechazar(solicitud_id, motivo, trabajador):
    """El trabajador descarta una solicitud pendiente; vuelve a quedar disponible."""
    _exigir_trabajador_aprobado(trabajador, "rechazar")
    solicitud = _buscar(solicitud_id)
    if solicitud.estado != EstadoSolicitud.PENDIENTE:
        raise ErrorSolicitud("Esta solicitud ya no está disponible.")

    solicitud.motivo_rechazo = motivo or ""
    solicitud.estado = EstadoSolicitud.PENDIENTE
    solicitud.trabajador = None
    solicitud.save()
    notificador.notificar(EventoSolicitud(TipoEvento.REASIGNADA, solicitud))
    return solicitud


def cancelar(solicitud_id, cliente):
    solicitud = _buscar(solicitud_id)
    if solicitud.cliente_id != cliente.id:
        raise ErrorSolicitud("Solo el cliente que creó la solicitud puede cancelarla.")
    if solicitud.estado != EstadoSolicitud.PENDIENTE:
        raise ErrorSolicitud("Solo puedes cancelar solicitudes que aún no han sido aceptadas.")

    solicitud.estado = EstadoSolicitud.CANCELADA
    solicitud.save()
    return solicitud


def liberar(solicitud_id, trabajador):
    """El trabajador suelta un trabajo que había aceptado; vuelve a estar disponible."""
    solicitud = _buscar(solicitud_id)
    if solicitud.trabajador_id != trabajador.id:
        raise ErrorSolicitud("Solo el trabajador asignado puede liberar este trabajo.")
    if solicitud.estado != EstadoSolicitud.ACEPTADA:
        raise ErrorSolicitud("Solo puedes liberar un trabajo que esté en curso.")

    solicitud.estado = EstadoSolicitud.PENDIENTE
    solicitud.trabajador = None
    solicitud.save()
    notificador.notificar(EventoSolicitud(TipoEvento.REASIGNADA, solicitud))
    return solicitud


def validar_codigo(solicitud_id, codigo):
    solicitud = _buscar(solicitud_id)
    return bool(solicitud.codigo_finalizacion) and (
        solicitud.codigo_finalizacion.upper() == (codigo or "").strip().upper()
    )


def finalizar_con_evidencia(solicitud_id, evidencia):
    """Marca el trabajo como COMPLETADA y guarda la foto de evidencia."""
    solicitud = _buscar(solicitud_id)
    solicitud.evidencia = evidencia
    solicitud.estado = EstadoSolicitud.COMPLETADA
    solicitud.fecha_finalizacion = timezone.now()
    solicitud.save()
    notificador.notificar(EventoSolicitud(TipoEvento.COMPLETADA, solicitud))
    return solicitud


def calificar(solicitud_id, calificacion, comentario, cliente):
    solicitud = _buscar(solicitud_id)
    if solicitud.estado != EstadoSolicitud.COMPLETADA:
        raise ErrorSolicitud("Solo puedes calificar servicios que ya estén completados.")
    if solicitud.cliente_id != cliente.id:
        raise ErrorSolicitud("Solo el cliente que solicitó el servicio puede calificarlo.")
    if solicitud.calificacion is not None:
        raise ErrorSolicitud("Este servicio ya fue calificado.")
    if calificacion is None or not (1 <= calificacion <= 5):
        raise ErrorSolicitud("La calificación debe estar entre 1 y 5 estrellas.")

    solicitud.calificacion = calificacion
    solicitud.comentario = comentario or ""
    solicitud.save()
    notificador.notificar(EventoSolicitud(TipoEvento.CALIFICADA, solicitud))
    return solicitud


def listar_del_cliente(cliente, estado=None):
    """Las solicitudes del cliente, de la más reciente a la más antigua."""
    solicitudes = Solicitud.objects.filter(cliente=cliente).select_related(
        "trabajador", "metodo_pago"
    )
    if estado:
        solicitudes = solicitudes.filter(estado=estado)
    return solicitudes.order_by("-id")


def historial_del_cliente(cliente):
    """Todo lo que ya salió de 'pendiente': aceptadas, completadas y canceladas."""
    return (
        Solicitud.objects.filter(cliente=cliente)
        .exclude(estado=EstadoSolicitud.PENDIENTE)
        .select_related("trabajador")
        .order_by("-id")
    )