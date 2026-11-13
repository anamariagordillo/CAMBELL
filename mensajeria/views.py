"""Pantallas de mensajería: chat de una solicitud y bandeja de notificaciones."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import servicios
from .servicios import ErrorMensajeria

POR_PAGINA = 10


# ------------------------------------------------------------------ Chat
@login_required
def chat(request, solicitud_id):
    """Conversación entre el cliente y el trabajador de una solicitud."""
    try:
        solicitud = servicios.buscar_solicitud(solicitud_id)
    except ErrorMensajeria:
        raise Http404("Solicitud no encontrada")

    if not servicios.puede_participar(solicitud, request.user):
        raise PermissionDenied

    if request.method == "POST":
        try:
            servicios.enviar_mensaje(solicitud, request.user, request.POST.get("contenido"))
            messages.success(request, "Mensaje enviado.")
        except ErrorMensajeria as error:
            messages.error(request, str(error))
        return redirect("mensajeria:chat", solicitud_id=solicitud_id)

    # Al abrir la conversación se marcan como leídos los mensajes recibidos.
    servicios.marcar_mensajes_leidos(solicitud, request.user)

    return render(request, "mensajeria/chat.html", {
        "solicitud": solicitud,
        "mensajes": servicios.listar_mensajes(solicitud),
    })


# ------------------------------------------------------------------ Notificaciones
@login_required
def notificaciones(request):
    tipo = request.GET.get("tipo") or "TODOS"
    if tipo not in dict(servicios.TIPOS_NOTIFICACION):
        tipo = "TODOS"

    lista = servicios.listar_notificaciones(request.user, tipo)
    pagina = Paginator(lista, POR_PAGINA).get_page(request.GET.get("pag"))

    return render(request, "mensajeria/notificaciones.html", {
        "notificaciones": pagina,
        "tipos": servicios.TIPOS_NOTIFICACION,
        "tipo_filtro": tipo,
        "total": pagina.paginator.count,
        "no_leidos": servicios.contar_no_leidas(request.user),
    })


@require_POST
@login_required
def marcar_leida(request, notificacion_id):
    if not servicios.marcar_leida(notificacion_id, request.user):
        messages.error(request, "No se encontró la notificación.")
    return redirect("mensajeria:notificaciones")


@require_POST
@login_required
def marcar_todas(request):
    servicios.marcar_todas_leidas(request.user)
    messages.success(request, "Todas las notificaciones quedaron marcadas como leídas.")
    return redirect("mensajeria:notificaciones")


@require_POST
@login_required
def eliminar(request, notificacion_id):
    if not servicios.eliminar_notificacion(notificacion_id, request.user):
        messages.error(request, "No se encontró la notificación.")
    return redirect("mensajeria:notificaciones")
