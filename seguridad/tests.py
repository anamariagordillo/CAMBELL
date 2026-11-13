"""Pruebas de la Fase 1C: reportes de seguridad y su moderación."""
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud
from usuarios.models import EstadoVerificacion, Rol, Usuario

from .models import ReporteSeguridad


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol,
        estado_verificacion=EstadoVerificacion.APROBADO, **extra,
    )


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class ReportarTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario(
            "cliente@example.com", Rol.CLIENTE, telefono="3004440001"
        )
        self.trabajador = crear_usuario(
            "trabajador@example.com", Rol.TRABAJADOR, telefono="3004440002"
        )
        self.ajeno = crear_usuario(
            "ajeno@example.com", Rol.CLIENTE, telefono="3004440003"
        )
        self.admin = Usuario.objects.create_superuser(
            "admin@example.com", "Clave1234", nombre="Admin"
        )
        self.solicitud = Solicitud.objects.create(
            descripcion="Trabajo en curso",
            categoria=CategoriaServicio.ELECTRICIDAD,
            cliente=self.cliente,
            trabajador=self.trabajador,
            estado=EstadoSolicitud.ACEPTADA,
        )

    def test_cliente_reporta_al_trabajador(self):
        self.client.force_login(self.cliente)
        r = self.client.post(
            reverse("seguridad:reportar", args=[self.solicitud.id]),
            {"motivo": "Trato irrespetuoso"},
        )
        self.assertRedirects(r, reverse("solicitudes:mis_solicitudes"))

        reporte = ReporteSeguridad.objects.get()
        self.assertEqual(reporte.reportante, self.cliente)
        self.assertEqual(reporte.reportado, self.trabajador)
        self.assertEqual(reporte.estado, ReporteSeguridad.Estado.EN_REVISION)

    def test_trabajador_reporta_al_cliente(self):
        self.client.force_login(self.trabajador)
        r = self.client.post(
            reverse("seguridad:reportar", args=[self.solicitud.id]),
            {"motivo": "Dirección insegura"},
        )
        self.assertRedirects(r, reverse("solicitudes:mis_trabajos"))
        self.assertEqual(ReporteSeguridad.objects.get().reportado, self.cliente)

    def test_una_persona_ajena_no_puede_reportar(self):
        self.client.force_login(self.ajeno)
        r = self.client.post(
            reverse("seguridad:reportar", args=[self.solicitud.id]),
            {"motivo": "Sin permiso"},
        )
        self.assertRedirects(r, reverse("solicitudes:mis_solicitudes"))
        self.assertFalse(ReporteSeguridad.objects.exists())

    def test_motivo_vacio_no_se_acepta(self):
        self.client.force_login(self.cliente)
        self.client.post(
            reverse("seguridad:reportar", args=[self.solicitud.id]), {"motivo": "  "}
        )
        self.assertFalse(ReporteSeguridad.objects.exists())

    def test_admin_bloquea_al_reportado(self):
        reporte = ReporteSeguridad.objects.create(
            reportante=self.cliente, reportado=self.trabajador, motivo="Conducta insegura"
        )
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse("panel_admin:bloquear_reportado", args=[reporte.id])
        )
        self.assertRedirects(r, reverse("panel_admin:reportes"))

        reporte.refresh_from_db()
        self.trabajador.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteSeguridad.Estado.BLOQUEADO)
        self.assertTrue(self.trabajador.bloqueado)

    def test_admin_descarta_el_reporte(self):
        reporte = ReporteSeguridad.objects.create(
            reportante=self.cliente, reportado=self.trabajador, motivo="Duda"
        )
        self.client.force_login(self.admin)
        self.client.post(reverse("panel_admin:descartar_reporte", args=[reporte.id]))
        reporte.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteSeguridad.Estado.DESCARTADO)

    def test_filtros_de_reportes(self):
        ReporteSeguridad.objects.create(
            reportante=self.cliente, reportado=self.trabajador, motivo="Uno"
        )
        ReporteSeguridad.objects.create(
            reportante=self.trabajador, reportado=self.cliente,
            motivo="Dos", estado=ReporteSeguridad.Estado.DESCARTADO,
        )
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("panel_admin:reportes"), {"estado": "EN_REVISION"}
        )
        self.assertContains(r, "Uno")
        self.assertNotContains(r, "Dos")

    def test_solo_admin_ve_reportes(self):
        self.client.force_login(self.cliente)
        self.assertEqual(
            self.client.get(reverse("panel_admin:reportes")).status_code, 403
        )
