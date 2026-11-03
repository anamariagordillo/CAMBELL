from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import servicios
from .models import CategoriaServicio, EstadoSolicitud, Solicitud


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


class TrabajadorVistasTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.otro = crear_usuario(
            "otro@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.client.force_login(self.trabajador)

    def crear(self, descripcion="Solicitud de prueba", **extra):
        datos = {
            "descripcion": descripcion,
            "categoria": CategoriaServicio.PLOMERIA,
            "localidad": "Chapinero",
            "barrio": "Marly",
            "precio_ofertado": 50000,
        }
        datos.update(extra)
        return servicios.crear_solicitud(self.cliente, **datos)

    def ids(self, respuesta, clave="solicitudes"):
        return [s.id for s in respuesta.context[clave]]

    # ---------- Disponibles ----------
    def test_disponibles_lista_pendientes_y_no_muestra_la_direccion(self):
        s = self.crear("Fuga en la cocina", direccion_especifica="Calle Secreta 123")
        r = self.client.get(reverse("solicitudes:disponibles"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Fuga en la cocina")
        self.assertContains(r, "Cliente: ")
        self.assertNotContains(r, "Calle Secreta 123")
        self.assertEqual(self.ids(r), [s.id])

    def test_no_lista_las_que_ya_fueron_aceptadas(self):
        s = self.crear()
        servicios.aceptar(s.id, self.otro)
        r = self.client.get(reverse("solicitudes:disponibles"))
        self.assertEqual(self.ids(r), [])

    def test_filtros_por_categoria_y_localidad(self):
        plomeria = self.crear("Plomeria")
        electricidad = self.crear(
            "Electricidad", categoria=CategoriaServicio.ELECTRICIDAD, localidad="Suba", barrio="Niza"
        )
        url = reverse("solicitudes:disponibles")
        self.assertEqual(self.ids(self.client.get(url, {"categoria": "ELECTRICIDAD"})), [electricidad.id])
        self.assertEqual(self.ids(self.client.get(url, {"localidad": "Suba"})), [electricidad.id])
        self.assertEqual(self.ids(self.client.get(url, {"localidad": "Chapinero", "barrio": "Marly"})), [plomeria.id])

    def test_filtro_de_precio_incluye_las_que_no_tienen_precio(self):
        cara = self.crear("Cara", precio_ofertado=50000)
        barata = self.crear("Barata", precio_ofertado=20000)
        sin_precio = self.crear("Sin precio", precio_ofertado=None)
        url = reverse("solicitudes:disponibles")

        con_minimo = self.ids(self.client.get(url, {"precio_min": "40000"}))
        self.assertIn(cara.id, con_minimo)
        self.assertIn(sin_precio.id, con_minimo)
        self.assertNotIn(barata.id, con_minimo)

        con_maximo = self.ids(self.client.get(url, {"precio_max": "30000"}))
        self.assertIn(barata.id, con_maximo)
        self.assertIn(sin_precio.id, con_maximo)
        self.assertNotIn(cara.id, con_maximo)

    def test_orden_recientes_y_antiguas(self):
        a = self.crear("Primera")
        b = self.crear("Segunda")
        ahora = timezone.now()
        Solicitud.objects.filter(pk=a.pk).update(fecha_creacion=ahora - timedelta(hours=2))
        Solicitud.objects.filter(pk=b.pk).update(fecha_creacion=ahora - timedelta(hours=1))
        url = reverse("solicitudes:disponibles")
        self.assertEqual(self.ids(self.client.get(url)), [b.id, a.id])
        self.assertEqual(self.ids(self.client.get(url, {"orden": "antiguas"})), [a.id, b.id])

    def test_filtros_invalidos_se_ignoran(self):
        self.crear()
        r = self.client.get(
            reverse("solicitudes:disponibles"), {"precio_min": "abc", "categoria": "NOEXISTE"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.ids(r)), 1)

    def test_un_cliente_no_entra_a_las_pantallas_del_trabajador(self):
        self.client.force_login(self.cliente)
        for nombre in ("disponibles", "mis_trabajos", "historial_trabajos"):
            self.assertEqual(self.client.get(reverse(f"solicitudes:{nombre}")).status_code, 403)

    def test_sin_sesion_va_al_login(self):
        self.client.logout()
        r = self.client.get(reverse("solicitudes:disponibles"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])

    def test_trabajador_sin_verificar_ve_la_pagina_de_revision(self):
        pendiente = crear_usuario("pend@example.com", Rol.TRABAJADOR)
        self.crear("No deberia verla")
        self.client.force_login(pendiente)
        r = self.client.get(reverse("solicitudes:disponibles"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Tu cuenta está en revisión")
        self.assertNotContains(r, "No deberia verla")

    # ---------- Aceptar y rechazar ----------
    def test_aceptar_asigna_la_solicitud_y_aparece_en_mis_trabajos(self):
        s = self.crear("Para aceptar")
        r = self.client.post(reverse("solicitudes:aceptar", args=[s.id]), follow=True)
        self.assertRedirects(r, reverse("solicitudes:disponibles"))
        self.assertContains(r, "Aceptaste la solicitud")
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.ACEPTADA)
        self.assertEqual(s.trabajador, self.trabajador)

        trabajos = self.client.get(reverse("solicitudes:mis_trabajos"))
        self.assertEqual(self.ids(trabajos, "trabajos"), [s.id])

    def test_aceptar_una_que_otro_ya_tomo(self):
        s = self.crear()
        servicios.aceptar(s.id, self.otro)
        r = self.client.post(reverse("solicitudes:aceptar", args=[s.id]), follow=True)
        self.assertContains(r, "ya no está disponible")
        s.refresh_from_db()
        self.assertEqual(s.trabajador, self.otro)

    def test_aceptar_exige_post(self):
        s = self.crear()
        self.assertEqual(self.client.get(reverse("solicitudes:aceptar", args=[s.id])).status_code, 405)

    def test_rechazar_exige_motivo(self):
        s = self.crear()
        r = self.client.post(reverse("solicitudes:rechazar", args=[s.id]), {"motivo": "   "})
        mensajes = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertIn("Debes indicar el motivo del rechazo.", mensajes)
        self.assertRedirects(r, reverse("solicitudes:disponibles"))
        s.refresh_from_db()
        self.assertEqual(s.motivo_rechazo, "")

    def test_rechazar_con_motivo_deja_la_solicitud_disponible(self):
        s = self.crear()
        r = self.client.post(
            reverse("solicitudes:rechazar", args=[s.id]), {"motivo": "Muy lejos de mi zona"}, follow=True
        )
        self.assertContains(r, "Rechazaste la solicitud")
        s.refresh_from_db()
        self.assertEqual(s.motivo_rechazo, "Muy lejos de mi zona")
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertIsNone(s.trabajador)

    # ---------- Mis trabajos ----------
    def test_mis_trabajos_filtros(self):
        en_curso = self.crear("En curso")
        servicios.aceptar(en_curso.id, self.trabajador)
        completada = self.crear("Completada")
        servicios.aceptar(completada.id, self.trabajador)
        servicios.finalizar_con_evidencia(completada.id, "evidencias/foto.png")

        url = reverse("solicitudes:mis_trabajos")
        self.assertEqual(self.ids(self.client.get(url), "trabajos"), [en_curso.id])
        self.assertEqual(self.ids(self.client.get(url, {"estado": "completadas"}), "trabajos"), [completada.id])
        self.assertEqual(
            self.ids(self.client.get(url, {"estado": "todas"}), "trabajos"), [completada.id, en_curso.id]
        )
        self.assertEqual(self.ids(self.client.get(url, {"estado": "cualquiera"}), "trabajos"), [en_curso.id])

    def test_el_punto_exacto_solo_se_envia_para_trabajos_en_curso(self):
        en_curso = self.crear("En curso", latitud=4.6280, longitud=-74.0650)
        servicios.aceptar(en_curso.id, self.trabajador)
        completada = self.crear("Completada", latitud=4.7, longitud=-74.1)
        servicios.aceptar(completada.id, self.trabajador)
        servicios.finalizar_con_evidencia(completada.id, "evidencias/foto.png")

        r = self.client.get(reverse("solicitudes:mis_trabajos"), {"estado": "todas"})
        puntos = r.context["puntos_exactos"]
        self.assertIn(str(en_curso.id), puntos)
        self.assertNotIn(str(completada.id), puntos)
        self.assertContains(r, 'id="puntos-exactos"')

    def test_liberar_devuelve_el_trabajo_a_disponibles(self):
        s = self.crear()
        servicios.aceptar(s.id, self.trabajador)
        r = self.client.post(reverse("solicitudes:liberar", args=[s.id]), follow=True)
        self.assertRedirects(r, reverse("solicitudes:mis_trabajos"))
        self.assertContains(r, "Liberaste el trabajo")
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.PENDIENTE)
        self.assertIsNone(s.trabajador)

    def test_otro_trabajador_no_puede_liberar_un_trabajo_ajeno(self):
        s = self.crear()
        servicios.aceptar(s.id, self.otro)
        r = self.client.post(reverse("solicitudes:liberar", args=[s.id]), follow=True)
        self.assertContains(r, "Solo el trabajador asignado")
        s.refresh_from_db()
        self.assertEqual(s.estado, EstadoSolicitud.ACEPTADA)

    def test_historial_del_trabajador(self):
        aceptada = self.crear("Aceptada")
        servicios.aceptar(aceptada.id, self.trabajador)
        self.crear("Sigue pendiente")
        r = self.client.get(reverse("solicitudes:historial_trabajos"))
        self.assertEqual(self.ids(r, "historial"), [aceptada.id])