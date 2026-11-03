"""Patrón Observer para los eventos de una solicitud (paquete observer/ de la versión Java)."""
import logging
from dataclasses import dataclass
from enum import Enum

from django.db.models import Avg, Count

from mensajeria.servicios import crear_notificacion

from .models import EstadoSolicitud, Solicitud

logger = logging.getLogger(__name__)


class TipoEvento(Enum):
    CREADA = "CREADA"
    ACEPTADA = "ACEPTADA"
    COMPLETADA = "COMPLETADA"
    CALIFICADA = "CALIFICADA"
    REASIGNADA = "REASIGNADA"


@dataclass(frozen=True)
class EventoSolicitud:
    """Lo que se le avisa a los observadores: qué pasó y a qué solicitud."""

    tipo: TipoEvento
    solicitud: object


class Notificador:
    """El 'sujeto' del patrón: guarda la lista de observadores y les avisa."""

    def __init__(self):
        self._observadores = []

    def suscribir(self, observador):
        self._observadores.append(observador)

    def notificar(self, evento):
        for observador in self._observadores:
            observador.actualizar(evento)


class NotificacionObservador:
    """Crea las notificaciones que ve la gente en su bandeja."""

    def actualizar(self, evento):
        s = evento.solicitud
        if evento.tipo == TipoEvento.ACEPTADA:
            crear_notificacion(
                s.cliente, "ESTADO",
                f'Tu solicitud "{s.descripcion}" fue aceptada por {s.trabajador.nombre}. '
                "El servicio ya está en camino.",
                s,
            )
        elif evento.tipo == TipoEvento.COMPLETADA:
            crear_notificacion(
                s.cliente, "ESTADO",
                f'El servicio "{s.descripcion}" fue completado. No olvides calificar y pagar.',
                s,
            )
        # CREADA y REASIGNADA avisan a los trabajadores compatibles con la zona.
        # Eso depende de "Mi cobertura" (paso 5) y se conecta cuando exista.


class RecalculoPromedioObservador:
    """Cuando un cliente califica, recalcula el promedio del trabajador."""

    def actualizar(self, evento):
        if evento.tipo != TipoEvento.CALIFICADA:
            return
        trabajador = evento.solicitud.trabajador
        resumen = Solicitud.objects.filter(
            trabajador=trabajador,
            estado=EstadoSolicitud.COMPLETADA,
            calificacion__isnull=False,
        ).aggregate(promedio=Avg("calificacion"), total=Count("id"))

        trabajador.calificacion_promedio = resumen["promedio"] or 0.0
        trabajador.total_calificaciones = resumen["total"]
        trabajador.save(update_fields=["calificacion_promedio", "total_calificaciones"])
        logger.info("Promedio recalculado para %s", trabajador.nombre)


class LogObservador:
    """Deja un registro en la consola (equivale a NotificacionLogObservador)."""

    def actualizar(self, evento):
        logger.info("Evento %s en la solicitud #%s", evento.tipo.value, evento.solicitud.pk)


# Un único notificador para toda la aplicación, con sus observadores ya suscritos.
notificador = Notificador()
notificador.suscribir(NotificacionObservador())
notificador.suscribir(RecalculoPromedioObservador())
notificador.suscribir(LogObservador())