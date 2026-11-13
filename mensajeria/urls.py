from django.urls import path

from . import views

app_name = "mensajeria"

# Rutas equivalentes a las de la versión Java:
#   /solicitudes/{id}/mensajes y /notificaciones
urlpatterns = [
    path("solicitudes/<int:solicitud_id>/mensajes", views.chat, name="chat"),
    path("notificaciones", views.notificaciones, name="notificaciones"),
    path("notificaciones/<int:notificacion_id>/leer", views.marcar_leida, name="marcar_leida"),
    path("notificaciones/marcar-todas", views.marcar_todas, name="marcar_todas"),
    path(
        "notificaciones/<int:notificacion_id>/eliminar",
        views.eliminar,
        name="eliminar",
    ),
]
