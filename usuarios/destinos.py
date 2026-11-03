"""A donde va cada rol despues de iniciar sesion.

En la version Java (CustomAuthSuccessHandler) los destinos eran:
  TRABAJADOR aprobado    -> /solicitudes/disponibles
  TRABAJADOR no aprobado -> /verificacion/reintentar
  CLIENTE                -> /solicitudes/nueva
  ADMINISTRADOR          -> /admin/verificaciones
  ALIADO_COMERCIAL       -> /anuncios/mios

Esas pantallas llegan en las fases siguientes. Mientras tanto todos los roles
(salvo el administrador) van al panel de la fase 1. Al construir cada fase solo
hay que cambiar el nombre de la URL en este archivo.
"""
from .models import Rol

PANEL = "usuarios:panel"

DESTINO_POR_ROL = {
    Rol.TRABAJADOR: PANEL,        # fase 2: "solicitudes:disponibles"
    Rol.CLIENTE: PANEL,           # fase 2: "solicitudes:nueva"
    Rol.ALIADO_COMERCIAL: PANEL,  # fase 5: "anuncios:mios"
    Rol.ADMINISTRADOR: "admin:index",  # fase 6: panel propio de verificaciones
}


def destino_para(usuario):
    return DESTINO_POR_ROL.get(usuario.rol, PANEL)
