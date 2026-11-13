from django.urls import path

from . import views

app_name = "anuncios"

# Las mismas rutas de la versión Java: /anuncios/mios, /nuevo, /{id}/editar y /{id}/eliminar.
urlpatterns = [
    path("mios", views.mios, name="mios"),
    path("mios/nuevo", views.nuevo, name="nuevo"),
    path("mios/<int:anuncio_id>/editar", views.editar, name="editar"),
    path("mios/<int:anuncio_id>/eliminar", views.eliminar, name="eliminar"),
]
