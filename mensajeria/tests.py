"""Pruebas de la Fase 1C: chat por solicitud y bandeja de notificaciones."""
from django.test import TestCase
from django.urls import reverse

from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud
from usuarios.models import EstadoVerificacion, Rol, Usuario

from .models import Mensaje, Notificacion

PASSWORD = "Clave1234"


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, PASSWORD, nombre=correo.split("@")[0], rol=rol,
        estado_verificacion=EstadoVerificacion.APROBADO, **extra,
    )


class BaseMensajeriaTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com", Rol.CLIENTE, telefono="3001110001")
        self.trabajador = crear_usuario(
            "trabajador@example.com", Rol.TRABAJADOR, telefono="3001110002"
        )
        self.ajeno = crear_usuario("ajeno@example.com", Rol.CLIENTE, telefono="3001110003")
        self.solicitud = Solicitud.objects.create(
            descripcion="Arreglar una fuga",
            categoria=CategoriaServicio.PLOMERIA,
            cliente=self.cliente,
            trabajador=self.trabajador,
            estado=EstadoSolicitud.ACEPTADA,
        )


class ChatTests(BaseMensajeriaTests):
    def test_cliente_y_trabajador_pueden_entrar(self):
        self.client.force_login(self.cliente)
        self.assertEqual(
            self.client.get(reverse("mensajeria:chat", args=[self.solicitud.id])).status_code,
            200,
        )
        self.client.force_login(self.trabajador)
        self.assertEqual(
            self.client.get(reverse("mensajeria:chat", args=[self.solicitud.id])).status_code,
            200,
        )

    def test_una_persona_ajena_no_puede_entrar(self):
        self.client.force_login(self.ajeno)
        r = self.client.get(reverse("mensajeria:chat", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 403)

    def test_enviar_mensaje_avisa_a_la_contraparte(self):
        self.client.force_login(self.cliente)
        r = self.client.post(
            reverse("mensajeria:chat", args=[self.solicitud.id]),
            {"contenido": "  Voy en camino  "},
        )
        self.assertRedirects(
            r, reverse("mensajeria:chat", args=[self.solicitud.id])
        )

        mensaje = Mensaje.objects.get()
        self.assertEqual(mensaje.contenido, "Voy en camino")
        self.assertEqual(mensaje.emisor, self.cliente)

        aviso = Notificacion.objects.get(usuario=self.trabajador)
        self.assertEqual(aviso.tipo, "MENSAJE")
        self.assertIn("Voy en camino", aviso.mensaje)

    def test_mensaje_vacio_no_se_guarda(self):
        self.client.force_login(self.cliente)
        self.client.post(
            reverse("mensajeria:chat", args=[self.solicitud.id]), {"contenido": "   "}
        )
        self.assertFalse(Mensaje.objects.exists())

    def test_abrir_el_chat_marca_leidos_los_recibidos(self):
        recibido = Mensaje.objects.create(
            solicitud=self.solicitud, emisor=self.trabajador, contenido="Hola"
        )
        propio = Mensaje.objects.create(
            solicitud=self.solicitud, emisor=self.cliente, contenido="Buen día"
        )

        self.client.force_login(self.cliente)
        self.client.get(reverse("mensajeria:chat", args=[self.solicitud.id]))

        recibido.refresh_from_db()
        propio.refresh_from_db()
        self.assertTrue(recibido.leido)
        self.assertFalse(propio.leido)


class NotificacionesTests(BaseMensajeriaTests):
    def setUp(self):
        super().setUp()
        self.propia = Notificacion.objects.create(
            usuario=self.cliente, tipo="ESTADO", mensaje="Tu solicitud fue aceptada"
        )
        self.otra = Notificacion.objects.create(
            usuario=self.ajeno, tipo="ESTADO", mensaje="Aviso para otra persona"
        )

    def test_solo_muestra_las_propias(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("mensajeria:notificaciones"))
        self.assertContains(r, "Tu solicitud fue aceptada")
        self.assertNotContains(r, "Aviso para otra persona")

    def test_filtra_por_tipo(self):
        Notificacion.objects.create(
            usuario=self.cliente, tipo="PAGO", mensaje="Recibiste un pago"
        )
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("mensajeria:notificaciones"), {"tipo": "PAGO"})
        self.assertContains(r, "Recibiste un pago")
        self.assertNotContains(r, "Tu solicitud fue aceptada")

    def test_marcar_una_como_leida(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("mensajeria:marcar_leida", args=[self.propia.id]))
        self.assertRedirects(r, reverse("mensajeria:notificaciones"))
        self.propia.refresh_from_db()
        self.assertTrue(self.propia.leido)

    def test_marcar_todas_como_leidas(self):
        self.client.force_login(self.cliente)
        self.client.post(reverse("mensajeria:marcar_todas"))
        self.propia.refresh_from_db()
        self.assertTrue(self.propia.leido)
        # La de otra persona no se toca.
        self.otra.refresh_from_db()
        self.assertFalse(self.otra.leido)

    def test_eliminar_la_propia(self):
        self.client.force_login(self.cliente)
        self.client.post(reverse("mensajeria:eliminar", args=[self.propia.id]))
        self.assertFalse(Notificacion.objects.filter(pk=self.propia.pk).exists())

    def test_no_puede_eliminar_la_de_otra_persona(self):
        self.client.force_login(self.cliente)
        self.client.post(reverse("mensajeria:eliminar", args=[self.otra.id]))
        self.assertTrue(Notificacion.objects.filter(pk=self.otra.pk).exists())
