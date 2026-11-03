from django.contrib import admin

from .models import ReporteSeguridad


@admin.register(ReporteSeguridad)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ("id", "reportante", "reportado", "estado", "fecha")
    list_filter = ("estado",)
