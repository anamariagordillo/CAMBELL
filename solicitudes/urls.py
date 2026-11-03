from django.urls import path

from . import views

app_name = "solicitudes"

urlpatterns = [
    path("nueva", views.nueva, name="nueva"),
    path("mis-solicitudes", views.mis_solicitudes, name="mis_solicitudes"),
    path("mis-solicitudes/historial", views.historial_cliente, name="historial_cliente"),
    path("<int:solicitud_id>/cancelar", views.cancelar, name="cancelar"),
]