"""Consultas de lectura sobre los pagos."""
from .models import Pago


def historial_cliente(cliente):
    """Los pagos del cliente, del más reciente al más antiguo."""
    return (
        Pago.objects.filter(cliente=cliente)
        .select_related("solicitud")
        .order_by("-fecha_pago", "-id")
    )