from .models import Notificacion


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