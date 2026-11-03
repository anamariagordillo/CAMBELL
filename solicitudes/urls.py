from django.urls import path

from . import views, views_trabajador

app_name = "solicitudes"

urlpatterns = [
    # Cliente
    path("nueva", views.nueva, name="nueva"),
    path("mis-solicitudes", views.mis_solicitudes, name="mis_solicitudes"),
    path("mis-solicitudes/historial", views.historial_cliente, name="historial_cliente"),
    path("<int:solicitud_id>/cancelar", views.cancelar, name="cancelar"),
    # Trabajador
    path("disponibles", views_trabajador.disponibles, name="disponibles"),
    path("mis-trabajos", views_trabajador.mis_trabajos, name="mis_trabajos"),
    path("mis-trabajos/historial", views_trabajador.historial_trabajos, name="historial_trabajos"),
    path("<int:solicitud_id>/aceptar", views_trabajador.aceptar, name="aceptar"),
    path("<int:solicitud_id>/rechazar", views_trabajador.rechazar, name="rechazar"),
    path("<int:solicitud_id>/liberar", views_trabajador.liberar, name="liberar"),
]