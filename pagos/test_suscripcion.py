"""Pruebas de la Fase 1C: suscripción premium simulada y reembolsos."""
from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud
from usuarios.models import EstadoVerificacion, Rol, Usuario

from .models import Pago, Reembolso, Suscripcion


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol,
        estado_verificacion=EstadoVerificacion.APROBADO, **extra,
    )


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class SuscripcionTests(TestCase):
    def setUp(self):
        self.trabajador = crear_usuario(
            "trabajador@example.com", Rol.TRABAJADOR, telefono="3003330001"
        )

    def test_contratar_activa_el_plan_y_avisa(self):
        self.client.force_login(self.trabajador)
        r = self.client.post(reverse("pagos:contratar_suscripcion"))
        self.assertRedirects(r, reverse("pagos:suscripcion"))

        suscripcion = Suscripcion.objects.get(trabajador=self.trabajador)
        self.assertTrue(suscripcion.activa)
        self.assertTrue(suscripcion.renovacion_automatica)
        self.assertGreater(suscripcion.fecha_vencimiento, timezone.now())
        self.assertEqual(
            self.trabajador.notificaciones.filter(tipo="SUSCRIPCION").count(), 1
        )

    @override_settings(PROBABILIDAD_PAGO_APROBADO=0.0)
    def test_pago_rechazado_no_activa_nada(self):
        self.client.force_login(self.trabajador)
        r = self.client.post(reverse("pagos:contratar_suscripcion"))
        self.assertIn("rechazado", " ".join(mensajes(r)))
        self.assertFalse(Suscripcion.objects.exists())

    def test_cancelar_apaga_la_renovacion(self):
        Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            renovacion_automatica=True,
            fecha_vencimiento=timezone.now() + timedelta(days=20),
        )
        self.client.force_login(self.trabajador)
        r = self.client.post(reverse("pagos:cancelar_suscripcion"))
        self.assertRedirects(r, reverse("pagos:suscripcion"))

        suscripcion = Suscripcion.objects.get(trabajador=self.trabajador)
        self.assertFalse(suscripcion.renovacion_automatica)
        self.assertTrue(suscripcion.activa)  # sigue disfrutando el periodo pagado

    def test_cancelar_sin_suscripcion_muestra_error(self):
        self.client.force_login(self.trabajador)
        r = self.client.post(reverse("pagos:cancelar_suscripcion"))
        self.assertIn("No tienes una suscripción activa", " ".join(mensajes(r)))

    def test_una_suscripcion_vencida_no_cuenta_como_activa(self):
        Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            renovacion_automatica=True,
            fecha_vencimiento=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("pagos:suscripcion"))
        self.assertFalse(r.context["activa"])
        self.assertContains(r, "vencida")

    def test_exige_iniciar_sesion(self):
        r = self.client.get(reverse("pagos:suscripcion"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])


class ReembolsoTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario(
            "cliente@example.com", Rol.CLIENTE, telefono="3003330002"
        )
        self.trabajador = crear_usuario(
            "trabajador@example.com", Rol.TRABAJADOR, telefono="3003330003"
        )
        self.admin = Usuario.objects.create_superuser(
            "admin@example.com", "Clave1234", nombre="Admin"
        )
        self.solicitud = Solicitud.objects.create(
            descripcion="Servicio terminado",
            categoria=CategoriaServicio.PLOMERIA,
            cliente=self.cliente,
            trabajador=self.trabajador,
            estado=EstadoSolicitud.COMPLETADA,
        )
        self.pago = Pago.objects.create(
            solicitud=self.solicitud,
            cliente=self.cliente,
            trabajador=self.trabajador,
            monto_total=100000,
            comision=3000,
            neto_trabajador=97000,
            estado=Pago.Estado.COMPLETADO,
            fecha_pago=timezone.now(),
        )

    def test_admin_reembolsa_y_avisa_al_cliente(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse("panel_admin:iniciar_reembolso", args=[self.pago.id]),
            {"motivo": "Servicio no realizado"},
        )
        self.assertRedirects(r, reverse("panel_admin:reembolsos"))

        self.pago.refresh_from_db()
        self.assertEqual(self.pago.estado, Pago.Estado.REEMBOLSADO)
        reembolso = Reembolso.objects.get(pago=self.pago)
        self.assertEqual(reembolso.monto, self.pago.monto_total)
        self.assertEqual(reembolso.motivo, "Servicio no realizado")
        self.assertEqual(
            self.cliente.notificaciones.filter(tipo="PAGO").count(), 1
        )

    def test_no_se_reembolsa_dos_veces(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("panel_admin:iniciar_reembolso", args=[self.pago.id]))
        r = self.client.post(
            reverse("panel_admin:iniciar_reembolso", args=[self.pago.id])
        )
        self.assertIn("ya fue reembolsado", " ".join(mensajes(r)))
        self.assertEqual(Reembolso.objects.count(), 1)

    def test_no_admin_no_puede_reembolsar(self):
        self.client.force_login(self.cliente)
        r = self.client.post(
            reverse("panel_admin:iniciar_reembolso", args=[self.pago.id])
        )
        self.assertEqual(r.status_code, 403)
