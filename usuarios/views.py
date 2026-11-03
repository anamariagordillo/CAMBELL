from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render, resolve_url
from django.views.generic import TemplateView

from .catalogos import OFICIOS, TIPOS_ALIADO
from .destinos import destino_para
from .forms import LoginForm, RegistroForm
from .localidades import nombres_localidades
from .models import Rol


class InicioView(TemplateView):
    template_name = "index.html"

    def get_context_data(self, **kwargs):
        from anuncios.models import Anuncio

        contexto = super().get_context_data(**kwargs)
        contexto["anuncios"] = Anuncio.objects.filter(estado=Anuncio.Estado.PUBLICADO)[:6]
        return contexto


class IniciarSesionView(LoginView):
    """Login por correo. Redirige según el rol (antes: CustomAuthSuccessHandler)."""

    template_name = "usuarios/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return resolve_url(destino_para(self.request.user))


def registro(request):
    if request.user.is_authenticated:
        return redirect(destino_para(request.user))

    if request.method == "POST":
        form = RegistroForm(request.POST, request.FILES)
        if form.is_valid():
            usuario = form.save()
            if usuario.rol == Rol.TRABAJADOR:
                messages.success(
                    request,
                    "Registro exitoso. Tu cuenta está en revisión hasta confirmar tu identidad. "
                    "Ya puedes iniciar sesión.",
                )
            else:
                messages.success(request, "Registro exitoso. Ya puedes iniciar sesión.")
            return redirect("usuarios:login")
    else:
        form = RegistroForm()

    return render(
        request,
        "usuarios/registro.html",
        {
            "form": form,
            "localidades": nombres_localidades(),
            "oficios": OFICIOS,
            "tipos_aliado": TIPOS_ALIADO,
        },
    )


@login_required
def panel(request):
    return render(request, "usuarios/panel.html")
