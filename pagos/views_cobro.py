"""Pantallas del cobro: pagar un servicio, comprobante e historial de pagos."""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from solicitudes.models import EstadoSolicitud, Solicitud
from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import cobros, consultas, servicios
from .models import Pago
from .servicios import ErrorPago


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@rol_requerido(Rol.CLIENTE)
def pagar(request, solicitud_id):
    # La pantalla de pago solo existe para el cliente dueño de la solicitud.
    solicitud = get_object_or_404(
        Solicitud.objects.select_related("trabajador", "metodo_pago"),
        pk=solicitud_id, cliente=request.user,
    )
    pago = Pago.objects.filter(solicitud=solicitud).select_related("metodo_pago").first()

    return render(request, "pagos/pago_solicitud.html", {
        "solicitud": solicitud,
        "pago": pago,
        "metodos": servicios.listar_metodos(request.user),
        "porcentaje": cobros.porcentaje_comision(),
        "completada": solicitud.estado == EstadoSolicitud.COMPLETADA,
    })


@require_POST
@rol_requerido(Rol.CLIENTE)
def realizar_pago(request, solicitud_id):
    try:
        cobros.pagar(solicitud_id, _entero(request.POST.get("metodo_id")), request.user)
        messages.success(request, "Pago realizado con éxito. El trabajador recibirá el neto.")
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("pagos:pagar", solicitud_id=solicitud_id)


@rol_requerido(Rol.CLIENTE)
def historial(request):
    return render(request, "pagos/historial_pagos.html", {
        "pagos": consultas.historial_cliente(request.user),
    })


@rol_requerido(Rol.CLIENTE, Rol.TRABAJADOR)
def comprobante(request, pago_id):
    # Lo ven solo las dos personas del pago: quien pagó y quien trabajó.
    pago = get_object_or_404(
        Pago.objects.select_related("solicitud", "cliente", "trabajador", "metodo_pago"),
        Q(pk=pago_id) & (Q(cliente=request.user) | Q(trabajador=request.user)),
    )
    return render(request, "pagos/comprobante_pago.html", {
        "pago": pago,
        "porcentaje": cobros.porcentaje_comision(),
    })