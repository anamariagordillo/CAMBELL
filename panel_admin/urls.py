from django.urls import path

from . import views

app_name = "panel_admin"

# Los nombres coinciden con los de la barra del administrador (usuarios/contexto.py):
# cuando se crea cada pantalla, su botón aparece solo.
urlpatterns = [
    path("verificaciones", views.verificaciones, name="verificaciones"),
    path("verificaciones/<int:usuario_id>/imagen", views.imagen, name="imagen"),
    path("verificaciones/<int:usuario_id>/aprobar", views.aprobar, name="aprobar"),
    path("verificaciones/<int:usuario_id>/rechazar", views.rechazar, name="rechazar"),
    path("usuarios", views.usuarios, name="usuarios"),
    path("usuarios/<int:usuario_id>/bloquear", views.bloquear, name="bloquear"),
    path("usuarios/<int:usuario_id>/reactivar", views.reactivar, name="reactivar"),
    path("usuarios/<int:usuario_id>/editar", views.editar_usuario, name="editar_usuario"),
    path("historial/<int:usuario_id>", views.historial, name="historial"),
]