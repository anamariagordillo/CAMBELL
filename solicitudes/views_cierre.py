"""Cierre del servicio: finalizar (trabajador), calificar y ver el perfil (cliente)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from pagos.models import Suscripcion
from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import consultas, finalizacion, servicios
from .models import Solicitud
from .servicios import ErrorSolicitud


@require_POST
@rol_requerido(Rol.TRABAJADOR)
def finalizar(request, solicitud_id):
    try:
        finalizacion.finalizar_trabajo(
            solicitud_id,
            request.user,
            request.POST.get("codigo"),
            request.FILES.get("evidencia"),
        )
    except ErrorSolicitud as error:
        messages.error(request, str(error))
        return redirect("solicitudes:mis_trabajos")
    return redirect("solicitudes:finalizado", solicitud_id=solicitud_id)


@rol_requerido(Rol.TRABAJADOR)
def finalizado(request, solicitud_id):
    # Solo el trabajador de ese trabajo puede ver la página; para los demás no existe.
    solicitud = get_object_or_404(
        Solicitud.objects.select_related("metodo_pago"),
        pk=solicitud_id, trabajador=request.user,
    )
    return render(request, "solicitudes/trabajo_finalizado.html", {"solicitud": solicitud})


@require_POST
@rol_requerido(Rol.CLIENTE)
def calificar(request, solicitud_id):
    try:
        puntuacion = int(request.POST.get("puntuacion", ""))
    except ValueError:
        puntuacion = None  # el servicio responde "La calificación debe estar entre 1 y 5"

    comentario = (request.POST.get("comentario") or "").strip()[:500]
    try:
        servicios.calificar(solicitud_id, puntuacion, comentario, request.user)
        messages.success(request, "Gracias por calificar el servicio.")
    except ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:mis_solicitudes")


@rol_requerido(Rol.CLIENTE)
def perfil_trabajador(request, solicitud_id):
    # El cliente solo ve el perfil del trabajador que atendió una solicitud suya.
    solicitud = get_object_or_404(
        Solicitud.objects.select_related("trabajador"),
        pk=solicitud_id, cliente=request.user,
    )
    trabajador = solicitud.trabajador
    if trabajador is None:
        return redirect("solicitudes:mis_solicitudes")

    premium_activo = Suscripcion.objects.filter(
        trabajador=trabajador, activa=True, fecha_vencimiento__gt=timezone.now()
    ).exists()

    return render(request, "solicitudes/perfil_trabajador.html", {
        "trabajador": trabajador,
        "trabajos_realizados": consultas.contar_completados(trabajador),
        "premium_activo": premium_activo,
    })