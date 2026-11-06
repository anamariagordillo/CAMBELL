from django.urls import path

from . import views

app_name = "pagos"

urlpatterns = [
    path("metodos", views.metodos, name="metodos"),
    path("metodos/<int:metodo_id>/editar", views.editar_metodo, name="editar_metodo"),
    path("metodos/<int:metodo_id>/eliminar", views.eliminar_metodo, name="eliminar_metodo"),
]