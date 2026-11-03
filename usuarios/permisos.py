"""Control de acceso por rol (equivalente a hasRole(...) de Spring Security)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


def rol_requerido(*roles):
    """Decorador para vistas basadas en funciones.

    Uso:
        @rol_requerido(Rol.CLIENTE)
        def nueva_solicitud(request): ...
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if request.user.rol not in roles:
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return login_required(envoltura)

    return decorador


class RolRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin para vistas basadas en clases. Define `roles_permitidos`."""

    roles_permitidos = ()

    def test_func(self):
        return self.request.user.rol in self.roles_permitidos
