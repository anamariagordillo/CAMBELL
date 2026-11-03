"""Consultas de lectura sobre las solicitudes (las listas que ven los trabajadores).

Las acciones que cambian datos (aceptar, rechazar, liberar...) viven en servicios.py;
aquí solo se piden listas a la base de datos.
"""
from django.db.models import Q

from .models import EstadoSolicitud, Solicitud


def listar_disponibles(localidad=None, barrio=None, categoria=None,
                       precio_min=None, precio_max=None, orden="recientes"):
    """Solicitudes PENDIENTES que un trabajador puede tomar, con filtros opcionales."""
    solicitudes = Solicitud.objects.filter(
        estado=EstadoSolicitud.PENDIENTE
    ).select_related("cliente")

    if localidad:
        solicitudes = solicitudes.filter(localidad=localidad)
    if barrio:
        solicitudes = solicitudes.filter(barrio=barrio)
    if categoria:
        solicitudes = solicitudes.filter(categoria=categoria)

    # Las solicitudes sin precio ofertado siempre se muestran (igual que en la versión Java).
    if precio_min is not None:
        solicitudes = solicitudes.filter(
            Q(precio_ofertado__isnull=True) | Q(precio_ofertado__gte=precio_min)
        )
    if precio_max is not None:
        solicitudes = solicitudes.filter(
            Q(precio_ofertado__isnull=True) | Q(precio_ofertado__lte=precio_max)
        )

    if orden == "antiguas":
        return solicitudes.order_by("fecha_creacion", "id")
    return solicitudes.order_by("-fecha_creacion", "-id")


def listar_trabajos(trabajador, estado=None):
    """Los trabajos del trabajador, del más reciente al más antiguo."""
    trabajos = Solicitud.objects.filter(trabajador=trabajador).select_related("cliente")
    if estado:
        trabajos = trabajos.filter(estado=estado)
    return trabajos.order_by("-id")


def historial_del_trabajador(trabajador):
    """Todo lo que el trabajador ya tomó (en curso, completado o cancelado)."""
    return (
        Solicitud.objects.filter(trabajador=trabajador)
        .exclude(estado=EstadoSolicitud.PENDIENTE)
        .select_related("cliente")
        .order_by("-id")
    )


def contar_completados(trabajador):
    return Solicitud.objects.filter(
        trabajador=trabajador, estado=EstadoSolicitud.COMPLETADA
    ).count()