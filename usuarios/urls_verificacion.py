from django.urls import path

from . import views_verificacion

app_name = "verificacion"

# Mismas rutas de la versión Java: /verificacion/reintentar y /verificacion/actualizar-documento
urlpatterns = [
    path("reintentar", views_verificacion.reintentar, name="reintentar"),
    path(
        "actualizar-documento",
        views_verificacion.actualizar_documento,
        name="actualizar_documento",
    ),
]
