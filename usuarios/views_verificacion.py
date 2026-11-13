"""Reintento y actualización de documentos de verificación.

La comparación facial usa el patrón Strategy (`verificacion_facial.py`):
  - Con credenciales de Face++ configuradas se intenta la aprobación automática.
  - Sin credenciales, el intento queda PENDIENTE para revisión manual.

La actualización de un documento renovado siempre queda PENDIENTE, porque un
administrador debe confirmar que el documento nuevo es válido.
"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from usuarios.models import Archivo, EstadoVerificacion, Rol, Verificacion
from usuarios.permisos import rol_requerido
from usuarios.verificacion_facial import (
    evaluar_y_registrar,
    registrar_archivo,
    registrar_intento,
)

from .validadores import validar_mime

TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB


def _validar_archivo(archivo, etiqueta):
    """Devuelve un mensaje de error, o None si el archivo sirve."""
    if archivo is None:
        return f"Debes subir {etiqueta}."
    if archivo.size > TAMANO_MAXIMO:
        return f"{etiqueta.capitalize()} no puede superar los 5 MB."
    try:
        validar_mime(archivo)
    except ValidationError:
        return f"{etiqueta.capitalize()} debe ser una imagen o un PDF."
    return None


@rol_requerido(Rol.TRABAJADOR)
def reintentar(request):
    """Formulario para volver a subir documento y selfie tras un rechazo."""
    if request.method != "POST":
        return render(request, "solicitudes/verificacion_pendiente.html")

    documento = request.FILES.get("documento")
    selfie = request.FILES.get("selfie")

    error = _validar_archivo(documento, "la foto del documento") or _validar_archivo(
        selfie, "la selfie"
    )
    if error:
        messages.error(request, error)
        return redirect("verificacion:reintentar")

    trabajador = request.user
    trabajador.documento = documento
    trabajador.selfie = selfie
    trabajador.save(update_fields=["documento", "selfie"])

    verificacion = evaluar_y_registrar(trabajador)
    if verificacion and verificacion.estado == Verificacion.Estado.APROBADA:
        messages.success(
            request,
            "Tu identidad fue verificada automáticamente. Ya puedes aceptar solicitudes.",
        )
    else:
        messages.success(
            request,
            "Recibimos tus documentos. Un administrador revisará tu identidad nuevamente.",
        )
    return redirect("solicitudes:disponibles")


@require_POST
@rol_requerido(Rol.TRABAJADOR)
def actualizar_documento(request):
    """El trabajador sube un documento renovado; vuelve a quedar pendiente."""
    documento = request.FILES.get("documento")
    error = _validar_archivo(documento, "la foto del documento renovado")
    if error:
        messages.error(request, error)
        return redirect("solicitudes:mis_trabajos")

    trabajador = request.user
    trabajador.documento = documento
    trabajador.estado_verificacion = EstadoVerificacion.PENDIENTE
    trabajador.motivo_verificacion = "Documento renovado por el trabajador."
    trabajador.save(
        update_fields=["documento", "estado_verificacion", "motivo_verificacion"]
    )

    documento_registrado = registrar_archivo(
        trabajador, Archivo.Tipo.DOCUMENTO, trabajador.documento.name
    )
    registrar_intento(
        trabajador,
        documento=documento_registrado,
        motivo="Actualización de documento.",
    )

    messages.success(
        request,
        "Tu documento fue actualizado y quedó pendiente de verificación por un administrador.",
    )
    return redirect("solicitudes:mis_trabajos")
