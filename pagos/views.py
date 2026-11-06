from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import servicios
from .models import MetodoPago
from .servicios import ErrorPago


def _entero(valor):
    """'12' -> 12; '' o texto raro -> None."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@rol_requerido(Rol.CLIENTE)
def metodos(request):
    """GET: lista los métodos del cliente. POST: registra uno nuevo."""
    if request.method == "POST":
        try:
            servicios.registrar_metodo(
                request.user,
                request.POST.get("tipo"),
                request.POST.get("titular"),
                request.POST.get("numero"),
                _entero(request.POST.get("mes_vencimiento")),
                _entero(request.POST.get("anio_vencimiento")),
            )
            messages.success(request, "Método de pago registrado.")
        except ErrorPago as error:
            messages.error(request, str(error))
        return redirect("pagos:metodos")

    return render(request, "pagos/metodos_pago.html", {
        "metodos": servicios.listar_metodos(request.user),
        "tipos": MetodoPago.Tipo.choices,
        "anio_minimo": timezone.localdate().year,
    })


@require_POST
@rol_requerido(Rol.CLIENTE)
def editar_metodo(request, metodo_id):
    try:
        servicios.editar_metodo(
            metodo_id,
            request.user,
            request.POST.get("titular"),
            _entero(request.POST.get("mes_vencimiento")),
            _entero(request.POST.get("anio_vencimiento")),
        )
        messages.success(request, "Método de pago actualizado.")
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("pagos:metodos")


@require_POST
@rol_requerido(Rol.CLIENTE)
def eliminar_metodo(request, metodo_id):
    try:
        servicios.eliminar_metodo(metodo_id, request.user)
        messages.success(request, "Método de pago eliminado.")
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("pagos:metodos")