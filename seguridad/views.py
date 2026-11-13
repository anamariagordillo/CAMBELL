"""Pantalla para reportar un comportamiento inseguro dentro de una solicitud."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from solicitudes.models import Solicitud
from usuarios.models import Rol

from . import servicios
from .servicios import ErrorReporte


def _destino(usuario):
    if usuario.rol == Rol.TRABAJADOR:
        return "solicitudes:mis_trabajos"
    return "solicitudes:mis_solicitudes"


@login_required
def reportar(request, solicitud_id):
    solicitud = get_object_or_404(
        Solicitud.objects.select_related("cliente", "trabajador"), pk=solicitud_id
    )
    reportado = servicios.contraparte(solicitud, request.user)

    if reportado is None:
        messages.error(request, "No puedes reportar a nadie en esta solicitud.")
        return redirect(_destino(request.user))

    if request.method == "POST":
        try:
            servicios.crear(request.user, reportado, request.POST.get("motivo"))
            messages.success(
                request, "Tu reporte fue enviado. El administrador lo revisará."
            )
            return redirect(_destino(request.user))
        except ErrorReporte as error:
            messages.error(request, str(error))

    return render(request, "seguridad/reportar.html", {
        "solicitud": solicitud,
        "reportado": reportado,
    })
