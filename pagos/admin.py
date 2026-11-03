from django.contrib import admin

from .models import MetodoPago, Pago, Reembolso, Suscripcion


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("id", "solicitud", "monto_total", "comision", "estado", "estado_transferencia")
    list_filter = ("estado", "estado_transferencia")


admin.site.register(MetodoPago)
admin.site.register(Reembolso)
admin.site.register(Suscripcion)
