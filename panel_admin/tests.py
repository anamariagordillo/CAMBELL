import shutil
import tempfile
from datetime import timedelta

from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from mensajeria.models import Notificacion
from pagos.models import Pago
from seguridad.models import ReporteSeguridad
from solicitudes import servicios as servicios_solicitud
from solicitudes.models import CategoriaServicio
from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import servicios
from .servicios import ErrorAdmin

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, PASSWORD, nombre=correo.split("@")[0], rol=rol, **extra
    )


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class AdminBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.admin = Usuario.objects.create_superuser("adm@example.com", PASSWORD, nombre="Adm")
        self.cliente = crear_usuario(
            "cli@example.com", Rol.CLIENTE, telefono="3001112222", localidad="Chapinero",
            estado_verificacion=EstadoVerificacion.APROBADO,
        )
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, telefono="3003334444", localidad="Suba",
            numero_documento="1012345678",
        )
        self.client.force_login(self.admin)

    def con_archivos(self, usuario):
        usuario.documento.save("doc.png", ContentFile(PNG), save=False)
        usuario.selfie.save("selfie.png", ContentFile(PNG), save=True)


class AccesoTests(AdminBase):
    def test_solo_el_administrador_entra(self):
        urls = [
            reverse("panel_admin:verificaciones"),
            reverse("panel_admin:usuarios"),
            reverse("panel_admin:editar_usuario", args=[self.cliente.id]),
            reverse("panel_admin:historial", args=[self.cliente.id]),
            reverse("panel_admin:imagen", args=[self.trabajador.id]) + "?tipo=selfie",
        ]
        for usuario in (self.cliente, self.trabajador):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_sin_sesion_va_al_login(self):
        self.client.logout()
        r = self.client.get(reverse("panel_admin:usuarios"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])

    def test_la_barra_del_administrador_tiene_sus_botones(self):
        r = self.client.get(reverse("panel_admin:usuarios"))
        self.assertContains(r, "Cambell · Admin")
        self.assertContains(r, reverse("panel_admin:verificaciones"))
        self.assertContains(r, reverse("panel_admin:usuarios"))

    def test_las_acciones_exigen_post(self):
        for nombre in ("aprobar", "rechazar", "bloquear", "reactivar"):
            url = reverse(f"panel_admin:{nombre}", args=[self.trabajador.id])
            self.assertEqual(self.client.get(url).status_code, 405, nombre)


class VerificacionesTests(AdminBase):
    def test_lista_solo_trabajadores_pendientes(self):
        self.cliente.estado_verificacion = EstadoVerificacion.PENDIENTE
        self.cliente.save()
        aprobado = crear_usuario(
            "aprobado@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        r = self.client.get(reverse("panel_admin:verificaciones"))
        self.assertEqual(list(r.context["trabajadores"]), [self.trabajador])
        self.assertContains(r, "trab@example.com")
        self.assertContains(r, "1012345678")
        self.assertNotContains(r, aprobado.correo)
        self.assertNotContains(r, self.cliente.correo)

    def test_sin_pendientes(self):
        Usuario.objects.filter(pk=self.trabajador.pk).update(
            estado_verificacion=EstadoVerificacion.APROBADO
        )
        r = self.client.get(reverse("panel_admin:verificaciones"))
        self.assertContains(r, "No hay verificaciones pendientes.")

    def test_muestra_las_imagenes_por_una_direccion_protegida(self):
        self.con_archivos(self.trabajador)
        r = self.client.get(reverse("panel_admin:verificaciones"))
        self.assertContains(r, reverse("panel_admin:imagen", args=[self.trabajador.id]) + "?tipo=documento")
        self.assertContains(r, reverse("panel_admin:imagen", args=[self.trabajador.id]) + "?tipo=selfie")

    def test_aprobar(self):
        r = self.client.post(reverse("panel_admin:aprobar", args=[self.trabajador.id]))
        self.assertRedirects(r, reverse("panel_admin:verificaciones"))
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.estado_verificacion, EstadoVerificacion.APROBADO)
        aviso = Notificacion.objects.get(usuario=self.trabajador, tipo="VERIFICACION")
        self.assertIn("APROBADA", aviso.mensaje)

    def test_rechazar(self):
        self.client.post(reverse("panel_admin:rechazar", args=[self.trabajador.id]))
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.estado_verificacion, EstadoVerificacion.RECHAZADO)
        aviso = Notificacion.objects.get(usuario=self.trabajador, tipo="VERIFICACION")
        self.assertIn("RECHAZADA", aviso.mensaje)

    def test_al_decidir_se_borra_el_motivo_de_la_revision(self):
        Usuario.objects.filter(pk=self.trabajador.pk).update(motivo_verificacion="Rostro poco claro")
        self.client.post(reverse("panel_admin:aprobar", args=[self.trabajador.id]))
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.motivo_verificacion, "")

    def test_solo_se_verifican_trabajadores(self):
        r = self.client.post(reverse("panel_admin:aprobar", args=[self.cliente.id]))
        self.assertIn("Solo se verifican trabajadores.", mensajes(r))
        self.assertFalse(Notificacion.objects.filter(usuario=self.cliente).exists())

    def test_aprobar_un_usuario_inexistente(self):
        r = self.client.post(reverse("panel_admin:aprobar", args=[9999]))
        self.assertIn("Usuario no encontrado", mensajes(r))

    def test_un_trabajador_aprobado_ya_puede_aceptar_solicitudes(self):
        self.client.post(reverse("panel_admin:aprobar", args=[self.trabajador.id]))
        s = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Prueba", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly",
        )
        self.trabajador.refresh_from_db()
        servicios_solicitud.aceptar(s.id, self.trabajador)


class ImagenTests(AdminBase):
    def test_el_administrador_ve_el_archivo(self):
        self.con_archivos(self.trabajador)
        url = reverse("panel_admin:imagen", args=[self.trabajador.id])
        r = self.client.get(url + "?tipo=selfie")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(b"".join(r.streaming_content), PNG)
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.get(url + "?tipo=documento").status_code, 200)

    def test_tipo_desconocido_o_ausente(self):
        self.con_archivos(self.trabajador)
        url = reverse("panel_admin:imagen", args=[self.trabajador.id])
        self.assertEqual(self.client.get(url + "?tipo=otro").status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_usuario_sin_archivo(self):
        url = reverse("panel_admin:imagen", args=[self.cliente.id])
        self.assertEqual(self.client.get(url + "?tipo=selfie").status_code, 404)

    def test_archivo_borrado_del_disco(self):
        self.con_archivos(self.trabajador)
        self.trabajador.selfie.delete(save=False)  # borra el archivo, pero la base sigue apuntando a él
        Usuario.objects.filter(pk=self.trabajador.pk).update(selfie="selfies/no_existe.png")
        url = reverse("panel_admin:imagen", args=[self.trabajador.id])
        self.assertEqual(self.client.get(url + "?tipo=selfie").status_code, 404)

    def test_el_archivo_no_tiene_direccion_publica(self):
        self.con_archivos(self.trabajador)
        self.assertEqual(self.client.get("/uploads/" + self.trabajador.selfie.name).status_code, 404)


class UsuariosListaTests(AdminBase):
    def ids(self, **filtros):
        r = self.client.get(reverse("panel_admin:usuarios"), filtros)
        return {u.id for u in r.context["resultados"]}

    def test_sin_filtros_lista_a_todos(self):
        self.assertEqual(self.ids(), {self.admin.id, self.cliente.id, self.trabajador.id})

    def test_filtros_simples(self):
        self.assertEqual(self.ids(rol="TRABAJADOR"), {self.trabajador.id})
        self.assertEqual(self.ids(localidad="Chapinero"), {self.cliente.id})
        self.assertEqual(self.ids(estado_verificacion="PENDIENTE"), {self.trabajador.id})
        self.assertEqual(self.ids(estado_verificacion="APROBADO"), {self.admin.id, self.cliente.id})

    def test_filtro_por_estado_de_cuenta(self):
        Usuario.objects.filter(pk=self.cliente.pk).update(bloqueado=True)
        self.assertEqual(self.ids(cuenta="bloqueados"), {self.cliente.id})
        self.assertEqual(self.ids(cuenta="activos"), {self.admin.id, self.trabajador.id})

    def test_busqueda_por_nombre_correo_o_telefono(self):
        self.assertEqual(self.ids(q="TRAB"), {self.trabajador.id})
        self.assertEqual(self.ids(q="cli@example"), {self.cliente.id})
        self.assertEqual(self.ids(q="1112222"), {self.cliente.id})
        self.assertEqual(self.ids(q="  "), {self.admin.id, self.cliente.id, self.trabajador.id})

    def test_los_criterios_se_combinan(self):
        self.assertEqual(self.ids(rol="CLIENTE", localidad="Suba"), set())
        self.assertEqual(self.ids(rol="TRABAJADOR", localidad="Suba", q="trab"), {self.trabajador.id})

    def test_rango_de_fechas_de_registro(self):
        hoy = timezone.localdate()
        Usuario.objects.filter(pk=self.cliente.pk).update(
            fecha_registro=timezone.now() - timedelta(days=30)
        )
        hace_30 = (hoy - timedelta(days=30)).isoformat()
        self.assertEqual(self.ids(desde=hace_30, hasta=hace_30), {self.cliente.id})
        self.assertEqual(self.ids(hasta=(hoy - timedelta(days=1)).isoformat()), {self.cliente.id})
        self.assertNotIn(self.cliente.id, self.ids(desde=hoy.isoformat()))

    def test_valores_invalidos_se_ignoran(self):
        self.assertEqual(
            self.ids(rol="NOEXISTE", estado_verificacion="XX", cuenta="rara", desde="ayer"),
            {self.admin.id, self.cliente.id, self.trabajador.id},
        )

    def test_los_filtros_se_conservan_en_el_formulario(self):
        r = self.client.get(reverse("panel_admin:usuarios"), {"rol": "CLIENTE", "q": "ana"})
        self.assertContains(r, 'value="ana"')
        self.assertContains(r, '<option value="CLIENTE" selected>')

    def test_sin_resultados(self):
        r = self.client.get(reverse("panel_admin:usuarios"), {"q": "nadie-se-llama-asi"})
        self.assertContains(r, "No hay usuarios que coincidan")


class BloquearTests(AdminBase):
    def test_bloquear_y_reactivar(self):
        self.client.post(reverse("panel_admin:bloquear", args=[self.cliente.id]))
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.bloqueado)

        self.client.post(reverse("panel_admin:reactivar", args=[self.cliente.id]))
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.bloqueado)

    def test_un_usuario_bloqueado_no_puede_iniciar_sesion(self):
        self.client.post(reverse("panel_admin:bloquear", args=[self.cliente.id]))
        self.client.logout()
        self.client.post(reverse("usuarios:login"), {"username": "cli@example.com", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

        self.client.force_login(self.admin)
        self.client.post(reverse("panel_admin:reactivar", args=[self.cliente.id]))
        self.client.logout()
        self.client.post(reverse("usuarios:login"), {"username": "cli@example.com", "password": PASSWORD})
        self.assertIn("_auth_user_id", self.client.session)

    def test_el_administrador_no_puede_bloquearse_a_si_mismo(self):
        r = self.client.post(reverse("panel_admin:bloquear", args=[self.admin.id]))
        self.assertIn("No puedes bloquear tu propia cuenta.", mensajes(r))
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.bloqueado)

    def test_no_aparece_el_boton_de_bloquear_en_la_propia_cuenta(self):
        r = self.client.get(reverse("panel_admin:usuarios"), {"q": "adm@"})
        self.assertContains(r, "(tu cuenta)")
        self.assertNotContains(r, reverse("panel_admin:bloquear", args=[self.admin.id]))


class EditarUsuarioTests(AdminBase):
    def editar(self, usuario, **datos):
        base = {
            "nombre": usuario.nombre, "correo": usuario.correo,
            "telefono": usuario.telefono or "", "rol": usuario.rol,
        }
        base.update(datos)
        return self.client.post(reverse("panel_admin:editar_usuario", args=[usuario.id]), base)

    def test_ver_el_formulario(self):
        r = self.client.get(reverse("panel_admin:editar_usuario", args=[self.cliente.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "cli@example.com")

    def test_guardar_cambios(self):
        r = self.editar(self.cliente, nombre="Ana Nueva", correo="ANA@Example.com",
                        telefono="3005556666", rol="ALIADO_COMERCIAL")
        self.assertRedirects(r, reverse("panel_admin:usuarios"))
        self.assertIn("Usuario actualizado correctamente.", mensajes(r))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Ana Nueva")
        self.assertEqual(self.cliente.correo, "ana@example.com")
        self.assertEqual(self.cliente.telefono, "3005556666")
        self.assertEqual(self.cliente.rol, Rol.ALIADO_COMERCIAL)

    def test_los_campos_vacios_no_se_tocan(self):
        self.editar(self.cliente, nombre="", correo="", telefono="")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "cli")
        self.assertEqual(self.cliente.correo, "cli@example.com")
        self.assertEqual(self.cliente.telefono, "3001112222")

    def test_correo_repetido(self):
        r = self.editar(self.cliente, correo="TRAB@example.com")
        self.assertRedirects(r, reverse("panel_admin:editar_usuario", args=[self.cliente.id]),
                             fetch_redirect_response=False)
        self.assertIn("Ya existe un usuario con ese correo.", mensajes(r))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.correo, "cli@example.com")

    def test_se_puede_guardar_con_el_mismo_correo(self):
        r = self.editar(self.cliente, nombre="Otro Nombre")
        self.assertIn("Usuario actualizado correctamente.", mensajes(r))

    def test_telefono_repetido_o_invalido(self):
        r = self.editar(self.cliente, telefono="3003334444")
        self.assertIn("Ya existe un usuario con ese teléfono.", mensajes(r))
        r = self.editar(self.cliente, telefono="12ab")
        self.assertIn("El teléfono debe tener solo números (7 a 15 dígitos).", mensajes(r))

    def test_correo_invalido_y_rol_invalido(self):
        r = self.editar(self.cliente, correo="no-es-un-correo")
        self.assertIn("El correo no es válido.", mensajes(r))
        r = self.editar(self.cliente, rol="SUPERMAN")
        self.assertIn("El rol no es válido.", mensajes(r))

    def test_el_administrador_no_puede_cambiar_su_propio_rol(self):
        r = self.editar(self.admin, rol="CLIENTE")
        self.assertIn("No puedes cambiar tu propio rol.", mensajes(r))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, Rol.ADMINISTRADOR)

    def test_usuario_inexistente(self):
        r = self.client.get(reverse("panel_admin:editar_usuario", args=[9999]))
        self.assertEqual(r.status_code, 404)


class HistorialTests(AdminBase):
    def test_muestra_la_actividad_del_usuario(self):
        self.trabajador.estado_verificacion = EstadoVerificacion.APROBADO
        self.trabajador.save()
        s = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Arreglar fuga", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly", precio_ofertado=100000,
        )
        servicios_solicitud.aceptar(s.id, self.trabajador)
        Pago.objects.create(
            solicitud=s, cliente=self.cliente, trabajador=self.trabajador, monto_total=100000,
            comision=3000, neto_trabajador=97000, estado=Pago.Estado.COMPLETADO,
            fecha_pago=timezone.now(),
        )
        ReporteSeguridad.objects.create(reportante=self.cliente, reportado=self.trabajador, motivo="Llegó tarde")

        r_cli = self.client.get(reverse("panel_admin:historial", args=[self.cliente.id]))
        self.assertContains(r_cli, "Solicitó: Arreglar fuga")
        self.assertContains(r_cli, "Pagó $100000")
        self.assertContains(r_cli, "Realizó un reporte: Llegó tarde")

        r_trab = self.client.get(reverse("panel_admin:historial", args=[self.trabajador.id]))
        self.assertContains(r_trab, "Atendió: Arreglar fuga")
        self.assertContains(r_trab, "Recibió $97000")
        self.assertContains(r_trab, "Recibió un reporte: Llegó tarde")

    def test_el_orden_es_del_mas_reciente_al_mas_antiguo_y_sin_fecha_al_final(self):
        ahora = timezone.now()
        s1 = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Vieja", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly",
        )
        s2 = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion="Nueva", categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly",
        )
        from solicitudes.models import Solicitud
        Solicitud.objects.filter(pk=s1.pk).update(fecha_creacion=ahora - timedelta(days=5))
        Solicitud.objects.filter(pk=s2.pk).update(fecha_creacion=ahora - timedelta(days=1))
        Pago.objects.create(
            solicitud=s1, cliente=self.cliente, trabajador=self.trabajador, monto_total=1,
            comision=0, neto_trabajador=1, estado=Pago.Estado.FALLIDO, fecha_pago=None,
        )
        detalles = [a["detalle"] for a in servicios.historial_actividad(self.cliente)]
        self.assertTrue(detalles[0].startswith("Solicitó: Nueva"))
        self.assertTrue(detalles[1].startswith("Solicitó: Vieja"))
        self.assertTrue(detalles[2].startswith("Pagó"))

    def test_sin_actividad(self):
        r = self.client.get(reverse("panel_admin:historial", args=[self.cliente.id]))
        self.assertContains(r, "Sin actividad registrada.")

    def test_usuario_inexistente(self):
        self.assertEqual(self.client.get(reverse("panel_admin:historial", args=[9999])).status_code, 404)


class ServiciosTests(AdminBase):
    def test_errores_de_negocio_son_ErrorAdmin(self):
        with self.assertRaises(ErrorAdmin):
            servicios.aprobar_trabajador(9999)
        with self.assertRaises(ErrorAdmin):
            servicios.bloquear(self.admin.id, self.admin)