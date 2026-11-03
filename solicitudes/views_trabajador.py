"""Pantallas y acciones del trabajador (disponibles, aceptar, rechazar, mis trabajos)."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from usuarios.localidades import localidades_para_mapa, nombres_localidades
from usuarios.models import EstadoVerificacion, Rol
from usuarios.permisos import rol_requerido

from . import consultas, servicios
from .filtros import FiltroDisponiblesForm
from .models import CategoriaServicio, EstadoSolicitud
from .servicios import ErrorSolicitud

# ?estado=... de "Mis trabajos" -> estado real en la base de datos
FILTROS_TRABAJOS = {
    "completadas": EstadoSolicitud.COMPLETADA,
    "canceladas": EstadoSolicitud.CANCELADA,
}


@rol_requerido(Rol.TRABAJADOR)
def disponibles(request):
    # Solo un trabajador con identidad aprobada puede ver y tomar solicitudes.
    if request.user.estado_verificacion != EstadoVerificacion.APROBADO:
        return render(request, "solicitudes/verificacion_pendiente.html")

    filtro = FiltroDisponiblesForm(request.GET)
    filtro.is_valid()  # los valores inválidos simplemente se ignoran
    datos = filtro.cleaned_data

    solicitudes = consultas.listar_disponibles(
        localidad=datos.get("localidad") or None,
        barrio=datos.get("barrio") or None,
        categoria=datos.get("categoria") or None,
        precio_min=datos.get("precio_min"),
        precio_max=datos.get("precio_max"),
        orden=datos.get("orden") or "recientes",
    )

    return render(request, "solicitudes/disponibles.html", {
        "solicitudes": solicitudes,
        "localidades": nombres_localidades(),
        "localidades_json": localidades_para_mapa(),
        "categorias": CategoriaServicio.choices,
        "filtros": {
            "localidad": datos.get("localidad") or "",
            "barrio": datos.get("barrio") or "",
            "categoria": datos.get("categoria") or "",
            "precio_min": datos.get("precio_min") if datos.get("precio_min") is not None else "",
            "precio_max": datos.get("precio_max") if datos.get("precio_max") is not None else "",
            "orden": datos.get("orden") or "recientes",
        },
        # IDs de solicitudes compatibles con la cobertura del trabajador.
        # Se llena cuando exista "Mi cobertura" (fase 5).
        "compatibles": set(),
    })


@require_POST
@rol_requerido(Rol.TRABAJADOR)
def aceptar(request, solicitud_id):
    try:
        servicios.aceptar(solicitud_id, request.user)
        messages.success(request, "Aceptaste la solicitud. La encuentras en Mis trabajos.")
    except ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:disponibles")


@require_POST
@rol_requerido(Rol.TRABAJADOR)
def rechazar(request, solicitud_id):
    motivo = (request.POST.get("motivo") or "").strip()
    if not motivo:
        messages.error(request, "Debes indicar el motivo del rechazo.")
        return redirect("solicitudes:disponibles")
    try:
        servicios.rechazar(solicitud_id, motivo, request.user)
        messages.success(request, "Rechazaste la solicitud. Quedó disponible para otros trabajadores.")
    except ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:disponibles")


@rol_requerido(Rol.TRABAJADOR)
def mis_trabajos(request):
    pedido = (request.GET.get("estado") or "").lower()
    if pedido == "todas":
        filtro_actual, estado = "todas", None
    elif pedido in FILTROS_TRABAJOS:
        filtro_actual, estado = pedido, FILTROS_TRABAJOS[pedido]
    else:
        filtro_actual, estado = "en-curso", EstadoSolicitud.ACEPTADA

    trabajos = list(consultas.listar_trabajos(request.user, estado))

    # Punto exacto del mapa: solo de los trabajos en curso (los únicos que lo necesitan).
    puntos_exactos = {
        str(t.id): {"lat": t.latitud, "lon": t.longitud}
        for t in trabajos
        if t.estado == EstadoSolicitud.ACEPTADA
        and t.latitud is not None and t.longitud is not None
    }

    return render(request, "solicitudes/mis_trabajos.html", {
        "trabajos": trabajos,
        "puntos_exactos": puntos_exactos,
        "filtro_actual": filtro_actual,
    })


@rol_requerido(Rol.TRABAJADOR)
def historial_trabajos(request):
    return render(request, "solicitudes/historial_trabajos.html", {
        "historial": consultas.historial_del_trabajador(request.user),
    })


@require_POST
@rol_requerido(Rol.TRABAJADOR)
def liberar(request, solicitud_id):
    try:
        servicios.liberar(solicitud_id, request.user)
        messages.success(request, "Liberaste el trabajo. Quedó disponible para otros trabajadores.")
    except ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:mis_trabajos")