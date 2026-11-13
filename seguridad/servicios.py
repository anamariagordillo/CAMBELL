"""Reglas de los reportes de seguridad (ReporteSeguridadService.java)."""
from django.db.models import Q

from .models import ReporteSeguridad


class ErrorReporte(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle a la persona."""


def contraparte(solicitud, usuario):
    """A quién puede reportar el usuario dentro de una solicitud.

    El cliente reporta al trabajador asignado y el trabajador reporta al cliente.
    Cualquier otra persona recibe None.
    """
    if solicitud.cliente_id == usuario.id:
        return solicitud.trabajador
    if solicitud.trabajador_id == usuario.id:
        return solicitud.cliente
    return None


def crear(reportante, reportado, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorReporte("Describe el motivo del reporte.")
    if len(motivo) > 1000:
        raise ErrorReporte("El motivo no puede superar los 1000 caracteres.")
    if reportante.id == reportado.id:
        raise ErrorReporte("No puedes reportarte a ti mismo.")

    return ReporteSeguridad.objects.create(
        reportante=reportante, reportado=reportado, motivo=motivo
    )


def listar_en_revision():
    return ReporteSeguridad.objects.filter(
        estado=ReporteSeguridad.Estado.EN_REVISION
    ).select_related("reportante", "reportado")


def listar_todos():
    return ReporteSeguridad.objects.select_related("reportante", "reportado")


def buscar(estado=None, q=None, desde=None, hasta=None):
    """Filtros combinados del panel de administración (todos opcionales)."""
    reportes = listar_todos()

    if estado in ReporteSeguridad.Estado.values:
        reportes = reportes.filter(estado=estado)
    if q and q.strip():
        texto = q.strip()
        reportes = reportes.filter(
            Q(reportado__nombre__icontains=texto)
            | Q(reportado__correo__icontains=texto)
            | Q(reportante__nombre__icontains=texto)
            | Q(motivo__icontains=texto)
        )
    if desde:
        reportes = reportes.filter(fecha__date__gte=desde)
    if hasta:
        reportes = reportes.filter(fecha__date__lte=hasta)

    return reportes.order_by("-fecha", "-id")


def buscar_uno(reporte_id):
    try:
        return ReporteSeguridad.objects.select_related("reportante", "reportado").get(
            pk=reporte_id
        )
    except ReporteSeguridad.DoesNotExist:
        raise ErrorReporte("Reporte no encontrado")


def marcar_bloqueado(reporte_id):
    reporte = buscar_uno(reporte_id)
    reporte.estado = ReporteSeguridad.Estado.BLOQUEADO
    reporte.save(update_fields=["estado"])
    return reporte


def descartar(reporte_id):
    reporte = buscar_uno(reporte_id)
    reporte.estado = ReporteSeguridad.Estado.DESCARTADO
    reporte.save(update_fields=["estado"])
    return reporte
