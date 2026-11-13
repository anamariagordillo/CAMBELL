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
    # Moderación de anuncios
    path("anuncios", views.anuncios, name="anuncios"),
    path("anuncios/<int:anuncio_id>/aprobar", views.aprobar_anuncio, name="aprobar_anuncio"),
    path("anuncios/<int:anuncio_id>/rechazar", views.rechazar_anuncio, name="rechazar_anuncio"),
    # Reembolsos
    path("reembolsos", views.reembolsos, name="reembolsos"),
    path("reembolsos/<int:pago_id>/iniciar", views.iniciar_reembolso, name="iniciar_reembolso"),
    # Reportes de seguridad
    path("reportes", views.reportes, name="reportes"),
    path("reportes/<int:reporte_id>/bloquear", views.bloquear_reportado, name="bloquear_reportado"),
    path("reportes/<int:reporte_id>/descartar", views.descartar_reporte, name="descartar_reporte"),
    # Reporte multicriterio global
    path("estadisticas", views.estadisticas, name="estadisticas"),
    path(
        "estadisticas/exportar/<str:formato>",
        views.exportar_estadisticas,
        name="exportar_estadisticas",
    ),
]
