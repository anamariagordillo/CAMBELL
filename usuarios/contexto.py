"""Datos que necesita la barra de navegación en todas las páginas.

Equivale a fragments/layout.html + GlobalModelAttributes.java. Los enlaces se definen por
nombre de URL; si la pantalla todavía no existe (se construye en una fase posterior), el
enlace simplemente no aparece. Así la barra se completa sola al avanzar las fases.
"""
from django.urls import NoReverseMatch, reverse

from .models import EstadoVerificacion, Rol

NAV_ADMIN = [
    ("Verificaciones", "panel_admin:verificaciones"),
    ("Usuarios", "panel_admin:usuarios"),
    ("Reportes", "panel_admin:reportes"),
    ("Reembolsos", "panel_admin:reembolsos"),
    ("Anuncios", "panel_admin:anuncios"),
    ("Estadísticas", "panel_admin:estadisticas"),
]
NAV_TRABAJADOR_APROBADO = [
    ("Disponibles", "solicitudes:disponibles"),
    ("Mis trabajos", "solicitudes:mis_trabajos"),
    ("Historial", "solicitudes:historial_trabajos"),
    ("Mis ingresos", "pagos:ingresos"),
    ("Mi cobertura", "usuarios:cobertura"),
    ("Mi suscripción", "pagos:suscripcion"),
    ("Notificaciones", "mensajeria:notificaciones"),
]
NAV_TRABAJADOR_SIN_APROBAR = [
    ("Notificaciones", "mensajeria:notificaciones"),
]
NAV_CLIENTE = [
    ("Nueva solicitud", "solicitudes:nueva"),
    ("Mis solicitudes", "solicitudes:mis_solicitudes"),
    ("Historial", "solicitudes:historial_cliente"),
    ("Métodos de pago", "pagos:metodos"),
    ("Historial de pagos", "pagos:historial"),
    ("Notificaciones", "mensajeria:notificaciones"),
]
MENU_CLIENTE = [
    ("Ver perfil", "usuarios:perfil"),
    ("Cambiar mis datos", "usuarios:editar_perfil"),
    ("Cambiar contraseña", "usuarios:cambiar_password"),
    ("Hazte premium", "pagos:suscripcion"),
]
NAV_ALIADO = [
    ("Mis anuncios", "anuncios:mios"),
    ("Notificaciones", "mensajeria:notificaciones"),
]


def _resolver(items, vista_actual):
    resueltos = []
    for etiqueta, nombre in items:
        try:
            url = reverse(nombre)
        except NoReverseMatch:
            continue
        resueltos.append(
            {"etiqueta": etiqueta, "url": url, "nombre": nombre, "activo": nombre == vista_actual}
        )
    return resueltos


def navegacion(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}

    coincidencia = getattr(request, "resolver_match", None)
    vista = coincidencia.view_name if coincidencia else ""
    rol = usuario.rol

    if rol == Rol.ADMINISTRADOR:
        items = NAV_ADMIN
    elif rol == Rol.TRABAJADOR:
        aprobado = usuario.estado_verificacion == EstadoVerificacion.APROBADO
        items = NAV_TRABAJADOR_APROBADO if aprobado else NAV_TRABAJADOR_SIN_APROBAR
    elif rol == Rol.CLIENTE:
        items = NAV_CLIENTE
    else:
        items = NAV_ALIADO

    return {
        "nav_items": _resolver(items, vista),
        "menu_items": _resolver(MENU_CLIENTE, vista) if rol == Rol.CLIENTE else [],
        "no_leidos": usuario.notificaciones.filter(leido=False).count(),
        "estado_verificacion": usuario.estado_verificacion,
    }
