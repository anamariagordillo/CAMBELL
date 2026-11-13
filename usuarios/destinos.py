"""A donde va cada rol despues de iniciar sesion.

En la version Java (CustomAuthSuccessHandler) los destinos eran:
  TRABAJADOR aprobado    -> /solicitudes/disponibles
  TRABAJADOR no aprobado -> /verificacion/reintentar
  CLIENTE                -> /solicitudes/nueva
  ADMINISTRADOR          -> /admin/verificaciones
  ALIADO_COMERCIAL       -> /anuncios/mios

Las pantallas pendientes se activan al construirlas: basta con cambiar el nombre de la URL aqui.
"""
from .models import Rol

PANEL = "usuarios:panel"

DESTINO_POR_ROL = {
    Rol.TRABAJADOR: "solicitudes:disponibles",
    Rol.CLIENTE: "solicitudes:nueva",
    Rol.ALIADO_COMERCIAL: PANEL,  # fase 5: "anuncios:mios"
    Rol.ADMINISTRADOR: "panel_admin:verificaciones",
}


def destino_para(usuario):
    return DESTINO_POR_ROL.get(usuario.rol, PANEL)