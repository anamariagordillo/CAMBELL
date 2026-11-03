from django.test import TestCase
from django.urls import reverse

from mensajeria.models import Notificacion
from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import servicios
from .models import CategoriaServicio, EstadoSolicitud, Solicitud
from .servicios import ErrorSolicitud


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


class SolicitudesServicioTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.otro = crear_usuario(
            "otro@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )

    def nueva(self):
        return servicios.crear_solicitud(
            self.cliente,
            descripcion="Arreglar fuga del lavaplatos",
            categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero",
            barrio="Marly",
            precio_ofertado=50000,
        )

    def test_crear_deja_pendiente_con_codigo_y_zona(self):
        s = self.nueva()
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertEqual(len(s.codigo_finalizacion), 6)
        self.assertEqual(s.zona, "Marly, Chapinero, Bogotá")

    def test_aceptar_asigna_trabajador_y_avisa_al_cliente(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.ACEPTADA)
        self.assertEqual(s.trabajador, self.trabajador)
        self.assertTrue(
            Notificacion.objects.filter(usuario=self.cliente, tipo="ESTADO", solicitud=s).exists()
        )

    def test_solo_uno_puede_aceptar(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        with self.assertRaisesMessage(ErrorSolicitud, "ya no está disponible"):
            servicios.aceptar(s.id, self.otro)

    def test_trabajador_sin_verificar_no_acepta(self):
        pendiente = crear_usuario("nuevo@example.com", Rol.TRABAJADOR)
        s = self.nueva()
        with self.assertRaisesMessage(ErrorSolicitud, "verificación APROBADA"):
            servicios.aceptar(s.id, pendiente)

    def test_un_cliente_no_puede_aceptar(self):
        s = self.nueva()
        with self.assertRaisesMessage(ErrorSolicitud, "Solo un trabajador"):
            servicios.aceptar(s.id, self.cliente)

    def test_cancelar_solo_si_esta_pendiente(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        with self.assertRaisesMessage(ErrorSolicitud, "aún no han sido aceptadas"):
            servicios.cancelar(s.id, self.cliente)

    def test_liberar_devuelve_la_solicitud_a_disponibles(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        servicios.liberar(s.id, self.trabajador)
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertIsNone(s.trabajador)

    def test_codigo_de_finalizacion(self):
        s = self.nueva()
        self.assertTrue(servicios.validar_codigo(s.id, s.codigo_finalizacion.lower()))
        self.assertFalse(servicios.validar_codigo(s.id, "ZZZZZZ"))

    def test_recorrido_completo_y_promedio_del_trabajador(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        servicios.finalizar_con_evidencia(s.id, "evidencias/foto.png")
        servicios.calificar(s.id, 4, "Buen trabajo", self.cliente)

        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.calificacion_promedio, 4.0)
        self.assertEqual(self.trabajador.total_calificaciones, 1)

        with self.assertRaisesMessage(ErrorSolicitud, "ya fue calificado"):
            servicios.calificar(s.id, 5, "", self.cliente)

    def test_calificacion_fuera_de_rango(self):
        s = self.nueva()
        servicios.aceptar(s.id, self.trabajador)
        servicios.finalizar_con_evidencia(s.id, "evidencias/foto.png")
        with self.assertRaisesMessage(ErrorSolicitud, "entre 1 y 5"):
            servicios.calificar(s.id, 6, "", self.cliente)


class NuevaSolicitudVistaTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)

    def datos(self, **extra):
        datos = {
            "descripcion": "Arreglar fuga del lavaplatos",
            "categoria": "PLOMERIA",
            "localidad": "Chapinero",
            "barrio": "Marly",
            "latitud": "4.6280",
            "longitud": "-74.0650",
            "direccion_especifica": "Cra 15 # 45-32",
            "precio_ofertado": "50000",
        }
        datos.update(extra)
        return datos

    def test_cliente_ve_el_formulario_con_mapa(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("solicitudes:nueva"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "mapaSolicitud")

    def test_crea_la_solicitud(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("solicitudes:nueva"), self.datos())
        self.assertRedirects(r, reverse("solicitudes:mis_solicitudes"))
        s = Solicitud.objects.get()
        self.assertEqual(s.cliente, self.cliente)
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertEqual(s.zona, "Marly, Chapinero, Bogotá")
        self.assertEqual(len(s.codigo_finalizacion), 6)

    def test_exige_el_punto_del_mapa(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("solicitudes:nueva"), self.datos(latitud="", longitud=""))
        self.assertEqual(r.status_code, 200)
        self.assertIn("latitud", r.context["form"].errors)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_precio_minimo(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("solicitudes:nueva"), self.datos(precio_ofertado="1000"))
        self.assertIn("precio_ofertado", r.context["form"].errors)

    def test_barrio_de_otra_localidad(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("solicitudes:nueva"), self.datos(barrio="Barrio Inventado"))
        self.assertIn("barrio", r.context["form"].errors)

    def test_un_trabajador_no_puede_crear_solicitudes(self):
        trabajador = crear_usuario("trab2@example.com", Rol.TRABAJADOR)
        self.client.force_login(trabajador)
        r = self.client.get(reverse("solicitudes:nueva"))
        self.assertEqual(r.status_code, 403)

    def test_sin_sesion_va_al_login(self):
        r = self.client.get(reverse("solicitudes:nueva"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])


class MisSolicitudesVistaTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.otro_cliente = crear_usuario("otro@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.client.force_login(self.cliente)

    def crear(self, cliente, descripcion):
        return servicios.crear_solicitud(
            cliente, descripcion=descripcion, categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly",
        )

    def test_lista_solo_las_propias_de_la_mas_nueva_a_la_mas_vieja(self):
        vieja = self.crear(self.cliente, "Solicitud vieja")
        nueva = self.crear(self.cliente, "Solicitud nueva")
        self.crear(self.otro_cliente, "Ajena")

        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertEqual(list(r.context["solicitudes"]), [nueva, vieja])
        self.assertNotContains(r, "Ajena")

    def test_filtro_por_estado(self):
        pendiente = self.crear(self.cliente, "Pendiente")
        aceptada = self.crear(self.cliente, "Aceptada")
        servicios.aceptar(aceptada.id, self.trabajador)

        r = self.client.get(reverse("solicitudes:mis_solicitudes"), {"estado": "PENDIENTE"})
        self.assertEqual(list(r.context["solicitudes"]), [pendiente])

    def test_estado_invalido_no_filtra(self):
        self.crear(self.cliente, "Una")
        r = self.client.get(reverse("solicitudes:mis_solicitudes"), {"estado": "NOEXISTE"})
        self.assertEqual(len(r.context["solicitudes"]), 1)

    def test_el_codigo_solo_se_muestra_cuando_esta_aceptada(self):
        s = self.crear(self.cliente, "Con codigo")
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertNotContains(r, "Código para el trabajador")

        servicios.aceptar(s.id, self.trabajador)
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        s.refresh_from_db()
        self.assertContains(r, "Código para el trabajador")
        self.assertContains(r, s.codigo_finalizacion)

    def test_cancelar_una_pendiente(self):
        s = self.crear(self.cliente, "Para cancelar")
        r = self.client.post(reverse("solicitudes:cancelar", args=[s.id]))
        self.assertRedirects(r, reverse("solicitudes:mis_solicitudes"))
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.CANCELADA)

    def test_no_se_puede_cancelar_la_de_otro_cliente(self):
        s = self.crear(self.otro_cliente, "Ajena")
        r = self.client.post(reverse("solicitudes:cancelar", args=[s.id]), follow=True)
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertContains(r, "Solo el cliente que creó la solicitud")

    def test_no_se_puede_cancelar_una_aceptada(self):
        s = self.crear(self.cliente, "Aceptada")
        servicios.aceptar(s.id, self.trabajador)
        r = self.client.post(reverse("solicitudes:cancelar", args=[s.id]), follow=True)
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.ACEPTADA)
        self.assertContains(r, "aún no han sido aceptadas")

    def test_cancelar_exige_post(self):
        s = self.crear(self.cliente, "Una")
        r = self.client.get(reverse("solicitudes:cancelar", args=[s.id]))
        self.assertEqual(r.status_code, 405)

    def test_historial_excluye_las_pendientes(self):
        self.crear(self.cliente, "Sigue pendiente")
        aceptada = self.crear(self.cliente, "Ya aceptada")
        servicios.aceptar(aceptada.id, self.trabajador)

        r = self.client.get(reverse("solicitudes:historial_cliente"))
        self.assertEqual(list(r.context["solicitudes"]), [aceptada])

    def test_un_trabajador_no_ve_estas_pantallas(self):
        self.client.force_login(self.trabajador)
        self.assertEqual(self.client.get(reverse("solicitudes:mis_solicitudes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("solicitudes:historial_cliente")).status_code, 403)