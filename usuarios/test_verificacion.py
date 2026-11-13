"""Pruebas de la Fase 1C: reintento y actualización de documentos."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Archivo, EstadoVerificacion, Rol, Usuario, Verificacion

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()


def imagen(nombre="foto.png"):
    return SimpleUploadedFile(
        nombre, b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png"
    )


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, PASSWORD, nombre=correo.split("@")[0], rol=rol,
        estado_verificacion=EstadoVerificacion.APROBADO, **extra,
    )


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class VerificacionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.trabajador = crear_usuario(
            "trabajador@example.com", Rol.TRABAJADOR, telefono="3005550001"
        )
        self.trabajador.estado_verificacion = EstadoVerificacion.RECHAZADO
        self.trabajador.save(update_fields=["estado_verificacion"])
        self.cliente = crear_usuario(
            "cliente@example.com", Rol.CLIENTE, telefono="3005550002"
        )

    def test_get_muestra_el_formulario_de_reintento(self):
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("verificacion:reintentar"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Reintentar verificación")

    def test_reintento_guarda_archivos_y_deja_pendiente(self):
        self.client.force_login(self.trabajador)
        r = self.client.post(
            reverse("verificacion:reintentar"),
            {"documento": imagen("documento.png"), "selfie": imagen("selfie.png")},
        )
        self.assertRedirects(r, reverse("solicitudes:disponibles"))

        self.trabajador.refresh_from_db()
        self.assertEqual(
            self.trabajador.estado_verificacion, EstadoVerificacion.PENDIENTE
        )
        self.assertTrue(self.trabajador.documento.name.startswith("documentos/"))
        self.assertTrue(self.trabajador.selfie.name.startswith("selfies/"))

        verificacion = Verificacion.objects.get(trabajador=self.trabajador)
        self.assertEqual(verificacion.estado, Verificacion.Estado.PENDIENTE)
        self.assertEqual(verificacion.origen, Verificacion.Origen.MANUAL)
        self.assertIsNotNone(verificacion.documento)
        self.assertIsNotNone(verificacion.selfie)

        self.assertEqual(
            Archivo.objects.filter(propietario=self.trabajador).count(), 2
        )

    def test_reintento_sin_archivos_no_cambia_el_estado(self):
        self.client.force_login(self.trabajador)
        self.client.post(reverse("verificacion:reintentar"), {})
        self.trabajador.refresh_from_db()
        self.assertEqual(
            self.trabajador.estado_verificacion, EstadoVerificacion.RECHAZADO
        )
        self.assertFalse(Verificacion.objects.exists())

    def test_actualizar_documento_deja_pendiente(self):
        self.trabajador.estado_verificacion = EstadoVerificacion.APROBADO
        self.trabajador.save(update_fields=["estado_verificacion"])

        self.client.force_login(self.trabajador)
        r = self.client.post(
            reverse("verificacion:actualizar_documento"),
            {"documento": imagen("renovado.png")},
        )
        self.assertRedirects(r, reverse("solicitudes:mis_trabajos"))

        self.trabajador.refresh_from_db()
        self.assertEqual(
            self.trabajador.estado_verificacion, EstadoVerificacion.PENDIENTE
        )
        self.assertEqual(
            Verificacion.objects.filter(trabajador=self.trabajador).count(), 1
        )
        self.assertEqual(
            Archivo.objects.filter(
                propietario=self.trabajador, tipo=Archivo.Tipo.DOCUMENTO
            ).count(),
            1,
        )

    def test_actualizar_documento_sin_archivo_no_hace_nada(self):
        self.trabajador.estado_verificacion = EstadoVerificacion.APROBADO
        self.trabajador.save(update_fields=["estado_verificacion"])

        self.client.force_login(self.trabajador)
        self.client.post(reverse("verificacion:actualizar_documento"), {})
        self.trabajador.refresh_from_db()
        self.assertEqual(
            self.trabajador.estado_verificacion, EstadoVerificacion.APROBADO
        )
        self.assertFalse(Verificacion.objects.exists())

    def test_solo_un_trabajador_puede_reintentar(self):
        self.client.force_login(self.cliente)
        self.assertEqual(
            self.client.get(reverse("verificacion:reintentar")).status_code, 403
        )
