from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from usuarios.localidades import localidades_para_mapa
from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import servicios
from .forms import SolicitudForm
from .models import EstadoSolicitud
from .servicios import ErrorSolicitud


@rol_requerido(Rol.CLIENTE)
def nueva(request):
    if request.method == "POST":
        form = SolicitudForm(request.POST, cliente=request.user)
        if form.is_valid():
            # Los datos ya validados pasan a la lógica del paso 2.1.
            servicios.crear_solicitud(request.user, **form.cleaned_data)
            messages.success(
                request,
                "Tu solicitud fue enviada. Te avisaremos cuando un trabajador la acepte.",
            )
            return redirect("solicitudes:mis_solicitudes")
    else:
        form = SolicitudForm(cliente=request.user)

    return render(request, "solicitudes/nueva.html", {
        "form": form,
        "localidades": localidades_para_mapa(),
        "metodos_pago": form.fields["metodo_pago"].queryset,
    })


@rol_requerido(Rol.CLIENTE)
def mis_solicitudes(request):
    # Filtro opcional: /solicitudes/mis-solicitudes?estado=PENDIENTE
    estado = (request.GET.get("estado") or "").upper()
    if estado not in EstadoSolicitud.values:
        estado = None  # un valor inválido se ignora, igual que en la versión Java

    return render(request, "solicitudes/mis_solicitudes.html", {
        "solicitudes": servicios.listar_del_cliente(request.user, estado),
        "filtro_actual": estado,
    })


@rol_requerido(Rol.CLIENTE)
def historial_cliente(request):
    return render(request, "solicitudes/historial_cliente.html", {
        "solicitudes": servicios.historial_del_cliente(request.user),
    })


@require_POST  # cancelar cambia datos, así que solo se acepta por POST (nunca por un enlace)
@rol_requerido(Rol.CLIENTE)
def cancelar(request, solicitud_id):
    try:
        servicios.cancelar(solicitud_id, request.user)
        messages.success(request, "La solicitud fue cancelada.")
    except ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:mis_solicitudes")