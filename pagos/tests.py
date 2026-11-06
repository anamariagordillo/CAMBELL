from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from solicitudes import servicios as servicios_solicitud
from solicitudes.models import CategoriaServicio
from usuarios.models import Rol, Usuario

from . import servicios
from .models import MetodoPago
from .servicios import ErrorPago

ANIO = timezone.localdate().year
MES = timezone.localdate().month


def crear_usuario(correo, rol):
    return Usuario.objects.create_user(correo, "Clave1234", nombre=correo.split("@")[0], rol=rol)


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class FuncionesAuxiliaresTests(TestCase):
    def test_enmascarar(self):
        self.assertEqual(servicios.enmascarar("4242 4242 4242 4242"), "•••• 4242")
        self.assertEqual(servicios.enmascarar("4242-4242-4242-1111"), "•••• 1111")
        self.assertEqual(servicios.enmascarar("1234"), "1234")
        self.assertEqual(servicios.enmascarar(None), "")

    def test_vigencia_de_la_tarjeta(self):
        self.assertTrue(servicios.es_tarjeta_vigente(MES, ANIO))          # este mismo mes sirve
        self.assertTrue(servicios.es_tarjeta_vigente(12, ANIO + 3))
        self.assertFalse(servicios.es_tarjeta_vigente(12, ANIO - 1))       # año pasado
        self.assertFalse(servicios.es_tarjeta_vigente(13, ANIO + 1))       # mes inexistente
        self.assertFalse(servicios.es_tarjeta_vigente(0, ANIO + 1))
        self.assertFalse(servicios.es_tarjeta_vigente(None, ANIO))
        self.assertFalse(servicios.es_tarjeta_vigente(5, None))
        if MES > 1:
            self.assertFalse(servicios.es_tarjeta_vigente(MES - 1, ANIO))  # mes anterior


class MetodosServicioTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.otro = crear_usuario("otro@example.com", Rol.CLIENTE)

    def tarjeta(self, **extra):
        datos = dict(
            tipo="TARJETA", titular="Ana Perez", numero="4242 4242 4242 4242",
            mes_vencimiento=12, anio_vencimiento=ANIO + 2,
        )
        datos.update(extra)
        return servicios.registrar_metodo(self.cliente, **datos)

    def test_registrar_tarjeta_guarda_solo_los_ultimos_4_digitos(self):
        m = self.tarjeta()
        self.assertEqual(m.numero_enmascarado, "•••• 4242")
        self.assertEqual(m.cliente, self.cliente)
        valores = [str(v) for v in MetodoPago.objects.filter(pk=m.pk).values()[0].values()]
        self.assertFalse(any("4242424242424242" in v or "4242 4242 4242" in v for v in valores))

    def test_tarjeta_vencida(self):
        with self.assertRaisesMessage(ErrorPago, "vencida"):
            self.tarjeta(anio_vencimiento=ANIO - 1)

    def test_tarjeta_sin_vencimiento(self):
        with self.assertRaisesMessage(ErrorPago, "vencida"):
            self.tarjeta(mes_vencimiento=None, anio_vencimiento=None)

    def test_nequi_no_necesita_vencimiento_y_lo_ignora(self):
        m = servicios.registrar_metodo(
            self.cliente, "NEQUI", "Ana", "3001234567", mes_vencimiento=5, anio_vencimiento=2000
        )
        self.assertEqual(m.numero_enmascarado, "•••• 4567")
        self.assertIsNone(m.mes_vencimiento)
        self.assertIsNone(m.anio_vencimiento)

    def test_validaciones_basicas(self):
        with self.assertRaisesMessage(ErrorPago, "tipo de método"):
            servicios.registrar_metodo(self.cliente, "BITCOIN", "Ana", "12345678")
        with self.assertRaisesMessage(ErrorPago, "titular es obligatorio"):
            servicios.registrar_metodo(self.cliente, "NEQUI", "   ", "3001234567")
        with self.assertRaisesMessage(ErrorPago, "mínimo 4 dígitos"):
            servicios.registrar_metodo(self.cliente, "NEQUI", "Ana", "12")

    def test_editar_cambia_titular_y_vencimiento(self):
        m = self.tarjeta()
        servicios.editar_metodo(m.id, self.cliente, "Ana M. Perez", 11, ANIO + 4)
        m.refresh_from_db()
        self.assertEqual(m.titular, "Ana M. Perez")
        self.assertEqual((m.mes_vencimiento, m.anio_vencimiento), (11, ANIO + 4))

    def test_editar_no_acepta_una_fecha_vencida(self):
        m = self.tarjeta()
        with self.assertRaisesMessage(ErrorPago, "vencida"):
            servicios.editar_metodo(m.id, self.cliente, "Ana", 1, ANIO - 1)

    def test_otro_cliente_no_puede_editar_ni_eliminar(self):
        m = self.tarjeta()
        with self.assertRaisesMessage(ErrorPago, "no te pertenece"):
            servicios.editar_metodo(m.id, self.otro, "Intruso", 12, ANIO + 1)
        with self.assertRaisesMessage(ErrorPago, "no te pertenece"):
            servicios.eliminar_metodo(m.id, self.otro)
        self.assertTrue(MetodoPago.objects.filter(pk=m.pk).exists())

    def test_eliminar_no_borra_las_solicitudes_que_lo_usaban(self):
        m = self.tarjeta()
        s = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Con tarjeta", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly", metodo_pago=m,
        )
        servicios.eliminar_metodo(m.id, self.cliente)
        s.refresh_from_db()
        self.assertIsNone(s.metodo_pago)

    def test_buscar_metodo_del_cliente(self):
        m = self.tarjeta()
        self.assertEqual(servicios.buscar_metodo_del_cliente(m.id, self.cliente), m)
        self.assertIsNone(servicios.buscar_metodo_del_cliente(m.id, self.otro))
        self.assertIsNone(servicios.buscar_metodo_del_cliente(None, self.cliente))


class MetodosVistaTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.otro = crear_usuario("otro@example.com", Rol.CLIENTE)
        self.client.force_login(self.cliente)

    def datos_tarjeta(self, **extra):
        datos = {
            "tipo": "TARJETA", "titular": "Ana Perez", "numero": "4242 4242 4242 4242",
            "mes_vencimiento": "12", "anio_vencimiento": str(ANIO + 2),
        }
        datos.update(extra)
        return datos

    def test_lista_solo_mis_metodos(self):
        servicios.registrar_metodo(self.cliente, "NEQUI", "Titular Mio", "3001112233")
        servicios.registrar_metodo(self.otro, "NEQUI", "Titular Ajeno", "3009998877")
        r = self.client.get(reverse("pagos:metodos"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Titular Mio")
        self.assertNotContains(r, "Titular Ajeno")

    def test_registrar_por_el_formulario(self):
        r = self.client.post(reverse("pagos:metodos"), self.datos_tarjeta())
        self.assertRedirects(r, reverse("pagos:metodos"))
        self.assertIn("Método de pago registrado.", mensajes(r))
        m = MetodoPago.objects.get()
        self.assertEqual(m.cliente, self.cliente)
        self.assertEqual(m.numero_enmascarado, "•••• 4242")

    def test_el_numero_completo_no_se_vuelve_a_mostrar(self):
        self.client.post(reverse("pagos:metodos"), self.datos_tarjeta())
        r = self.client.get(reverse("pagos:metodos"))
        self.assertContains(r, "•••• 4242")
        self.assertNotContains(r, "4242 4242 4242 4242")

    def test_tarjeta_vencida_muestra_el_error(self):
        r = self.client.post(reverse("pagos:metodos"), self.datos_tarjeta(anio_vencimiento=str(ANIO - 1)))
        self.assertTrue(any("vencida" in m for m in mensajes(r)))
        self.assertEqual(MetodoPago.objects.count(), 0)

    def test_vencimiento_con_texto_no_rompe(self):
        r = self.client.post(reverse("pagos:metodos"), self.datos_tarjeta(mes_vencimiento="abc"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(MetodoPago.objects.count(), 0)

    def test_editar_por_el_formulario(self):
        m = servicios.registrar_metodo(self.cliente, "TARJETA", "Ana", "4242424242424242", 12, ANIO + 2)
        r = self.client.post(reverse("pagos:editar_metodo", args=[m.id]), {
            "titular": "Ana Nueva", "mes_vencimiento": "10", "anio_vencimiento": str(ANIO + 3),
        })
        self.assertIn("Método de pago actualizado.", mensajes(r))
        m.refresh_from_db()
        self.assertEqual(m.titular, "Ana Nueva")

    def test_eliminar_por_el_formulario(self):
        m = servicios.registrar_metodo(self.cliente, "NEQUI", "Ana", "3001234567")
        r = self.client.post(reverse("pagos:eliminar_metodo", args=[m.id]))
        self.assertIn("Método de pago eliminado.", mensajes(r))
        self.assertFalse(MetodoPago.objects.filter(pk=m.pk).exists())

    def test_no_se_puede_eliminar_el_de_otro_cliente(self):
        ajeno = servicios.registrar_metodo(self.otro, "NEQUI", "Otro", "3001234567")
        r = self.client.post(reverse("pagos:eliminar_metodo", args=[ajeno.id]))
        self.assertTrue(any("no te pertenece" in m for m in mensajes(r)))
        self.assertTrue(MetodoPago.objects.filter(pk=ajeno.pk).exists())

    def test_editar_y_eliminar_exigen_post(self):
        m = servicios.registrar_metodo(self.cliente, "NEQUI", "Ana", "3001234567")
        self.assertEqual(self.client.get(reverse("pagos:editar_metodo", args=[m.id])).status_code, 405)
        self.assertEqual(self.client.get(reverse("pagos:eliminar_metodo", args=[m.id])).status_code, 405)

    def test_un_trabajador_no_entra(self):
        trabajador = crear_usuario("trab@example.com", Rol.TRABAJADOR)
        self.client.force_login(trabajador)
        self.assertEqual(self.client.get(reverse("pagos:metodos")).status_code, 403)

    def test_sin_sesion_va_al_login(self):
        self.client.logout()
        r = self.client.get(reverse("pagos:metodos"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])

    def test_el_enlace_aparece_en_la_barra_del_cliente(self):
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertContains(r, reverse("pagos:metodos"))

    def test_nueva_solicitud_ofrece_los_metodos_del_cliente(self):
        m = servicios.registrar_metodo(self.cliente, "NEQUI", "Ana", "3001234567")
        r = self.client.get(reverse("solicitudes:nueva"))
        self.assertContains(r, f'value="{m.id}"')
        self.assertContains(r, "•••• 4567")