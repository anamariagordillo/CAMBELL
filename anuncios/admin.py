from django.contrib import admin

from .models import Anuncio


@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "aliado", "estado", "fecha_creacion")
    list_filter = ("estado",)
