"""Servicio de verificación de identidad (VerificacionFacialService.java).

Combina la estrategia elegida (Strategy) con el umbral configurado y deja el
resultado en el usuario y en un expediente `Verificacion`. Cuando la estrategia
es manual (sin credenciales de Face++), el intento queda PENDIENTE para que un
administrador lo revise, igual que en la versión Java.
"""
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from .estrategias_verificacion import EstrategiaVerificacion, estrategia_actual
from .models import Archivo, EstadoVerificacion, Verificacion

# Cómo se traduce el estado del usuario al estado del expediente.
ESTADO_EXPEDIENTE = {
    EstadoVerificacion.PENDIENTE: Verificacion.Estado.PENDIENTE,
    EstadoVerificacion.APROBADO: Verificacion.Estado.APROBADA,
    EstadoVerificacion.RECHAZADO: Verificacion.Estado.RECHAZADA,
}


@dataclass(frozen=True)
class ResultadoVerificacion:
    """Lo que devuelve la evaluación automática."""

    estado: str
    motivo: str
    confianza: float | None = None


def umbral():
    return float(settings.UMBRAL_VERIFICACION_FACIAL)


def evaluar_automatica(
    ruta_documento, ruta_selfie, numero_documento=None, estrategia=None
):
    """Compara documento y selfie y decide el estado del trabajador.

    El orden de las decisiones es el mismo de Java:
      1. Sin número de documento no hay nada que contrastar.
      2. Si la estrategia es manual, el intento va a revisión humana.
      3. Similitud >= umbral: se aprueba.
      4. El servicio no respondió: se deja pendiente (no se rechaza).
      5. Similitud menor al umbral: se deja pendiente con el motivo.
    """
    estrategia = estrategia or estrategia_actual()

    if not numero_documento:
        return ResultadoVerificacion(
            EstadoVerificacion.PENDIENTE,
            "No se pudo comprobar el número de documento del trabajador.",
        )

    if not estrategia.automatica:
        return ResultadoVerificacion(
            EstadoVerificacion.PENDIENTE,
            "La verificación facial automática no está configurada; "
            "el intento queda para revisión manual.",
        )

    confianza = estrategia.verificar(ruta_documento, ruta_selfie)

    if confianza >= umbral():
        return ResultadoVerificacion(
            EstadoVerificacion.APROBADO, "", round(confianza, 1)
        )

    if confianza < 0:
        return ResultadoVerificacion(
            EstadoVerificacion.PENDIENTE,
            "La verificación facial automática no pudo completarse "
            "(el servicio de similitud no respondió).",
        )

    return ResultadoVerificacion(
        EstadoVerificacion.PENDIENTE,
        f"La similitud facial entre el documento y la selfie fue del "
        f"{confianza:.1f}%, por debajo del umbral del {umbral():.0f}%.",
        round(confianza, 1),
    )


# ------------------------------------------------------------------ Registro
def registrar_archivo(trabajador, tipo, nombre):
    """Apunta en `Archivo` un documento del trabajador.

    Antes marca como no vigentes los archivos anteriores del mismo tipo. Los
    archivos viejos quedan en disco hasta que la tarea de limpieza los borre.
    """
    Archivo.objects.filter(
        propietario=trabajador, tipo=tipo, vigente=True
    ).update(vigente=False)

    archivo = Archivo(
        propietario=trabajador,
        tipo=tipo,
        archivo=nombre,
        nombre_original=nombre.split("/")[-1],
    )
    archivo.save()
    return archivo


def registrar_intento(
    trabajador,
    documento=None,
    selfie=None,
    motivo="",
    origen=Verificacion.Origen.MANUAL,
    estado=Verificacion.Estado.PENDIENTE,
    porcentaje=None,
):
    """Crea un expediente de verificación (historial de intentos)."""
    return Verificacion.objects.create(
        trabajador=trabajador,
        estado=estado,
        origen=origen,
        porcentaje_coincidencia=porcentaje,
        documento=documento,
        selfie=selfie,
        motivo=motivo[:500],
        fecha_decision=timezone.now() if estado == Verificacion.Estado.APROBADA else None,
    )


def evaluar_y_registrar(trabajador, estrategia=None):
    """Evalúa los archivos del trabajador y guarda el resultado.

    Si al trabajador le falta el documento o la selfie, no hace nada y devuelve
    None. Se usa en el registro y en el reintento de verificación.
    """
    if not trabajador.documento or not trabajador.selfie:
        return None

    estrategia = estrategia or estrategia_actual()
    resultado = evaluar_automatica(
        trabajador.documento.path,
        trabajador.selfie.path,
        trabajador.numero_documento,
        estrategia,
    )

    trabajador.estado_verificacion = resultado.estado
    trabajador.motivo_verificacion = resultado.motivo
    trabajador.save(update_fields=["estado_verificacion", "motivo_verificacion"])

    documento = registrar_archivo(
        trabajador, Archivo.Tipo.DOCUMENTO, trabajador.documento.name
    )
    selfie = registrar_archivo(
        trabajador, Archivo.Tipo.SELFIE, trabajador.selfie.name
    )

    porcentaje = resultado.confianza
    if porcentaje is not None and not (0 <= porcentaje <= 100):
        porcentaje = None

    return registrar_intento(
        trabajador,
        documento=documento,
        selfie=selfie,
        motivo=resultado.motivo,
        origen=(
            Verificacion.Origen.AUTOMATICA
            if estrategia.automatica
            else Verificacion.Origen.MANUAL
        ),
        estado=ESTADO_EXPEDIENTE[resultado.estado],
        porcentaje=porcentaje,
    )
