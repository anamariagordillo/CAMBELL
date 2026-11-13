"""Pruebas de la Fase 1C: CRUD de anuncios y moderación del administrador."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.models import EstadoVerificacion, Rol, Usuario

from .models import Anuncio

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()


def imagen(nombre="anuncio.png"):
    return SimpleUploadedFile(
        nombre, b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png"
    )


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, PASSWORD, nombre=correo.split("@")[0], rol=rol,
        estado_verificacion=EstadoVerificacion.APROBADO, **extra,
    )


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class AnunciosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.aliado = crear_usuario(
            "aliado@example.com", Rol.ALIADO_COMERCIAL, telefono="3002220001"
        )
        self.otro_aliado = crear_usuario(
            "otro@example.com", Rol.ALIADO_COMERCIAL, telefono="3002220002"
        )
        self.admin = Usuario.objects.create_superuser(
            "admin@example.com", PASSWORD, nombre="Admin"
        )
        self.cliente = crear_usuario(
            "cliente@example.com", Rol.CLIENTE, telefono="3002220003"
        )

    def datos(self, **extra):
        datos = {
            "titulo": "Ferretería con descuento",
            "descripcion": "Materiales para tu hogar con 10 % de descuento.",
            "imagen": imagen(),
        }
        datos.update(extra)
        return datos

    def test_aliado_crea_anuncio_pendiente(self):
        self.client.force_login(self.aliado)
        r = self.client.post(reverse("anuncios:nuevo"), self.datos())
        self.assertRedirects(r, reverse("anuncios:mios"))

        anuncio = Anuncio.objects.get()
        self.assertEqual(anuncio.aliado, self.aliado)
        self.assertEqual(anuncio.estado, Anuncio.Estado.PENDIENTE)
        self.assertTrue(anuncio.imagen.name.startswith("anuncios/"))

    def test_titulo_vacio_no_se_acepta(self):
        self.client.force_login(self.aliado)
        r = self.client.post(reverse("anuncios:nuevo"), self.datos(titulo="   "))
        self.assertEqual(r.status_code, 200)
        self.assertIn("titulo", r.context["form"].errors)
        self.assertFalse(Anuncio.objects.exists())

    def test_otro_rol_no_puede_publicar(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("anuncios:nuevo"))
        self.assertEqual(r.status_code, 403)

    def test_editar_vuelve_a_pendiente_y_limpia_el_rechazo(self):
        anuncio = Anuncio.objects.create(
            aliado=self.aliado, titulo="Viejo", descripcion="Texto",
            estado=Anuncio.Estado.RECHAZADO, motivo_rechazo="No permitido",
        )
        self.client.force_login(self.aliado)
        r = self.client.post(
            reverse("anuncios:editar", args=[anuncio.id]),
            self.datos(titulo="Nuevo título", imagen=""),
        )
        self.assertRedirects(r, reverse("anuncios:mios"))

        anuncio.refresh_from_db()
        self.assertEqual(anuncio.titulo, "Nuevo título")
        self.assertEqual(anuncio.estado, Anuncio.Estado.PENDIENTE)
        self.assertEqual(anuncio.motivo_rechazo, "")

    def test_no_puede_editar_el_anuncio_de_otro(self):
        anuncio = Anuncio.objects.create(
            aliado=self.otro_aliado, titulo="Ajeno", descripcion="Texto"
        )
        self.client.force_login(self.aliado)
        self.client.post(
            reverse("anuncios:editar", args=[anuncio.id]), self.datos(imagen="")
        )
        anuncio.refresh_from_db()
        self.assertEqual(anuncio.titulo, "Ajeno")

    def test_eliminar_el_propio(self):
        anuncio = Anuncio.objects.create(
            aliado=self.aliado, titulo="Borrar", descripcion="Texto"
        )
        self.client.force_login(self.aliado)
        self.client.post(reverse("anuncios:eliminar", args=[anuncio.id]))
        self.assertFalse(Anuncio.objects.filter(pk=anuncio.pk).exists())

    def test_admin_aprueba_y_rechaza(self):
        anuncio = Anuncio.objects.create(
            aliado=self.aliado, titulo="Publicar", descripcion="Texto"
        )
        self.client.force_login(self.admin)

        self.client.post(reverse("panel_admin:aprobar_anuncio", args=[anuncio.id]))
        anuncio.refresh_from_db()
        self.assertEqual(anuncio.estado, Anuncio.Estado.PUBLICADO)

        self.client.post(
            reverse("panel_admin:rechazar_anuncio", args=[anuncio.id]),
            {"motivo": "Imagen no relacionada"},
        )
        anuncio.refresh_from_db()
        self.assertEqual(anuncio.estado, Anuncio.Estado.RECHAZADO)
        self.assertEqual(anuncio.motivo_rechazo, "Imagen no relacionada")

    def test_solo_el_admin_modera(self):
        anuncio = Anuncio.objects.create(
            aliado=self.aliado, titulo="Publicar", descripcion="Texto"
        )
        self.client.force_login(self.aliado)
        r = self.client.post(
            reverse("panel_admin:aprobar_anuncio", args=[anuncio.id])
        )
        self.assertEqual(r.status_code, 403)

    def test_login_del_aliado_va_a_sus_anuncios(self):
        r = self.client.post(
            reverse("usuarios:login"),
            {"username": "aliado@example.com", "password": PASSWORD},
        )
        self.assertRedirects(r, reverse("anuncios:mios"))
