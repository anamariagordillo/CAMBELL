"""Pantallas del administrador (el panel 'Cambell · Admin')."""
import mimetypes
from datetime import date

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from usuarios.localidades import nombres_localidades
from usuarios.models import EstadoVerificacion, Rol, Usuario
from usuarios.permisos import rol_requerido

from . import servicios
from .servicios import ErrorAdmin

SOLO_ADMIN = rol_requerido(Rol.ADMINISTRADOR)


def _fecha(valor):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ Verificaciones
@SOLO_ADMIN
def verificaciones(request):
    return render(request, "panel_admin/verificaciones.html", {
        "trabajadores": servicios.listar_pendientes(),
    })


@SOLO_ADMIN
def imagen(request, usuario_id):
    """Documento o selfie de un trabajador. NO es una dirección pública: solo la ve un administrador."""
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    tipo = request.GET.get("tipo")
    if tipo == "selfie":
        archivo = usuario.selfie
    elif tipo == "documento":
        archivo = usuario.documento
    else:
        raise Http404("Tipo de archivo desconocido")

    if not archivo:
        raise Http404("El usuario no tiene ese archivo")
    try:
        contenido = archivo.open("rb")
    except FileNotFoundError:
        raise Http404("El archivo ya no existe")

    tipo_mime = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
    respuesta = FileResponse(contenido, content_type=tipo_mime)
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@require_POST
@SOLO_ADMIN
def aprobar(request, usuario_id):
    try:
        usuario = servicios.aprobar_trabajador(usuario_id)
        messages.success(request, f"Verificación de {usuario.nombre} aprobada.")
    except ErrorAdmin as error:
        messages.error(request, str(error))
    return redirect("panel_admin:verificaciones")


@require_POST
@SOLO_ADMIN
def rechazar(request, usuario_id):
    try:
        usuario = servicios.rechazar_trabajador(usuario_id)
        messages.success(request, f"Verificación de {usuario.nombre} rechazada.")
    except ErrorAdmin as error:
        messages.error(request, str(error))
    return redirect("panel_admin:verificaciones")


# ------------------------------------------------------------------ Usuarios
@SOLO_ADMIN
def usuarios(request):
    g = request.GET
    desde, hasta = _fecha(g.get("desde")), _fecha(g.get("hasta"))
    resultados = servicios.buscar_usuarios(
        rol=g.get("rol"), localidad=g.get("localidad"),
        estado_verificacion=g.get("estado_verificacion"), cuenta=g.get("cuenta"),
        q=g.get("q"), desde=desde, hasta=hasta,
    )
    return render(request, "panel_admin/usuarios.html", {
        "resultados": resultados,
        "roles": Rol.choices,
        "estados": EstadoVerificacion.choices,
        "localidades": nombres_localidades(),
        "filtros": {
            "rol": g.get("rol") or "",
            "localidad": g.get("localidad") or "",
            "estado_verificacion": g.get("estado_verificacion") or "",
            "cuenta": g.get("cuenta") or "",
            "q": g.get("q") or "",
            "desde": desde.isoformat() if desde else "",
            "hasta": hasta.isoformat() if hasta else "",
        },
    })


@require_POST
@SOLO_ADMIN
def bloquear(request, usuario_id):
    try:
        usuario = servicios.bloquear(usuario_id, request.user)
        messages.success(request, f"{usuario.nombre} fue bloqueado.")
    except ErrorAdmin as error:
        messages.error(request, str(error))
    return redirect("panel_admin:usuarios")


@require_POST
@SOLO_ADMIN
def reactivar(request, usuario_id):
    try:
        usuario = servicios.reactivar(usuario_id)
        messages.success(request, f"{usuario.nombre} fue reactivado.")
    except ErrorAdmin as error:
        messages.error(request, str(error))
    return redirect("panel_admin:usuarios")


@SOLO_ADMIN
def editar_usuario(request, usuario_id):
    """GET: muestra el formulario. POST: guarda los cambios."""
    usuario = get_object_or_404(Usuario, pk=usuario_id)

    if request.method == "POST":
        try:
            servicios.actualizar_usuario(
                usuario_id, request.user,
                request.POST.get("nombre"), request.POST.get("correo"),
                request.POST.get("telefono"), request.POST.get("rol"),
            )
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("panel_admin:usuarios")
        except ErrorAdmin as error:
            messages.error(request, str(error))
            return redirect("panel_admin:editar_usuario", usuario_id=usuario_id)

    return render(request, "panel_admin/usuario_editar.html", {
        "usuario": usuario,
        "roles": Rol.choices,
    })


@SOLO_ADMIN
def historial(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    return render(request, "panel_admin/historial.html", {
        "usuario": usuario,
        "actividad": servicios.historial_actividad(usuario),
    })