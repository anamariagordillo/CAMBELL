from django.urls import path

from . import views, views_cierre, views_trabajador

app_name = "solicitudes"

urlpatterns = [
    # Cliente
    path("nueva", views.nueva, name="nueva"),
    path("mis-solicitudes", views.mis_solicitudes, name="mis_solicitudes"),
    path("mis-solicitudes/historial", views.historial_cliente, name="historial_cliente"),
    path("<int:solicitud_id>/cancelar", views.cancelar, name="cancelar"),
    path("<int:solicitud_id>/calificar", views_cierre.calificar, name="calificar"),
    path("<int:solicitud_id>/trabajador", views_cierre.perfil_trabajador, name="perfil_trabajador"),
    # Trabajador
    path("disponibles", views_trabajador.disponibles, name="disponibles"),
    path("mis-trabajos", views_trabajador.mis_trabajos, name="mis_trabajos"),
    path("mis-trabajos/historial", views_trabajador.historial_trabajos, name="historial_trabajos"),
    path("<int:solicitud_id>/aceptar", views_trabajador.aceptar, name="aceptar"),
    path("<int:solicitud_id>/rechazar", views_trabajador.rechazar, name="rechazar"),
    path("<int:solicitud_id>/liberar", views_trabajador.liberar, name="liberar"),
    path("<int:solicitud_id>/finalizar", views_cierre.finalizar, name="finalizar"),
    path("<int:solicitud_id>/finalizado", views_cierre.finalizado, name="finalizado"),
]