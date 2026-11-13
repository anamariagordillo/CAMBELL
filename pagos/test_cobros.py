from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from mensajeria.models import Notificacion
from solicitudes import servicios as servicios_solicitud
from solicitudes.models import CategoriaServicio
from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import cobros, servicios
from .models import MetodoPago, Pago
from .servicios import ErrorPago

ANIO = timezone.localdate().year


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class CobroBase(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.otro = crear_usuario("otro@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.metodo = servicios.registrar_metodo(
            self.cliente, "TARJETA", "Ana Perez", "4242 4242 4242 4242", 12, ANIO + 2
        )

    def solicitud(self, precio=Decimal("100000"), completar=True, **extra):
        s = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Instalar lavamanos", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly", precio_ofertado=precio, **extra,
        )
        servicios_solicitud.aceptar(s.id, self.trabajador)
        if completar:
            servicios_solicitud.finalizar_con_evidencia(s.id, "evidencias/foto.png")
        s.refresh_from_db()
        return s


class CalculoComisionTests(TestCase):
    def test_comision_del_3_por_ciento(self):
        comision, neto = cobros.calcular_comision(Decimal("100000"))
        self.assertEqual(comision, Decimal("3000.00"))
        self.assertEqual(neto, Decimal("97000.00"))

    def test_con_centavos_y_redondeo_hacia_arriba(self):
        casos = [
            (Decimal("27070"), Decimal("812.10"), Decimal("26257.90")),
            (Decimal("10001"), Decimal("300.03"), Decimal("9700.97")),
            (Decimal("12345.50"), Decimal("370.37"), Decimal("11975.13")),  # 370,365 sube a 370,37
        ]
        for monto, comision_esperada, neto_esperado in casos:
            comision, neto = cobros.calcular_comision(monto)
            self.assertEqual(comision, comision_esperada)
            self.assertEqual(neto, neto_esperado)
            self.assertEqual(comision + neto, monto)

    def test_porcentaje_para_mostrar(self):
        self.assertEqual(cobros.porcentaje_comision(), "3")


class PagarServicioTests(CobroBase):
    def test_pagar_deja_el_pago_completado(self):
        s = self.solicitud()
        pago = cobros.pagar(s.id, self.metodo.id, self.cliente)
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(pago.monto_total, Decimal("100000.00"))
        self.assertEqual(pago.comision, Decimal("3000.00"))
        self.assertEqual(pago.neto_trabajador, Decimal("97000.00"))
        self.assertEqual(pago.metodo_pago, self.metodo)
        self.assertEqual(pago.cliente, self.cliente)
        self.assertEqual(pago.trabajador, self.trabajador)
        self.assertIsNotNone(pago.fecha_pago)
        self.assertEqual(pago.estado_transferencia, Pago.EstadoTransferencia.PENDIENTE)

    def test_avisa_al_trabajador(self):
        s = self.solicitud()
        cobros.pagar(s.id, self.metodo.id, self.cliente)
        aviso = Notificacion.objects.get(usuario=self.trabajador, tipo="PAGO")
        self.assertIn("97000.00", aviso.mensaje)

    def test_no_se_paga_un_servicio_sin_completar(self):
        s = self.solicitud(completar=False)
        with self.assertRaisesMessage(ErrorPago, "debe estar completado"):
            cobros.pagar(s.id, self.metodo.id, self.cliente)
        self.assertEqual(Pago.objects.count(), 0)

    def test_no_se_paga_dos_veces(self):
        s = self.solicitud()
        cobros.pagar(s.id, self.metodo.id, self.cliente)
        with self.assertRaisesMessage(ErrorPago, "ya fue pagada"):
            cobros.pagar(s.id, self.metodo.id, self.cliente)
        self.assertEqual(Pago.objects.count(), 1)

    def test_solo_paga_el_cliente_de_la_solicitud(self):
        s = self.solicitud()
        with self.assertRaisesMessage(ErrorPago, "Solo el cliente"):
            cobros.pagar(s.id, self.metodo.id, self.otro)

    def test_exige_un_metodo_de_pago(self):
        s = self.solicitud()
        with self.assertRaisesMessage(ErrorPago, "método de pago válido"):
            cobros.pagar(s.id, None, self.cliente)

    def test_no_se_puede_pagar_con_el_metodo_de_otro_cliente(self):
        ajeno = servicios.registrar_metodo(self.otro, "NEQUI", "Otro", "3001234567")
        s = self.solicitud()
        with self.assertRaisesMessage(ErrorPago, "método de pago válido"):
            cobros.pagar(s.id, ajeno.id, self.cliente)
        self.assertEqual(Pago.objects.count(), 0)

    def test_tarjeta_vencida(self):
        MetodoPago.objects.filter(pk=self.metodo.pk).update(anio_vencimiento=ANIO - 1)
        s = self.solicitud()
        with self.assertRaisesMessage(ErrorPago, "está vencida"):
            cobros.pagar(s.id, self.metodo.id, self.cliente)

    def test_solicitud_sin_precio(self):
        s = self.solicitud(precio=None)
        with self.assertRaisesMessage(ErrorPago, "no tiene un precio"):
            cobros.pagar(s.id, self.metodo.id, self.cliente)

    def test_solicitud_inexistente(self):
        with self.assertRaisesMessage(ErrorPago, "no encontrada"):
            cobros.pagar(9999, self.metodo.id, self.cliente)

    def test_un_pago_fallido_se_puede_reintentar(self):
        s = self.solicitud()
        fallido = Pago.objects.create(
            solicitud=s, cliente=self.cliente, trabajador=self.trabajador,
            monto_total=0, comision=0, neto_trabajador=0, estado=Pago.Estado.FALLIDO,
        )
        pago = cobros.pagar(s.id, self.metodo.id, self.cliente)
        self.assertEqual(pago.pk, fallido.pk)
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(Pago.objects.count(), 1)


class PantallasDePagoTests(CobroBase):
    def setUp(self):
        super().setUp()
        self.s = self.solicitud(metodo_pago=self.metodo)
        self.client.force_login(self.cliente)

    def test_ver_la_pantalla_de_pago(self):
        r = self.client.get(reverse("pagos:pagar", args=[self.s.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Instalar lavamanos")
        self.assertContains(r, "se calcula al pagar")
        self.assertContains(r, "indicado al publicar la solicitud")  # método preseleccionado

    def test_pagar_por_el_formulario(self):
        r = self.client.post(reverse("pagos:realizar_pago", args=[self.s.id]), {"metodo_id": self.metodo.id})
        self.assertRedirects(r, reverse("pagos:pagar", args=[self.s.id]))
        self.assertIn("Pago realizado con éxito. El trabajador recibirá el neto.", mensajes(r))
        pago = Pago.objects.get()
        pantalla = self.client.get(reverse("pagos:pagar", args=[self.s.id]))
        self.assertContains(pantalla, "Pago recibido")
        self.assertContains(pantalla, reverse("pagos:comprobante", args=[pago.id]))
        self.assertNotContains(pantalla, "Pagar $")  # ya no se ofrece el formulario

    def test_pagar_sin_elegir_metodo_muestra_el_error(self):
        r = self.client.post(reverse("pagos:realizar_pago", args=[self.s.id]), {"metodo_id": ""})
        self.assertIn("Selecciona un método de pago válido.", mensajes(r))
        self.assertEqual(Pago.objects.count(), 0)

    def test_pagar_exige_post(self):
        r = self.client.get(reverse("pagos:realizar_pago", args=[self.s.id]))
        self.assertEqual(r.status_code, 405)

    def test_servicio_sin_completar_no_ofrece_el_formulario(self):
        pendiente = self.solicitud(completar=False)
        r = self.client.get(reverse("pagos:pagar", args=[pendiente.id]))
        self.assertContains(r, "todavía no está completado")
        self.assertNotContains(r, "realizar")

    def test_otro_cliente_no_ve_la_pantalla_de_pago(self):
        self.client.force_login(self.otro)
        r = self.client.get(reverse("pagos:pagar", args=[self.s.id]))
        self.assertEqual(r.status_code, 404)

    def test_un_trabajador_no_entra_a_pagar(self):
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("pagos:pagar", args=[self.s.id]))
        self.assertEqual(r.status_code, 403)

    def test_mis_solicitudes_ofrece_pagar_y_luego_muestra_pagado(self):
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertContains(r, "Pagar servicio")
        self.assertContains(r, reverse("pagos:pagar", args=[self.s.id]))

        cobros.pagar(self.s.id, self.metodo.id, self.cliente)
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertContains(r, "Servicio pagado")
        self.assertNotContains(r, "Pagar servicio")

    def test_el_trabajador_ve_pago_recibido(self):
        cobros.pagar(self.s.id, self.metodo.id, self.cliente)
        pago = Pago.objects.get()
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("solicitudes:finalizado", args=[self.s.id]))
        self.assertContains(r, "Pago recibido")
        self.assertContains(r, reverse("pagos:comprobante", args=[pago.id]))

    def test_historial_lista_solo_mis_pagos(self):
        cobros.pagar(self.s.id, self.metodo.id, self.cliente)
        r = self.client.get(reverse("pagos:historial"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Instalar lavamanos")
        self.assertContains(r, "Comprobante")

        self.client.force_login(self.otro)
        r = self.client.get(reverse("pagos:historial"))
        self.assertNotContains(r, "Instalar lavamanos")
        self.assertContains(r, "Aún no tienes pagos registrados.")

    def test_comprobante_lo_ven_el_cliente_y_el_trabajador(self):
        cobros.pagar(self.s.id, self.metodo.id, self.cliente)
        pago = Pago.objects.get()
        url = reverse("pagos:comprobante", args=[pago.id])

        for usuario in (self.cliente, self.trabajador):
            self.client.force_login(usuario)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "Comprobante de pago")
            self.assertContains(r, "Instalar lavamanos")
            self.assertContains(r, "Comisión (3%)")
            self.assertContains(r, "•••• 4242")

    def test_comprobante_no_lo_ve_un_tercero(self):
        cobros.pagar(self.s.id, self.metodo.id, self.cliente)
        pago = Pago.objects.get()
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(reverse("pagos:comprobante", args=[pago.id])).status_code, 404)
        otro_trabajador = crear_usuario(
            "otrotrab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.client.force_login(otro_trabajador)
        self.assertEqual(self.client.get(reverse("pagos:comprobante", args=[pago.id])).status_code, 404)

    def test_la_barra_del_cliente_muestra_el_historial_de_pagos(self):
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertContains(r, reverse("pagos:historial"))