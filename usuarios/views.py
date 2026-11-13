from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from . import servicios
from .catalogos import OFICIOS, TIPOS_ALIADO
from .destinos import destino_para
from .forms import (
    CambiarPasswordForm,
    CoberturaForm,
    LoginForm,
    PerfilForm,
    RecuperarPasswordForm,
    RegistroForm,
    RestablecerPasswordForm,
)
from .localidades import nombres_localidades
from .models import CoberturaTrabajador, Rol, Usuario
from .permisos import rol_requerido


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

    def form_invalid(self, form):
        # Cada intento fallido suma. Al llegar al límite, la cuenta se bloquea
        # temporalmente (ver usuarios/servicios.py).
        servicios.registrar_intento_fallido(form.data.get("username"))
        return super().form_invalid(form)

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # Entró bien: se limpia el contador de intentos.
        servicios.reiniciar_intentos(self.request.user)
        # Igual que Java: si la contraseña no cumple la política vigente,
        # se marca para obligar el cambio antes de seguir navegando.
        if not servicios.cumple_politica(form.cleaned_data.get("password", "")):
            self.request.user.debe_cambiar_password = True
            self.request.user.save(update_fields=["debe_cambiar_password"])
        return respuesta


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


# ============================================================ Recuperar contraseña
def recuperar_password(request):
    """Pide el correo y envía un enlace (si la cuenta existe)."""
    if request.user.is_authenticated:
        return redirect(destino_para(request.user))

    if request.method == "POST":
        form = RecuperarPasswordForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data["correo"]
            usuario = Usuario.objects.filter(correo__iexact=correo).first()
            if usuario is not None:
                token = servicios.crear_token_recuperacion(usuario)
                enlace = request.build_absolute_uri(
                    reverse("usuarios:restablecer_password") + f"?token={token.token}"
                )
                servicios.enviar_correo_recuperacion(usuario, enlace)

            # Se responde igual exista o no el correo, para no revelar cuentas.
            messages.success(
                request,
                "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.",
            )
            return redirect("usuarios:recuperar_password")
    else:
        form = RecuperarPasswordForm()

    return render(request, "usuarios/recuperar_password.html", {"form": form})


def restablecer_password(request):
    """Guarda la nueva contraseña si el token del enlace es válido."""
    token = request.POST.get("token") or request.GET.get("token") or ""

    if request.method == "POST":
        form = RestablecerPasswordForm(request.POST)
        if form.is_valid():
            if servicios.restablecer_password(token, form.cleaned_data["password"]):
                messages.success(request, "Contraseña restablecida. Ya puedes iniciar sesión.")
                return redirect("usuarios:login")
            form.add_error(None, "El enlace es inválido o ha expirado. Solicita uno nuevo.")
    else:
        form = RestablecerPasswordForm(initial={"token": token})

    return render(
        request,
        "usuarios/restablecer_password.html",
        {
            "form": form,
            "token": token,
            "token_valido": bool(servicios.obtener_token_valido(token)),
        },
    )


# ============================================================ Cuenta
@login_required
def cambiar_password(request):
    forzado = request.user.debe_cambiar_password

    if request.method == "POST":
        form = CambiarPasswordForm(request.POST, usuario=request.user, forzado=forzado)
        if form.is_valid():
            servicios.cambiar_password(
                request.user,
                form.cleaned_data["password_actual"],
                form.cleaned_data["password_nueva"],
                exigir_actual=not forzado,
            )
            update_session_auth_hash(request, request.user)
            messages.success(request, "Contraseña actualizada correctamente.")
            return redirect(destino_para(request.user))
    else:
        form = CambiarPasswordForm(usuario=request.user, forzado=forzado)

    return render(
        request,
        "usuarios/cambiar_password.html",
        {"form": form, "forzado": forzado},
    )


@login_required
def perfil(request):
    return render(request, "usuarios/perfil.html")


@login_required
def editar_perfil(request):
    if request.method == "POST":
        form = PerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil actualizado correctamente.")
            return redirect("usuarios:perfil")
    else:
        form = PerfilForm(instance=request.user)

    return render(request, "usuarios/editar_perfil.html", {"form": form})


@rol_requerido(Rol.TRABAJADOR)
def cobertura(request):
    """Zona, oficios y horario del trabajador (la usará el motor de recomendación)."""
    datos, _ = CoberturaTrabajador.objects.get_or_create(trabajador=request.user)

    if request.method == "POST":
        form = CoberturaForm(request.POST, instance=datos)
        if form.is_valid():
            form.save()
            messages.success(request, "Tu cobertura y disponibilidad se guardaron.")
            return redirect("usuarios:cobertura")
    else:
        form = CoberturaForm(instance=datos)

    return render(request, "usuarios/cobertura.html", {"form": form, "cobertura": datos})


@login_required
@require_POST
def desactivar_cuenta(request):
    """Desactiva la cuenta (igual que Java: usuario.bloqueado = true) y cierra sesión."""
    servicios.desactivar_cuenta(request.user)
    logout(request)
    messages.success(request, "Tu cuenta fue desactivada.")
    return redirect("usuarios:login")
