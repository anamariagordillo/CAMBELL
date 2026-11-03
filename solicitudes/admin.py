from django.contrib import admin

from .models import Calificacion, Solicitud


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ("id", "categoria", "estado", "cliente", "trabajador", "urgencia", "fecha_creacion")
    list_filter = ("estado", "categoria", "urgencia")
    search_fields = ("descripcion", "cliente__nombre", "trabajador__nombre")


admin.site.register(Calificacion)
