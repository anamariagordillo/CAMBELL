"""Pantalla de la suscripción premium (contratar y cancelar)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import suscripcion as servicio
from .servicios import ErrorPago


@login_required
def mi_suscripcion(request):
    actual = servicio.de_usuario(request.user)
    return render(request, "pagos/suscripcion.html", {
        "suscripcion": actual,
        "activa": servicio.esta_activa(request.user),
        "costo": servicio.costo_mensual(),
    })


@require_POST
@login_required
def contratar(request):
    try:
        servicio.contratar(request.user)
        messages.success(
            request,
            "Pago aprobado. Tu suscripción premium quedó activada correctamente.",
        )
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("pagos:suscripcion")


@require_POST
@login_required
def cancelar(request):
    try:
        servicio.cancelar(request.user)
        messages.success(
            request,
            "Suscripción cancelada. Los beneficios siguen vigentes hasta el fin del periodo pagado.",
        )
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("pagos:suscripcion")
