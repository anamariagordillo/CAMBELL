from django.urls import path

from . import views

app_name = "seguridad"

# Misma ruta de la versión Java: /solicitudes/{id}/reportar
urlpatterns = [
    path(
        "solicitudes/<int:solicitud_id>/reportar",
        views.reportar,
        name="reportar",
    ),
]
