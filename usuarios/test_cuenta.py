"""Pruebas de la Fase 1A: contrasenas, intentos fallidos, perfil y cobertura."""
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CoberturaTrabajador, EstadoVerificacion, Rol, TokenRecuperacion, Usuario

PASSWORD = "Clave1234"
PASSWORD_NUEVA = "NuevaClave99"


class BaseCuentaTests(TestCase):
    def crear_cliente(self, correo="cli@example.com", password=PASSWORD, telefono="3001112233"):
        return Usuario.objects.create_user(
            correo, password, nombre="Cliente Demo", rol=Rol.CLIENTE,
            estado_verificacion=EstadoVerificacion.APROBADO, telefono=telefono,
        )

    def crear_trabajador(self, correo="trab@example.com", telefono="3004445566"):
        return Usuario.objects.create_user(
            correo, PASSWORD, nombre="Trabajador Demo", rol=Rol.TRABAJADOR,
            estado_verificacion=EstadoVerificacion.APROBADO, telefono=telefono,
        )


class RecuperarPasswordTests(BaseCuentaTests):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_envia_correo_y_crea_token(self):
        self.crear_cliente()
        r = self.client.post(
            reverse("usuarios:recuperar_password"), {"correo": "CLI@example.com"}
        )
        self.assertRedirects(r, reverse("usuarios:recuperar_password"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Restablece tu contraseña", mail.outbox[0].subject)

        token = TokenRecuperacion.objects.get(usuario__correo="cli@example.com")
        self.assertIn(token.token, mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_correo_desconocido_no_revela_si_existe(self):
        r = self.client.post(
            reverse("usuarios:recuperar_password"), {"correo": "nadie@example.com"}
        )
        self.assertRedirects(r, reverse("usuarios:recuperar_password"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(TokenRecuperacion.objects.exists())

    def test_token_valido_muestra_formulario(self):
        usuario = self.crear_cliente()
        token = TokenRecuperacion.objects.create(
            usuario=usuario, token="token-demo",
            expiracion=timezone.now() + timedelta(hours=1),
        )
        r = self.client.get(reverse("usuarios:restablecer_password"), {"token": token.token})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["token_valido"])

    def test_restablecer_cambia_password_y_marca_token_usado(self):
        usuario = self.crear_cliente()
        token = TokenRecuperacion.objects.create(
            usuario=usuario, token="token-demo",
            expiracion=timezone.now() + timedelta(hours=1),
        )
        r = self.client.post(
            reverse("usuarios:restablecer_password"),
            {"token": token.token, "password": PASSWORD_NUEVA, "confirmar_password": PASSWORD_NUEVA},
        )
        self.assertRedirects(r, reverse("usuarios:login"))

        usuario.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(usuario.check_password(PASSWORD_NUEVA))
        self.assertTrue(token.usado)

    def test_token_vencido_no_permite_cambiar(self):
        usuario = self.crear_cliente()
        token = TokenRecuperacion.objects.create(
            usuario=usuario, token="viejo",
            expiracion=timezone.now() - timedelta(minutes=1),
        )
        r = self.client.post(
            reverse("usuarios:restablecer_password"),
            {"token": token.token, "password": PASSWORD_NUEVA, "confirmar_password": PASSWORD_NUEVA},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("inválido o ha expirado", str(r.context["form"].non_field_errors()))

    def test_password_debil_no_se_acepta(self):
        usuario = self.crear_cliente()
        token = TokenRecuperacion.objects.create(
            usuario=usuario, token="token-demo",
            expiracion=timezone.now() + timedelta(hours=1),
        )
        r = self.client.post(
            reverse("usuarios:restablecer_password"),
            {"token": token.token, "password": "abcdefgh", "confirmar_password": "abcdefgh"},
        )
        self.assertIn("password", r.context["form"].errors)


class CambiarPasswordTests(BaseCuentaTests):
    def test_cambio_con_password_actual_correcta(self):
        usuario = self.crear_cliente()
        self.client.force_login(usuario)

        r = self.client.post(
            reverse("usuarios:cambiar_password"),
            {
                "password_actual": PASSWORD,
                "password_nueva": PASSWORD_NUEVA,
                "confirmar_password": PASSWORD_NUEVA,
            },
        )
        self.assertRedirects(r, reverse("solicitudes:nueva"))
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(PASSWORD_NUEVA))

    def test_password_actual_incorrecta(self):
        usuario = self.crear_cliente()
        self.client.force_login(usuario)

        r = self.client.post(
            reverse("usuarios:cambiar_password"),
            {
                "password_actual": "incorrecta",
                "password_nueva": PASSWORD_NUEVA,
                "confirmar_password": PASSWORD_NUEVA,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("password_actual", r.context["form"].errors)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(PASSWORD))
        self.assertFalse(usuario.check_password(PASSWORD_NUEVA))

    def test_cambio_forzado_no_pide_password_actual(self):
        usuario = self.crear_cliente()
        usuario.debe_cambiar_password = True
        usuario.save(update_fields=["debe_cambiar_password"])
        self.client.force_login(usuario)

        # Al entrar a otra pantalla, el middleware lo manda a cambiar la clave.
        r = self.client.get(reverse("usuarios:panel"))
        self.assertRedirects(r, reverse("usuarios:cambiar_password"))

        # La pantalla avisa que el cambio es obligatorio.
        r = self.client.get(reverse("usuarios:cambiar_password"))
        self.assertContains(r, "Cambio de contraseña obligatorio")

        r = self.client.post(
            reverse("usuarios:cambiar_password"),
            {"password_nueva": PASSWORD_NUEVA, "confirmar_password": PASSWORD_NUEVA},
        )
        self.assertRedirects(r, reverse("solicitudes:nueva"))
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(PASSWORD_NUEVA))
        self.assertFalse(usuario.debe_cambiar_password)

    def test_login_con_password_vencida_obliga_a_cambiarla(self):
        usuario = Usuario.objects.create_user(
            "viejo@example.com", "debil123", nombre="Clave Vieja", rol=Rol.CLIENTE,
            estado_verificacion=EstadoVerificacion.APROBADO,
        )
        r = self.client.post(
            reverse("usuarios:login"), {"username": "viejo@example.com", "password": "debil123"}
        )
        self.assertRedirects(
            r, reverse("solicitudes:nueva"), fetch_redirect_response=False
        )

        usuario.refresh_from_db()
        self.assertTrue(usuario.debe_cambiar_password)

        r = self.client.get(reverse("usuarios:panel"))
        self.assertRedirects(r, reverse("usuarios:cambiar_password"))


class IntentosFallidosTests(BaseCuentaTests):
    def entrar(self, correo, password):
        return self.client.post(reverse("usuarios:login"), {"username": correo, "password": password})

    def test_bloqueo_despues_de_cinco_intentos(self):
        usuario = self.crear_cliente()

        for _ in range(5):
            self.entrar("cli@example.com", "mala")

        usuario.refresh_from_db()
        self.assertTrue(usuario.bloqueo_temporal_activo)
        self.assertIsNotNone(usuario.bloqueado_hasta)

        # Aun con la contraseña correcta, sigue bloqueado.
        r = self.entrar("cli@example.com", PASSWORD)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Demasiados intentos fallidos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_puede_entrar_cuando_vence_el_bloqueo(self):
        usuario = self.crear_cliente()
        usuario.intentos_fallidos = 5
        usuario.bloqueado_hasta = timezone.now() - timedelta(minutes=1)
        usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

        r = self.entrar("cli@example.com", PASSWORD)
        self.assertRedirects(r, reverse("solicitudes:nueva"))

        usuario.refresh_from_db()
        self.assertEqual(usuario.intentos_fallidos, 0)
        self.assertIsNone(usuario.bloqueado_hasta)

    def test_login_correcto_reinicia_contador(self):
        usuario = self.crear_cliente()
        usuario.intentos_fallidos = 3
        usuario.save(update_fields=["intentos_fallidos"])

        r = self.entrar("cli@example.com", PASSWORD)
        self.assertRedirects(r, reverse("solicitudes:nueva"))
        usuario.refresh_from_db()
        self.assertEqual(usuario.intentos_fallidos, 0)

    def test_bloqueo_manual_no_se_renueva(self):
        usuario = self.crear_cliente()
        usuario.bloqueado = True
        usuario.save(update_fields=["bloqueado"])

        self.entrar("cli@example.com", "mala")
        usuario.refresh_from_db()
        self.assertEqual(usuario.intentos_fallidos, 0)


class PerfilTests(BaseCuentaTests):
    def test_editar_perfil(self):
        usuario = self.crear_cliente()
        self.client.force_login(usuario)

        r = self.client.post(
            reverse("usuarios:editar_perfil"),
            {
                "nombre": "Cliente Nuevo", "correo": "nuevo@example.com",
                "telefono": "3009998877", "localidad": "Suba", "barrio": "Niza",
            },
        )
        self.assertRedirects(r, reverse("usuarios:perfil"))
        usuario.refresh_from_db()
        self.assertEqual(usuario.nombre, "Cliente Nuevo")
        self.assertEqual(usuario.correo, "nuevo@example.com")
        self.assertEqual(usuario.localidad, "Suba")

    def test_no_permite_correo_de_otra_cuenta(self):
        usuario = self.crear_cliente()
        self.crear_cliente(correo="otro@example.com", telefono="3007778899")
        self.client.force_login(usuario)

        r = self.client.post(
            reverse("usuarios:editar_perfil"),
            {
                "nombre": "Cliente Demo", "correo": "otro@example.com",
                "telefono": "3001112233", "localidad": "", "barrio": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("correo", r.context["form"].errors)

    def test_desactivar_cuenta_cierra_sesion(self):
        usuario = self.crear_cliente()
        self.client.force_login(usuario)

        r = self.client.post(reverse("usuarios:desactivar_cuenta"))
        self.assertRedirects(r, reverse("usuarios:login"))
        usuario.refresh_from_db()
        self.assertTrue(usuario.bloqueado)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_desactivar_solo_por_post(self):
        usuario = self.crear_cliente()
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("usuarios:desactivar_cuenta")).status_code, 405)


class CoberturaTests(BaseCuentaTests):
    def test_trabajador_guarda_su_cobertura(self):
        trabajador = self.crear_trabajador()
        self.client.force_login(trabajador)

        r = self.client.post(
            reverse("usuarios:cobertura"),
            {
                "radio_km": "15", "localidades": ["Suba"], "categorias": ["PLOMERIA"],
                "disponible": "on", "hora_inicio": "08:00", "hora_fin": "18:00",
            },
        )
        self.assertRedirects(r, reverse("usuarios:cobertura"))

        cobertura = CoberturaTrabajador.objects.get(trabajador=trabajador)
        self.assertEqual(cobertura.radio_km, 15)
        self.assertEqual(cobertura.localidades, ["Suba"])
        self.assertEqual(cobertura.categorias, ["PLOMERIA"])
        self.assertTrue(cobertura.disponible)

    def test_horario_invalido(self):
        trabajador = self.crear_trabajador()
        self.client.force_login(trabajador)

        r = self.client.post(
            reverse("usuarios:cobertura"),
            {
                "radio_km": "10", "hora_inicio": "18:00", "hora_fin": "08:00",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("hora_fin", r.context["form"].errors)

    def test_cliente_no_puede_entrar_a_cobertura(self):
        cliente = self.crear_cliente()
        self.client.force_login(cliente)
        self.assertEqual(self.client.get(reverse("usuarios:cobertura")).status_code, 403)
