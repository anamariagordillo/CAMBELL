"""Reglas de los métodos de pago del cliente (parte de PagoService.java).

Importante: del número de la tarjeta NUNCA se guarda el número completo; solo los últimos
4 dígitos enmascarados (por ejemplo "•••• 4242").
"""
import re

from django.utils import timezone

from .models import MetodoPago


class ErrorPago(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle a la persona."""


def enmascarar(numero):
    """'4242 4242 4242 4242' -> '•••• 4242'. Si tiene 4 dígitos o menos, se deja igual."""
    limpio = re.sub(r"\D", "", numero or "")
    if len(limpio) <= 4:
        return limpio
    return "•••• " + limpio[-4:]


def es_tarjeta_vigente(mes, anio):
    """Una tarjeta sirve hasta el último día de su mes de vencimiento."""
    if mes is None or anio is None:
        return False
    if not (1 <= mes <= 12):
        return False
    hoy = timezone.localdate()
    return (anio, mes) >= (hoy.year, hoy.month)


def _buscar_del_cliente(metodo_id, cliente, accion):
    try:
        metodo = MetodoPago.objects.get(pk=metodo_id)
    except MetodoPago.DoesNotExist:
        raise ErrorPago("Método de pago no encontrado")
    if metodo.cliente_id != cliente.id:
        raise ErrorPago(f"No puedes {accion} un método de pago que no te pertenece.")
    return metodo


def registrar_metodo(cliente, tipo, titular, numero, mes_vencimiento=None, anio_vencimiento=None):
    if tipo not in MetodoPago.Tipo.values:
        raise ErrorPago("El tipo de método de pago no es válido.")

    titular = (titular or "").strip()
    if not titular:
        raise ErrorPago("El nombre del titular es obligatorio.")
    if len(titular) > 100:
        raise ErrorPago("El nombre del titular es demasiado largo (máximo 100 caracteres).")

    if len(re.sub(r"\D", "", numero or "")) < 4:
        raise ErrorPago("Ingresa un número válido (mínimo 4 dígitos).")

    if tipo == MetodoPago.Tipo.TARJETA:
        if not es_tarjeta_vigente(mes_vencimiento, anio_vencimiento):
            raise ErrorPago("La tarjeta está vencida o los datos de vencimiento son inválidos.")
    else:
        mes_vencimiento = anio_vencimiento = None  # solo las tarjetas vencen

    return MetodoPago.objects.create(
        cliente=cliente,
        tipo=tipo,
        titular=titular,
        numero_enmascarado=enmascarar(numero),
        mes_vencimiento=mes_vencimiento,
        anio_vencimiento=anio_vencimiento,
    )


def editar_metodo(metodo_id, cliente, titular, mes_vencimiento=None, anio_vencimiento=None):
    metodo = _buscar_del_cliente(metodo_id, cliente, "editar")

    titular = (titular or "").strip()
    if not titular:
        raise ErrorPago("El nombre del titular es obligatorio.")
    if len(titular) > 100:
        raise ErrorPago("El nombre del titular es demasiado largo (máximo 100 caracteres).")

    if metodo.tipo == MetodoPago.Tipo.TARJETA:
        if not es_tarjeta_vigente(mes_vencimiento, anio_vencimiento):
            raise ErrorPago("La tarjeta está vencida o los datos de vencimiento son inválidos.")
        metodo.mes_vencimiento = mes_vencimiento
        metodo.anio_vencimiento = anio_vencimiento

    metodo.titular = titular
    metodo.save()
    return metodo


def eliminar_metodo(metodo_id, cliente):
    metodo = _buscar_del_cliente(metodo_id, cliente, "eliminar")
    metodo.delete()


def listar_metodos(cliente):
    return MetodoPago.objects.filter(cliente=cliente).order_by("id")


def buscar_metodo_del_cliente(metodo_id, cliente):
    """El método si existe y es del cliente; si no, None (no revela si existe para otro)."""
    if not metodo_id:
        return None
    return MetodoPago.objects.filter(pk=metodo_id, cliente=cliente).first()