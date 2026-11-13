"""Compatibilidad entre una solicitud y la cobertura de los trabajadores.

Equivale a CoberturaTrabajadorService.java. Se usa para avisar a los
trabajadores compatibles cuando entra una solicitud (patrón Observer) y para
reutilizarlo después en el motor de recomendación de la Fase 2.

Reglas de compatibilidad (las mismas de Java):
  - El trabajador debe estar disponible y dentro de su horario.
  - Si definió especialidades, la solicitud debe ser de una de ellas.
  - Si definió localidades, la solicitud debe estar en una de ellas o dentro
    del radio de cobertura (distancia Haversine).
"""
import math

from django.utils import timezone

from .localidades import LOCALIDADES
from .models import CoberturaTrabajador, EstadoVerificacion, Rol

RADIO_TIERRA_KM = 6371.0


# ------------------------------------------------------------------ Utilidades
def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia en línea recta entre dos coordenadas (fórmula de Haversine)."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return RADIO_TIERRA_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def coordenadas_de_barrio(localidad, barrio):
    """Coordenadas del barrio según el catálogo; None si no se encuentra."""
    for nombre, latitud, longitud in LOCALIDADES.get(localidad, []):
        if nombre == barrio:
            return latitud, longitud
    return None


def centro_localidad(localidad):
    """Coordenadas aproximadas de una localidad (su primer barrio del catálogo)."""
    barrios = LOCALIDADES.get(localidad)
    if not barrios:
        return None
    _, latitud, longitud = barrios[0]
    return latitud, longitud


def _punto_de_solicitud(solicitud):
    """Coordenadas de la solicitud: las guardadas o las del barrio del catálogo."""
    if solicitud.latitud is not None and solicitud.longitud is not None:
        return solicitud.latitud, solicitud.longitud
    return coordenadas_de_barrio(solicitud.localidad, solicitud.barrio)


def _cubre_horario(cobertura, momento):
    """True si el trabajador atiende en ese día y hora.

    Si el trabajador cargó bloques en `Horario` (Fase 1B), se usan esos.
    Si no, se conserva la ventana general de `CoberturaTrabajador`, como en Java.
    """
    bloques = [h for h in cobertura.trabajador.horarios.all() if h.activo]
    if bloques:
        return any(bloque.cubre(momento) for bloque in bloques)
    return cobertura.hora_inicio <= momento.time() <= cobertura.hora_fin


def _en_radio_de_cobertura(solicitud, cobertura):
    punto = _punto_de_solicitud(solicitud)
    if punto is None:
        return False
    return any(
        centro is not None
        and distancia_km(centro[0], centro[1], punto[0], punto[1]) <= cobertura.radio_km
        for centro in (centro_localidad(localidad) for localidad in cobertura.localidades)
    )


# ------------------------------------------------------------------ Compatibilidad
def es_compatible(solicitud, cobertura, momento=None):
    """True si la solicitud encaja con la cobertura del trabajador."""
    if not cobertura.disponible:
        return False

    momento = momento or timezone.localtime()
    if not _cubre_horario(cobertura, momento):
        return False

    # Si el trabajador no marcó especialidades, atiende todas.
    if cobertura.categorias and solicitud.categoria not in cobertura.categorias:
        return False

    # Si no marcó localidades, cubre cualquier zona.
    if cobertura.localidades:
        en_localidad = bool(solicitud.localidad) and solicitud.localidad in cobertura.localidades
        if not en_localidad and not _en_radio_de_cobertura(solicitud, cobertura):
            return False

    return True


def _coberturas_compatibles(solicitud, momento=None):
    """Coberturas de trabajadores aprobados que pueden atender la solicitud."""
    coberturas = (
        CoberturaTrabajador.objects.filter(
            trabajador__rol=Rol.TRABAJADOR,
            trabajador__estado_verificacion=EstadoVerificacion.APROBADO,
            trabajador__bloqueado=False,
        )
        .select_related("trabajador")
        .prefetch_related("trabajador__horarios")
    )
    return [c for c in coberturas if es_compatible(solicitud, c, momento)]


def trabajadores_compatibles(solicitud, momento=None):
    """Trabajadores aprobados cuya cobertura encaja con la solicitud."""
    return [c.trabajador for c in _coberturas_compatibles(solicitud, momento)]


def distancia_de_trabajador(solicitud, trabajador, cobertura=None):
    """Distancia (km) a la localidad cubierta más cercana al punto de la solicitud.

    Devuelve 0 cuando no hay coordenadas: en ese caso el orden no importa.
    """
    punto = _punto_de_solicitud(solicitud)
    if punto is None:
        return 0.0

    cobertura = cobertura or getattr(trabajador, "cobertura", None)
    localidades = list(cobertura.localidades) if cobertura else []
    if not localidades and trabajador.localidad:
        localidades = [trabajador.localidad]

    distancias = []
    for localidad in localidades:
        centro = centro_localidad(localidad)
        if centro is not None:
            distancias.append(distancia_km(centro[0], centro[1], punto[0], punto[1]))
    return min(distancias) if distancias else 0.0


def trabajadores_compatibles_por_cercania(solicitud, momento=None):
    """Los compatibles, ordenados del más cercano al más lejano."""
    coberturas = _coberturas_compatibles(solicitud, momento)
    coberturas.sort(key=lambda c: distancia_de_trabajador(solicitud, c.trabajador, c))
    return [c.trabajador for c in coberturas]
