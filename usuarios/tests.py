import shutil
import tempfile

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .localidades import LOCALIDADES
from .models import EstadoVerificacion, Rol, Usuario
from .permisos import rol_requerido

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()


def imagen(nombre="foto.png"):
    return SimpleUploadedFile(nombre, b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class RegistroTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def base(self, **extra):
        datos = {
            "password": PASSWORD, "confirm_password": PASSWORD,
            "acepta_terminos": "true", "acepta_datos": "true",
        }
        datos.update(extra)
        return datos

    def datos_cliente(self, **extra):
        return self.base(**{
            "nombre": "Ana Perez", "correo": "ana@example.com", "rol": "CLIENTE",
            "telefono": "3001234567", "localidad": "Chapinero", "barrio": "Marly", **extra,
        })

    def datos_trabajador(self, **extra):
        return self.base(**{
            "nombre": "Luis Gomez", "correo": "luis@example.com", "rol": "TRABAJADOR",
            "telefono": "3109876543", "localidad": "Suba", "oficio": "Plomería",
            "anios_experiencia": "5", "cuenta_bancaria": "Banco Demo Ahorros 000111",
            "numero_documento": "1012345678",
            "documento": imagen("doc.png"), "selfie": imagen("selfie.png"), **extra,
        })

    def datos_aliado(self, **extra):
        return self.base(**{
            "nombre": "Ferre Sur", "correo": "ferre@example.com", "rol": "ALIADO_COMERCIAL",
            "razon_social": "Ferretería Sur SAS", "nit": "900123456", "tipo_aliado": "Ferretería",
            "telefono": "3205550000", "direccion_negocio": "Calle 1 # 2-3",
            "documento_legal": SimpleUploadedFile("rut.pdf", b"%PDF-1.4 demo", content_type="application/pdf"),
            **extra,
        })

    def test_registro_cliente_exitoso(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_cliente())
        self.assertRedirects(r, reverse("usuarios:login"))
        u = Usuario.objects.get(correo="ana@example.com")
        self.assertEqual(u.rol, Rol.CLIENTE)
        self.assertEqual(u.estado_verificacion, EstadoVerificacion.APROBADO)
        self.assertNotEqual(u.password, PASSWORD)
        self.assertTrue(u.check_password(PASSWORD))

    def test_cliente_sin_telefono_ni_localidad(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_cliente(telefono="", localidad=""))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(correo="ana@example.com").exists())
        self.assertIn("telefono", r.context["form"].errors)
        self.assertIn("localidad", r.context["form"].errors)

    def test_contrasena_debil(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_cliente(password="abcdefgh"))
        self.assertIn("password", r.context["form"].errors)

    def test_correo_duplicado(self):
        self.client.post(reverse("usuarios:registro"), self.datos_cliente())
        r = self.client.post(
            reverse("usuarios:registro"),
            self.datos_cliente(correo="ANA@example.com", telefono="3009999999"),
        )
        self.assertIn("correo", r.context["form"].errors)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_telefono_duplicado(self):
        self.client.post(reverse("usuarios:registro"), self.datos_cliente())
        r = self.client.post(reverse("usuarios:registro"), self.datos_cliente(correo="otra@example.com"))
        self.assertIn("telefono", r.context["form"].errors)

    def test_contrasenas_distintas(self):
        r = self.client.post(
            reverse("usuarios:registro"), self.datos_cliente(confirm_password="Otra12345")
        )
        self.assertIn("confirm_password", r.context["form"].errors)

    def test_terminos_obligatorios(self):
        datos = self.datos_cliente()
        del datos["acepta_terminos"]
        del datos["acepta_datos"]
        r = self.client.post(reverse("usuarios:registro"), datos)
        self.assertIn("acepta_terminos", r.context["form"].errors)
        self.assertIn("acepta_datos", r.context["form"].errors)

    def test_rol_administrador_no_se_puede_registrar(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_cliente(rol="ADMINISTRADOR"))
        self.assertIn("rol", r.context["form"].errors)
        self.assertFalse(Usuario.objects.exists())

    def test_trabajador_exige_perfil_documento_y_archivos(self):
        datos = self.base(nombre="Luis Gomez", correo="luis@example.com", rol="TRABAJADOR")
        r = self.client.post(reverse("usuarios:registro"), datos)
        errores = r.context["form"].errors
        for campo in ("telefono", "localidad", "oficio", "anios_experiencia", "cuenta_bancaria",
                      "numero_documento", "documento", "selfie"):
            self.assertIn(campo, errores)

    def test_trabajador_exitoso_queda_pendiente(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_trabajador())
        self.assertRedirects(r, reverse("usuarios:login"))
        u = Usuario.objects.get(correo="luis@example.com")
        self.assertEqual(u.estado_verificacion, EstadoVerificacion.PENDIENTE)
        self.assertEqual(u.oficio, "Plomería")
        self.assertEqual(u.anios_experiencia, 5)
        self.assertTrue(u.documento.name.startswith("documentos/"))
        self.assertTrue(u.acepta_terminos and u.acepta_datos)

    def test_archivo_con_extension_no_permitida(self):
        exe = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(reverse("usuarios:registro"), self.datos_trabajador(documento=exe))
        self.assertIn("documento", r.context["form"].errors)

    def test_aliado_exitoso_queda_aprobado(self):
        r = self.client.post(reverse("usuarios:registro"), self.datos_aliado())
        self.assertRedirects(r, reverse("usuarios:login"))
        u = Usuario.objects.get(correo="ferre@example.com")
        self.assertEqual(u.estado_verificacion, EstadoVerificacion.APROBADO)
        self.assertEqual(u.nit, "900123456")
        self.assertIsNone(u.numero_documento)

    def test_aliado_exige_datos_del_negocio(self):
        datos = self.base(nombre="Ferre Sur", correo="ferre@example.com", rol="ALIADO_COMERCIAL")
        r = self.client.post(reverse("usuarios:registro"), datos)
        errores = r.context["form"].errors
        for campo in ("razon_social", "nit", "tipo_aliado", "telefono", "direccion_negocio", "documento_legal"):
            self.assertIn(campo, errores)

    def test_nit_duplicado(self):
        self.client.post(reverse("usuarios:registro"), self.datos_aliado())
        otro = self.datos_aliado(correo="otro@example.com", telefono="3205551111")
        r = self.client.post(reverse("usuarios:registro"), otro)
        self.assertIn("nit", r.context["form"].errors)


class LoginTests(TestCase):
    def setUp(self):
        self.cliente = Usuario.objects.create_user(
            "cli@example.com", PASSWORD, nombre="Cli", rol=Rol.CLIENTE,
            estado_verificacion=EstadoVerificacion.APROBADO,
        )
        self.admin = Usuario.objects.create_superuser("adm@example.com", PASSWORD, nombre="Adm")

    def entrar(self, correo, password=PASSWORD):
        return self.client.post(reverse("usuarios:login"), {"username": correo, "password": password})

    def test_login_cliente_va_al_panel(self):
        self.assertRedirects(self.entrar("cli@example.com"), reverse("usuarios:panel"))

    def test_login_admin_va_a_gestion(self):
        r = self.entrar("adm@example.com")
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)

    def test_login_no_distingue_mayusculas_en_el_correo(self):
        self.assertRedirects(self.entrar("CLI@Example.com"), reverse("usuarios:panel"))

    def test_credenciales_incorrectas(self):
        r = self.entrar("cli@example.com", "otra-clave")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Correo o contraseña incorrectos")

    def test_usuario_bloqueado_no_entra(self):
        self.cliente.bloqueado = True
        self.cliente.save()
        r = self.entrar("cli@example.com")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_panel_exige_login(self):
        r = self.client.get(reverse("usuarios:panel"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])

    def test_logout_solo_por_post(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("usuarios:logout")).status_code, 405)
        self.client.post(reverse("usuarios:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_solo_administrador_es_staff(self):
        self.assertTrue(self.admin.is_staff)
        self.assertFalse(self.cliente.is_staff)


class PaginasTests(TestCase):
    def test_inicio_publico(self):
        r = self.client.get(reverse("usuarios:inicio"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Aliados comerciales")

    def test_login_tiene_carrusel_y_boton_de_tema(self):
        r = self.client.get(reverse("usuarios:login"))
        self.assertContains(r, "carrusel-item")
        self.assertContains(r, "btn-tema-nav")

    def test_registro_muestra_los_tres_bloques(self):
        r = self.client.get(reverse("usuarios:registro"))
        for bloque in ("camposCliente", "camposTrabajadorPerfil", "camposAliado"):
            self.assertContains(r, bloque)

    def test_panel_para_cada_rol(self):
        for i, rol in enumerate([Rol.CLIENTE, Rol.TRABAJADOR, Rol.ALIADO_COMERCIAL]):
            u = Usuario.objects.create_user(f"u{i}@example.com", PASSWORD, nombre="U", rol=rol)
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("usuarios:panel")).status_code, 200)
        admin = Usuario.objects.create_superuser("adm@example.com", PASSWORD, nombre="Adm")
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("usuarios:panel")), "Cambell · Admin")


class PermisosTests(TestCase):
    def test_rol_requerido(self):
        @rol_requerido(Rol.ADMINISTRADOR)
        def vista(request):
            return "ok"

        cliente = Usuario.objects.create_user("c@example.com", PASSWORD, nombre="C", rol=Rol.CLIENTE)
        admin = Usuario.objects.create_superuser("a@example.com", PASSWORD, nombre="A")
        rf = RequestFactory()

        peticion = rf.get("/x")
        peticion.user = cliente
        with self.assertRaises(PermissionDenied):
            vista(peticion)

        peticion.user = admin
        self.assertEqual(vista(peticion), "ok")


class LocalidadesTests(TestCase):
    def test_catalogo_completo(self):
        self.assertEqual(len(LOCALIDADES), 12)
        self.assertEqual(sum(len(b) for b in LOCALIDADES.values()), 60)
