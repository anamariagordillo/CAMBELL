"""'Mis ingresos' del trabajador y la descarga de su reporte (PDF, Excel o CSV)."""
import logging
from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render

from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import cobros, ingresos
from .servicios import ErrorPago

logger = logging.getLogger(__name__)


def _fecha(valor):
    """'2026-10-28' -> date; vacío o inválido -> None."""
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


@rol_requerido(Rol.TRABAJADOR)
def mis_ingresos(request):
    inicio, hoy = ingresos.rango_permitido(request.user)
    return render(request, "pagos/ingresos_trabajador.html", {
        "pagos": ingresos.historial_trabajador(request.user),
        "total": ingresos.ingresos_trabajador(request.user),
        "porcentaje": cobros.porcentaje_comision(),
        "fecha_minima": inicio,
        "fecha_maxima": hoy,
    })


@rol_requerido(Rol.TRABAJADOR)
def exportar_ingresos(request):
    inicio, hoy = ingresos.rango_permitido(request.user)
    desde = _fecha(request.GET.get("desde"))
    hasta = _fecha(request.GET.get("hasta"))

    try:
        desde, hasta = ingresos.normalizar_rango(desde, hasta, inicio, hoy)
    except ErrorPago as error:
        messages.error(request, str(error))
        return redirect("pagos:ingresos")

    pagos = list(ingresos.pagos_en_rango(request.user, desde, hasta))

    try:
        # Se importa aquí para que, si faltan las librerías de Excel/PDF, solo falle la descarga
        # (con un aviso) y no todo el sitio.
        from . import reportes

        contenido, tipo, extension = reportes.generar(
            request.GET.get("formato"), pagos, request.user, desde, hasta
        )
    except Exception:
        logger.exception("No se pudo generar el reporte de ingresos")
        messages.error(request, "No se pudo generar el reporte. Inténtalo de nuevo.")
        return redirect("pagos:ingresos")

    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = (
        f'attachment; filename="reporte_ingresos_{hoy.isoformat()}.{extension}"'
    )
    return respuesta