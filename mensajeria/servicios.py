"""Reglas de mensajería: chat por solicitud y bandeja de notificaciones.

Equivale a MensajeService y NotificacionService de la versión Java. Las reglas
viven aquí (y no en las vistas) para poder probarlas por separado.
"""
from django.db.models import Q

from .models import Mensaje, Notificacion

# Los mismos tipos que usa la versión Java; sirven para filtrar la bandeja.
TIPOS_NOTIFICACION = [
    ("TODOS", "Todas"),
    ("ASIGNACION", "Solicitudes"),
    ("SOLICITUD", "Estado de solicitudes"),
    ("ESTADO", "Estado"),
    ("CALIFICACION", "Calificaciones"),
    ("VERIFICACION", "Verificación"),
    ("SUSCRIPCION", "Suscripción"),
    ("PAGO", "Pago"),
    ("DOCUMENTO", "Documento"),
    ("SEGURIDAD", "Seguridad"),
    ("MENSAJE", "Mensajes"),
]


class ErrorMensajeria(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle a la persona."""


# ------------------------------------------------------------------ Notificaciones
def crear_notificacion(usuario, tipo, mensaje, solicitud=None):
    """Guarda una notificación en la bandeja del usuario.

    tipo: ESTADO, ASIGNACION, CALIFICACION, PAGO, etc. (los mismos de la versión Java).
    """
    return Notificacion.objects.create(
        usuario=usuario,
        tipo=tipo,
        mensaje=mensaje[:500],  # el campo admite 500 caracteres
        solicitud=solicitud,
    )


def listar_notificaciones(usuario, tipo=None):
    """Bandeja del usuario, de la más reciente a la más antigua."""
    notificaciones = Notificacion.objects.filter(usuario=usuario).select_related("solicitud")
    if tipo and tipo != "TODOS":
        notificaciones = notificaciones.filter(tipo=tipo)
    return notificaciones.order_by("-fecha", "-id")


def contar_notificaciones(usuario, tipo=None):
    return listar_notificaciones(usuario, tipo).count()


def contar_no_leidas(usuario):
    return Notificacion.objects.filter(usuario=usuario, leido=False).count()


def _notificacion_del_usuario(notificacion_id, usuario):
    """Solo devuelve la notificación si es del usuario; si no, None."""
    return Notificacion.objects.filter(pk=notificacion_id, usuario=usuario).first()


def marcar_leida(notificacion_id, usuario):
    notificacion = _notificacion_del_usuario(notificacion_id, usuario)
    if notificacion is None:
        return False
    if not notificacion.leido:
        notificacion.leido = True
        notificacion.save(update_fields=["leido"])
    return True


def marcar_todas_leidas(usuario):
    return Notificacion.objects.filter(usuario=usuario, leido=False).update(leido=True)


def eliminar_notificacion(notificacion_id, usuario):
    notificacion = _notificacion_del_usuario(notificacion_id, usuario)
    if notificacion is None:
        return False
    notificacion.delete()
    return True


# ------------------------------------------------------------------ Chat
def buscar_solicitud(solicitud_id):
    # Se importa aquí para evitar un ciclo entre las apps solicitudes y mensajeria.
    from solicitudes.models import Solicitud

    try:
        return Solicitud.objects.select_related("cliente", "trabajador").get(pk=solicitud_id)
    except Solicitud.DoesNotExist:
        raise ErrorMensajeria("Solicitud no encontrada")


def puede_participar(solicitud, usuario):
    """Solo el cliente dueño de la solicitud y el trabajador asignado pueden chatear."""
    return usuario.id in (solicitud.cliente_id, solicitud.trabajador_id)


def listar_mensajes(solicitud):
    return solicitud.mensajes.select_related("emisor").order_by("fecha", "id")


def contar_no_leidos(usuario):
    """Mensajes que otros le enviaron al usuario en sus solicitudes."""
    return (
        Mensaje.objects.filter(leido=False)
        .exclude(emisor=usuario)
        .filter(Q(solicitud__cliente=usuario) | Q(solicitud__trabajador=usuario))
        .count()
    )


def marcar_mensajes_leidos(solicitud, usuario):
    """Al abrir el chat, se marcan como leídos los mensajes que recibió el usuario."""
    return (
        solicitud.mensajes.filter(leido=False)
        .exclude(emisor=usuario)
        .update(leido=True)
    )


def enviar_mensaje(solicitud, emisor, contenido):
    """Guarda el mensaje y avisa al otro participante de la solicitud."""
    if not puede_participar(solicitud, emisor):
        raise ErrorMensajeria("No puedes escribir en esta solicitud.")

    contenido = (contenido or "").strip()
    if not contenido:
        raise ErrorMensajeria("Escribe un mensaje antes de enviarlo.")
    if len(contenido) > 2000:
        raise ErrorMensajeria("El mensaje no puede superar los 2000 caracteres.")

    mensaje = Mensaje.objects.create(
        solicitud=solicitud, emisor=emisor, contenido=contenido
    )

    # Se avisa a la contraparte (si todavía no hay trabajador, no hay a quién avisar).
    if emisor.id == solicitud.cliente_id:
        destinatario = solicitud.trabajador
    else:
        destinatario = solicitud.cliente

    if destinatario is not None:
        resumen = contenido if len(contenido) <= 80 else contenido[:80] + "…"
        crear_notificacion(
            destinatario, "MENSAJE",
            f"Nuevo mensaje de {emisor.nombre}: «{resumen}»",
            solicitud,
        )

    return mensaje
