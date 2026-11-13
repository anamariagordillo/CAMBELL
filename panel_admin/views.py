"""Pantallas del administrador (el panel 'Cambell · Admin')."""
import logging
import mimetypes
from datetime import date

from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from anuncios import servicios as servicios_anuncios
from anuncios.models import Anuncio
from pagos import reembolsos as servicios_reembolso
from pagos.models import Pago
from pagos.servicios import ErrorPago
from seguridad import servicios as servicios_seguridad
from seguridad.models import ReporteSeguridad
from seguridad.servicios import ErrorReporte
from solicitudes.models import EstadoSolicitud
from usuarios.localidades import nombres_localidades
from usuarios.models import EstadoVerificacion, Rol, Usuario
from usuarios.permisos import rol_requerido

from . import estadisticas as servicios_estadisticas
from . import servicios
from .servicios import ErrorAdmin

logger = logging.getLogger(__name__)
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


# ------------------------------------------------------------------ Anuncios
@SOLO_ADMIN
def anuncios(request):
    return render(request, "panel_admin/anuncios.html", {
        "pendientes": servicios_anuncios.listar_por_estado(Anuncio.Estado.PENDIENTE),
        "publicados": servicios_anuncios.listar_por_estado(Anuncio.Estado.PUBLICADO),
        "rechazados": servicios_anuncios.listar_por_estado(Anuncio.Estado.RECHAZADO),
    })


@require_POST
@SOLO_ADMIN
def aprobar_anuncio(request, anuncio_id):
    try:
        anuncio = servicios_anuncios.aprobar(anuncio_id)
        messages.success(request, f'Anuncio "{anuncio.titulo}" publicado.')
    except servicios_anuncios.ErrorAnuncio as error:
        messages.error(request, str(error))
    return redirect("panel_admin:anuncios")


@require_POST
@SOLO_ADMIN
def rechazar_anuncio(request, anuncio_id):
    try:
        anuncio = servicios_anuncios.rechazar(anuncio_id, request.POST.get("motivo"))
        messages.success(request, f'Anuncio "{anuncio.titulo}" rechazado.')
    except servicios_anuncios.ErrorAnuncio as error:
        messages.error(request, str(error))
    return redirect("panel_admin:anuncios")


# ------------------------------------------------------------------ Reembolsos
@SOLO_ADMIN
def reembolsos(request):
    return render(request, "panel_admin/reembolsos.html", {
        "pagos": servicios_reembolso.pagos_completados(),
        "reembolsados": servicios_reembolso.pagos_reembolsados(),
        "reembolsos": servicios_reembolso.listar_todos(),
    })


@require_POST
@SOLO_ADMIN
def iniciar_reembolso(request, pago_id):
    try:
        servicios_reembolso.reembolsar(pago_id, request.POST.get("motivo"))
        messages.success(request, "Reembolso registrado correctamente.")
    except ErrorPago as error:
        messages.error(request, str(error))
    return redirect("panel_admin:reembolsos")


# ------------------------------------------------------------------ Reportes de seguridad
@SOLO_ADMIN
def reportes(request):
    g = request.GET
    desde, hasta = _fecha(g.get("desde")), _fecha(g.get("hasta"))
    return render(request, "panel_admin/reportes.html", {
        "reportes": servicios_seguridad.buscar(
            estado=g.get("estado"), q=g.get("q"), desde=desde, hasta=hasta
        ),
        "estados": ReporteSeguridad.Estado.choices,
        "filtros": {
            "estado": g.get("estado") or "",
            "q": g.get("q") or "",
            "desde": desde.isoformat() if desde else "",
            "hasta": hasta.isoformat() if hasta else "",
        },
    })


@require_POST
@SOLO_ADMIN
def bloquear_reportado(request, reporte_id):
    try:
        reporte = servicios_seguridad.buscar_uno(reporte_id)
        servicios.bloquear(reporte.reportado_id, request.user)
        servicios_seguridad.marcar_bloqueado(reporte_id)
        messages.success(
            request,
            f"{reporte.reportado.nombre} fue bloqueado y el reporte quedó atendido.",
        )
    except (ErrorAdmin, ErrorReporte) as error:
        messages.error(request, str(error))
    return redirect("panel_admin:reportes")


@require_POST
@SOLO_ADMIN
def descartar_reporte(request, reporte_id):
    try:
        servicios_seguridad.descartar(reporte_id)
        messages.success(request, "Reporte descartado.")
    except ErrorReporte as error:
        messages.error(request, str(error))
    return redirect("panel_admin:reportes")


# ------------------------------------------------------------------ Estadísticas
def _armar_reporte_estadisticas(request):
    """Lee los filtros de la URL, ajusta el rango y calcula el reporte."""
    hoy = timezone.localdate()
    inicio = servicios_estadisticas.fecha_primer_registro()
    desde = _fecha(request.GET.get("desde"))
    hasta = _fecha(request.GET.get("hasta"))
    desde, hasta = servicios_estadisticas.normalizar_rango(desde, hasta, inicio, hoy)
    reporte = servicios_estadisticas.armar_reporte(
        rol=request.GET.get("rol"),
        estado_solicitud=request.GET.get("estado_solicitud"),
        estado_pago=request.GET.get("estado_pago"),
        desde=desde,
        hasta=hasta,
    )
    return reporte, inicio, hoy


@SOLO_ADMIN
def estadisticas(request):
    try:
        reporte, inicio, hoy = _armar_reporte_estadisticas(request)
    except ErrorAdmin as error:
        messages.error(request, str(error))
        return redirect("panel_admin:estadisticas")

    return render(request, "panel_admin/estadisticas.html", {
        "reporte": reporte,
        "roles": Rol.choices,
        "estados_solicitud": EstadoSolicitud.choices,
        "estados_pago": Pago.Estado.choices,
        "filtros": {
            "rol": reporte.rol or "",
            "estado_solicitud": reporte.estado_solicitud or "",
            "estado_pago": reporte.estado_pago or "",
            "desde": reporte.desde.isoformat() if reporte.desde else "",
            "hasta": reporte.hasta.isoformat() if reporte.hasta else "",
        },
        "fecha_minima": inicio,
        "fecha_maxima": hoy,
    })


@SOLO_ADMIN
def exportar_estadisticas(request, formato):
    """Descarga el reporte en PDF (formato=pdf) o Excel (cualquier otro valor)."""
    try:
        reporte, _, hoy = _armar_reporte_estadisticas(request)
    except ErrorAdmin as error:
        messages.error(request, str(error))
        return redirect("panel_admin:estadisticas")

    try:
        contenido, tipo, extension = servicios_estadisticas.generar(formato, reporte)
    except Exception:
        logger.exception("No se pudo generar el reporte de estadísticas")
        messages.error(request, "No se pudo generar el reporte. Inténtalo de nuevo.")
        return redirect("panel_admin:estadisticas")

    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = (
        f'attachment; filename="estadisticas_{hoy.isoformat()}.{extension}"'
    )
    return respuesta