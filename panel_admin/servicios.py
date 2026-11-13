"""Reglas del panel de administración: verificaciones, usuarios e historial de actividad.

Equivale a las partes de UsuarioService.java y AdminService.java que usa AdminController.
"""
import re
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.utils import timezone

from mensajeria.servicios import crear_notificacion
from pagos.models import Pago
from seguridad.models import ReporteSeguridad
from solicitudes.models import Solicitud
from usuarios.models import EstadoVerificacion, Rol, Usuario


class ErrorAdmin(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle al administrador."""


def _buscar(usuario_id):
    try:
        return Usuario.objects.get(pk=usuario_id)
    except Usuario.DoesNotExist:
        raise ErrorAdmin("Usuario no encontrado")


# ------------------------------------------------------------------ Verificaciones
def listar_pendientes():
    """Trabajadores que esperan que un administrador valide su identidad."""
    return Usuario.objects.filter(
        rol=Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.PENDIENTE
    ).order_by("id")


def _cambiar_verificacion(usuario_id, estado, mensaje):
    usuario = _buscar(usuario_id)
    if usuario.rol != Rol.TRABAJADOR:
        raise ErrorAdmin("Solo se verifican trabajadores.")
    usuario.estado_verificacion = estado
    usuario.motivo_verificacion = ""  # al decidir, el motivo de la revisión ya no aplica
    usuario.save(update_fields=["estado_verificacion", "motivo_verificacion"])
    crear_notificacion(usuario, "VERIFICACION", mensaje)
    return usuario


def aprobar_trabajador(usuario_id):
    return _cambiar_verificacion(
        usuario_id, EstadoVerificacion.APROBADO,
        "Tu verificación fue APROBADA. Ya puedes ofrecer y aceptar trabajos.",
    )


def rechazar_trabajador(usuario_id):
    return _cambiar_verificacion(
        usuario_id, EstadoVerificacion.RECHAZADO,
        "Tu verificación fue RECHAZADA. Revisa tus documentos e inténtalo de nuevo.",
    )


# ------------------------------------------------------------------ Usuarios
def _inicio_del_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def buscar_usuarios(rol=None, localidad=None, estado_verificacion=None, cuenta=None,
                    q=None, desde=None, hasta=None):
    """Filtros combinados (todos opcionales). Los valores inválidos se ignoran."""
    usuarios = Usuario.objects.all()

    if rol in Rol.values:
        usuarios = usuarios.filter(rol=rol)
    if localidad:
        usuarios = usuarios.filter(localidad=localidad)
    if estado_verificacion in EstadoVerificacion.values:
        usuarios = usuarios.filter(estado_verificacion=estado_verificacion)
    if cuenta == "activos":
        usuarios = usuarios.filter(bloqueado=False)
    elif cuenta == "bloqueados":
        usuarios = usuarios.filter(bloqueado=True)
    if q and q.strip():
        texto = q.strip()
        usuarios = usuarios.filter(
            Q(nombre__icontains=texto) | Q(correo__icontains=texto) | Q(telefono__icontains=texto)
        )
    if desde:
        usuarios = usuarios.filter(fecha_registro__gte=_inicio_del_dia(desde))
    if hasta:
        usuarios = usuarios.filter(fecha_registro__lt=_inicio_del_dia(hasta + timedelta(days=1)))

    return usuarios.order_by("-id")


def bloquear(usuario_id, administrador):
    usuario = _buscar(usuario_id)
    if usuario.id == administrador.id:
        raise ErrorAdmin("No puedes bloquear tu propia cuenta.")
    usuario.bloqueado = True
    usuario.save(update_fields=["bloqueado"])
    return usuario


def reactivar(usuario_id):
    usuario = _buscar(usuario_id)
    usuario.bloqueado = False
    usuario.save(update_fields=["bloqueado"])
    return usuario


def actualizar_usuario(usuario_id, administrador, nombre, correo, telefono, rol):
    """Edita datos básicos. Los campos vacíos no se tocan (igual que en la versión Java)."""
    usuario = _buscar(usuario_id)

    nombre = (nombre or "").strip()
    correo = (correo or "").strip().lower()
    telefono = (telefono or "").strip()

    if correo:
        try:
            validate_email(correo)
        except ValidationError:
            raise ErrorAdmin("El correo no es válido.")
        if Usuario.objects.filter(correo__iexact=correo).exclude(pk=usuario.pk).exists():
            raise ErrorAdmin("Ya existe un usuario con ese correo.")

    if telefono:
        if not re.fullmatch(r"[0-9]{7,15}", telefono):
            raise ErrorAdmin("El teléfono debe tener solo números (7 a 15 dígitos).")
        if Usuario.objects.filter(telefono=telefono).exclude(pk=usuario.pk).exists():
            raise ErrorAdmin("Ya existe un usuario con ese teléfono.")

    if rol:
        if rol not in Rol.values:
            raise ErrorAdmin("El rol no es válido.")
        if usuario.id == administrador.id and rol != usuario.rol:
            raise ErrorAdmin("No puedes cambiar tu propio rol.")

    if nombre:
        usuario.nombre = nombre[:100]
    if correo:
        usuario.correo = correo
    if telefono:
        usuario.telefono = telefono
    if rol:
        usuario.rol = rol
    usuario.save()
    return usuario


# ------------------------------------------------------------------ Historial
def historial_actividad(usuario):
    """Todo lo que hizo o le pasó al usuario, del más reciente al más antiguo."""
    actividad = []

    for s in Solicitud.objects.filter(cliente=usuario):
        actividad.append({
            "fecha": s.fecha_creacion, "tipo": "Solicitud",
            "detalle": f"Solicitó: {s.descripcion} ({s.get_estado_display()})",
        })
    for s in Solicitud.objects.filter(trabajador=usuario):
        actividad.append({
            "fecha": s.fecha_creacion, "tipo": "Solicitud",
            "detalle": f"Atendió: {s.descripcion} ({s.get_estado_display()})",
        })
    for p in Pago.objects.filter(cliente=usuario):
        actividad.append({
            "fecha": p.fecha_pago, "tipo": "Pago",
            "detalle": f"Pagó ${p.monto_total} ({p.get_estado_display()})",
        })
    for p in Pago.objects.filter(trabajador=usuario):
        actividad.append({
            "fecha": p.fecha_pago, "tipo": "Pago",
            "detalle": f"Recibió ${p.neto_trabajador} ({p.get_estado_display()})",
        })
    for r in ReporteSeguridad.objects.filter(reportado=usuario):
        actividad.append({
            "fecha": r.fecha, "tipo": "Reporte", "detalle": f"Recibió un reporte: {r.motivo}",
        })
    for r in ReporteSeguridad.objects.filter(reportante=usuario):
        actividad.append({
            "fecha": r.fecha, "tipo": "Reporte", "detalle": f"Realizó un reporte: {r.motivo}",
        })

    # Los que no tienen fecha (por ejemplo un pago sin fecha) van al final.
    actividad.sort(key=lambda a: (a["fecha"] is None, -(a["fecha"].timestamp() if a["fecha"] else 0)))
    return actividad