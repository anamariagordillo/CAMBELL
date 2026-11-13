from django.urls import path

from . import views, views_cobro, views_ingresos, views_suscripcion

app_name = "pagos"

urlpatterns = [
    # Métodos de pago (cliente)
    path("metodos", views.metodos, name="metodos"),
    path("metodos/<int:metodo_id>/editar", views.editar_metodo, name="editar_metodo"),
    path("metodos/<int:metodo_id>/eliminar", views.eliminar_metodo, name="eliminar_metodo"),
    # Pagar un servicio, comprobante e historial (cliente)
    path("solicitud/<int:solicitud_id>", views_cobro.pagar, name="pagar"),
    path("solicitud/<int:solicitud_id>/realizar", views_cobro.realizar_pago, name="realizar_pago"),
    path("historial", views_cobro.historial, name="historial"),
    path("comprobante/<int:pago_id>", views_cobro.comprobante, name="comprobante"),
    # Ingresos y reporte (trabajador)
    path("ingresos", views_ingresos.mis_ingresos, name="ingresos"),
    path("ingresos/exportar", views_ingresos.exportar_ingresos, name="exportar_ingresos"),
    # Suscripción premium simulada
    path("suscripcion", views_suscripcion.mi_suscripcion, name="suscripcion"),
    path("suscripcion/contratar", views_suscripcion.contratar, name="contratar_suscripcion"),
    path("suscripcion/cancelar", views_suscripcion.cancelar, name="cancelar_suscripcion"),
]