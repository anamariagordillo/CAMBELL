"""Cierre de un trabajo: el trabajador entrega el código del cliente y una foto de evidencia."""
from django.core.exceptions import ValidationError

from usuarios.validadores import validar_extension, validar_mime

from . import servicios
from .models import EstadoSolicitud, Solicitud
from .servicios import ErrorSolicitud

TAMANO_MAXIMO_EVIDENCIA = 5 * 1024 * 1024  # 5 MB


def _validar_evidencia(archivo):
    try:
        validar_extension(archivo)  # jpg, png, webp, etc.
        validar_mime(archivo)       # el tipo declarado por el navegador también debe ser válido
    except ValidationError as error:
        raise ErrorSolicitud(error.messages[0])
    if archivo.size > TAMANO_MAXIMO_EVIDENCIA:
        raise ErrorSolicitud("La foto no puede superar los 5 MB.")


def finalizar_trabajo(solicitud_id, trabajador, codigo, evidencia):
    """Valida todo y marca el trabajo como COMPLETADA. Si algo falla, lanza ErrorSolicitud."""
    codigo = (codigo or "").strip()
    if not codigo:
        raise ErrorSolicitud("Debes ingresar el código de finalización.")
    if not evidencia:
        raise ErrorSolicitud("Debes adjuntar una foto del trabajo terminado.")

    try:
        solicitud = Solicitud.objects.get(pk=solicitud_id)
    except Solicitud.DoesNotExist:
        raise ErrorSolicitud("Solicitud no encontrada")

    # Primero se comprueba que el trabajo sea de este trabajador; así nadie más puede
    # probar códigos para ver si son correctos.
    if solicitud.trabajador_id != trabajador.id:
        raise ErrorSolicitud("Este trabajo no está asignado a ti.")
    if solicitud.estado != EstadoSolicitud.ACEPTADA:
        raise ErrorSolicitud("Este trabajo ya no está en curso.")
    if not servicios.validar_codigo(solicitud_id, codigo):
        raise ErrorSolicitud("El código de finalización ingresado es incorrecto.")

    _validar_evidencia(evidencia)
    return servicios.finalizar_con_evidencia(solicitud_id, evidencia)