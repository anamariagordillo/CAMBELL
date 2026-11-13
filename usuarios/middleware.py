"""Middleware que obliga a cambiar la contrasena cuando no cumple la politica.

Equivale a PasswordChangeFilter.java: si el usuario tiene `debe_cambiar_password`,
solo puede entrar al login, al logout y a la pantalla de cambio de contrasena.
"""
from django.shortcuts import redirect

# Rutas que si se pueden visitar aunque la contrasena este vencida.
RUTAS_PERMITIDAS = (
    "/login",
    "/logout",
    "/cambiar-password",
    "/recuperar-password",
    "/restablecer-password",
    "/static/",
    "/uploads/",
)


class ForzarCambioPasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)

        if usuario is not None and usuario.is_authenticated and usuario.debe_cambiar_password:
            ruta = request.path
            # /django-admin/ se deja libre para que un administrador no quede encerrado.
            permitida = ruta.startswith(RUTAS_PERMITIDAS) or ruta.startswith("/django-admin/")
            if not permitida:
                return redirect("usuarios:cambiar_password")

        return self.get_response(request)
