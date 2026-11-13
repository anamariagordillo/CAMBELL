"""Reglas de la cuenta: contrasenas, intentos fallidos y recuperacion.

Equivale a UsuarioService (cambiarPassword, desactivarCuenta) y a
RecuperacionPasswordService de la version Java. Se separa de las vistas para que
las vistas queden cortas y las reglas se puedan probar por separado.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import TokenRecuperacion, Usuario
from .politicas import cumple_politica


# ---------------------------------------------------------------- Contrasenas
def cambiar_password(usuario, password_actual, password_nueva, exigir_actual=True):
    """Cambia la contrasena del usuario.

    `exigir_actual=False` se usa cuando el sistema obliga el cambio: en ese caso
    no se pide la contrasena vieja (porque puede estar vencida por politica).
    Devuelve True si se cambio y False si la contrasena actual no coincide.
    """
    if exigir_actual and not usuario.check_password(password_actual):
        return False

    usuario.set_password(password_nueva)
    usuario.debe_cambiar_password = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.save(
        update_fields=[
            "password",
            "debe_cambiar_password",
            "intentos_fallidos",
            "bloqueado_hasta",
        ]
    )
    return True


def desactivar_cuenta(usuario):
    """Desactiva la cuenta: en Java se hace con usuario.bloqueado = true."""
    usuario.bloqueado = True
    usuario.save(update_fields=["bloqueado"])


# ------------------------------------------------------- Intentos fallidos
def _buscar_por_correo(correo):
    return Usuario.objects.filter(correo__iexact=(correo or "").strip()).first()


def registrar_intento_fallido(correo):
    """Suma un intento fallido y bloquea la cuenta al llegar al limite.

    Si la cuenta ya esta bloqueada (por el administrador o temporalmente) no se
    sigue sumando, para que el bloqueo no se renueve en cada intento.
    """
    usuario = _buscar_por_correo(correo)
    if usuario is None or usuario.bloqueado or usuario.bloqueo_temporal_activo:
        return usuario

    usuario.intentos_fallidos += 1
    campos = ["intentos_fallidos"]

    if usuario.intentos_fallidos >= settings.MAX_INTENTOS_FALLIDOS:
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = timezone.now() + timedelta(
            minutes=settings.MINUTOS_BLOQUEO
        )
        campos.append("bloqueado_hasta")

    usuario.save(update_fields=campos)
    return usuario


def reiniciar_intentos(usuario):
    """Al entrar bien se borra el historial de intentos fallidos."""
    if usuario.intentos_fallidos or usuario.bloqueado_hasta:
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])


# ------------------------------------------------------- Recuperar contrasena
def crear_token_recuperacion(usuario):
    """Crea un token nuevo y anula los anteriores que siguieran sin usar."""
    TokenRecuperacion.objects.filter(usuario=usuario, usado=False).update(usado=True)
    return TokenRecuperacion.objects.create(
        usuario=usuario,
        token=secrets.token_urlsafe(32),
        expiracion=timezone.now() + timedelta(hours=settings.HORAS_TOKEN_RECUPERACION),
    )


def obtener_token_valido(token):
    """Devuelve el token si existe, no se ha usado y no ha expirado."""
    if not token:
        return None
    return TokenRecuperacion.objects.filter(
        token=token,
        usado=False,
        expiracion__gt=timezone.now(),
    ).select_related("usuario").first()


def enviar_correo_recuperacion(usuario, enlace):
    """Envia el enlace de recuperacion.

    En desarrollo (sin EMAIL_HOST_USER) Django imprime el correo en la consola,
    asi que se puede probar sin configurar nada.
    """
    asunto = "Cambell - Restablece tu contraseña"
    mensaje = (
        f"Hola {usuario.nombre},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña de Cambell.\n"
        f"Abre este enlace (vence en {settings.HORAS_TOKEN_RECUPERACION} hora(s)):\n\n"
        f"{enlace}\n\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña seguirá igual.\n\n"
        "Equipo Cambell"
    )
    send_mail(asunto, mensaje, settings.DEFAULT_FROM_EMAIL, [usuario.correo], fail_silently=True)


def restablecer_password(token, password_nueva):
    """Cambia la contrasena usando un token valido. Devuelve True o False."""
    registro = obtener_token_valido(token)
    if registro is None:
        return False

    usuario = registro.usuario
    usuario.set_password(password_nueva)
    usuario.debe_cambiar_password = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.save(
        update_fields=[
            "password",
            "debe_cambiar_password",
            "intentos_fallidos",
            "bloqueado_hasta",
        ]
    )

    registro.usado = True
    registro.save(update_fields=["usado"])
    return True
