"""Suscripción premium del trabajador (versión simulada de SuscripcionService.java).

El cobro es simulado: no hay pasarela real. Por defecto siempre se aprueba; si se
quiere probar el camino del rechazo, se baja PROBABILIDAD_PAGO_APROBADO en settings.
"""
import calendar
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from mensajeria.servicios import crear_notificacion

from .models import Suscripcion
from .servicios import ErrorPago


def costo_mensual():
    return Decimal(str(getattr(settings, "COSTO_SUSCRIPCION_MENSUAL", 19900)))


def probabilidad_aprobacion():
    return float(getattr(settings, "PROBABILIDAD_PAGO_APROBADO", 1.0))


def pago_aprobado():
    """Simula la respuesta de la pasarela (siempre aprueba con la configuración por defecto)."""
    return random.random() < probabilidad_aprobacion()


def de_usuario(usuario):
    """La suscripción del usuario, si alguna vez contrató el plan."""
    return Suscripcion.objects.filter(trabajador=usuario).first()


def esta_activa(usuario):
    """Activa solo si el periodo pagado todavía no vence."""
    suscripcion = de_usuario(usuario)
    return bool(
        suscripcion
        and suscripcion.activa
        and suscripcion.fecha_vencimiento > timezone.now()
    )


def _sumar_un_mes(momento):
    """Suma un mes calendario, sin pasarse del último día del mes destino."""
    anio = momento.year + (momento.month // 12)
    mes = momento.month % 12 + 1
    dia = min(momento.day, calendar.monthrange(anio, mes)[1])
    return momento.replace(year=anio, month=mes, day=dia)


def contratar(usuario):
    """Cobra el primer mes y activa (o renueva) el plan premium."""
    if not pago_aprobado():
        raise ErrorPago(
            "Tu pago fue rechazado por la pasarela. Verifica tu método de pago e inténtalo de nuevo."
        )

    ahora = timezone.now()
    suscripcion, _ = Suscripcion.objects.get_or_create(
        trabajador=usuario,
        defaults={"fecha_vencimiento": ahora},
    )
    suscripcion.plan = Suscripcion.Plan.PREMIUM
    suscripcion.activa = True
    suscripcion.renovacion_automatica = True
    suscripcion.fecha_inicio = ahora
    suscripcion.fecha_vencimiento = _sumar_un_mes(ahora)
    suscripcion.save()

    crear_notificacion(
        usuario, "SUSCRIPCION",
        "Tu suscripción premium está activa. Ya disfrutas de mayor visibilidad en las búsquedas.",
    )
    return suscripcion


def cancelar(usuario):
    """Apaga la renovación automática; los beneficios siguen hasta el vencimiento."""
    suscripcion = de_usuario(usuario)
    if suscripcion is None:
        raise ErrorPago("No tienes una suscripción activa.")

    suscripcion.renovacion_automatica = False
    suscripcion.save(update_fields=["renovacion_automatica"])

    vence = timezone.localtime(suscripcion.fecha_vencimiento).strftime("%d/%m/%Y")
    crear_notificacion(
        usuario, "SUSCRIPCION",
        f"Tu suscripción no se renovará automáticamente. Los beneficios siguen activos hasta el {vence}.",
    )
    return suscripcion


# ------------------------------------------------------------------ Tareas programadas
def renovar_vencidas():
    """Cobra las suscripciones vencidas con renovación automática.

    Es la versión Django de SuscripcionService.renovarVencidas(). Si el pago
    simulado falla, se avisa al trabajador y la suscripción sigue vencida (su
    fecha ya pasó), así que deja de dar beneficios.
    """
    vencidas = Suscripcion.objects.filter(
        activa=True,
        renovacion_automatica=True,
        fecha_vencimiento__lt=timezone.now(),
    ).select_related("trabajador")

    renovadas = 0
    rechazadas = 0
    for suscripcion in vencidas:
        if not pago_aprobado():
            crear_notificacion(
                suscripcion.trabajador, "SUSCRIPCION",
                f"No se pudo cobrar tu renovación premium ($ {costo_mensual()}). "
                "Tu suscripción quedó vencida y podrás reactivarla cuando quieras desde tu cuenta.",
            )
            rechazadas += 1
            continue

        ahora = timezone.now()
        suscripcion.fecha_inicio = ahora
        suscripcion.fecha_vencimiento = _sumar_un_mes(ahora)
        suscripcion.save(update_fields=["fecha_inicio", "fecha_vencimiento"])
        crear_notificacion(
            suscripcion.trabajador, "SUSCRIPCION",
            f"Tu suscripción premium se renovó automáticamente "
            f"($ {costo_mensual()} cobrados). Nueva vigencia hasta "
            f"{timezone.localtime(suscripcion.fecha_vencimiento):%d/%m/%Y}.",
        )
        renovadas += 1

    return {"vencidas": renovadas + rechazadas, "renovadas": renovadas, "rechazadas": rechazadas}


def recordar_proximos_a_vencer():
    """Avisa a quienes vencen dentro de los próximos días."""
    ahora = timezone.now()
    dias = int(getattr(settings, "DIAS_AVISO_SUSCRIPCION", 7))
    limite = ahora + timedelta(days=dias)
    proximas = Suscripcion.objects.filter(
        activa=True, fecha_vencimiento__gte=ahora, fecha_vencimiento__lte=limite
    ).select_related("trabajador")

    avisadas = 0
    for suscripcion in proximas:
        vence = timezone.localtime(suscripcion.fecha_vencimiento).strftime("%d/%m/%Y")
        crear_notificacion(
            suscripcion.trabajador, "SUSCRIPCION",
            f"Tu suscripción premium vence el {vence}. "
            "Si no la cancelas, se renovará automáticamente.",
        )
        avisadas += 1
    return {"avisadas": avisadas}
