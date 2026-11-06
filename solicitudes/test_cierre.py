import shutil
import tempfile

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from mensajeria.models import Notificacion
from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import servicios
from .models import CategoriaServicio, EstadoSolicitud

MEDIA_TEMPORAL = tempfile.mkdtemp()


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def foto(nombre="trabajo.png", tipo="image/png"):
    return SimpleUploadedFile(nombre, b"\x89PNG\r\n\x1a\n" + b"0" * 64, content_type=tipo)


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class CierreBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.otro = crear_usuario(
            "otro@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.solicitud = servicios.crear_solicitud(
            self.cliente, descripcion="Cambiar llave del baño",
            categoria=CategoriaServicio.PLOMERIA, localidad="Chapinero", barrio="Marly",
        )
        servicios.aceptar(self.solicitud.id, self.trabajador)
        self.codigo = self.solicitud.codigo_finalizacion

    def finalizar(self, usuario, **datos):
        self.client.force_login(usuario)
        return self.client.post(reverse("solicitudes:finalizar", args=[self.solicitud.id]), datos)

    def completar(self):
        servicios.finalizar_con_evidencia(self.solicitud.id, "evidencias/foto.png")


class FinalizarTests(CierreBase):
    def test_finalizar_con_codigo_y_foto(self):
        r = self.finalizar(self.trabajador, codigo=self.codigo, evidencia=foto())
        self.assertRedirects(r, reverse("solicitudes:finalizado", args=[self.solicitud.id]))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.COMPLETADA)
        self.assertTrue(self.solicitud.evidencia.name.startswith("evidencias/"))
        self.assertIsNotNone(self.solicitud.fecha_finalizacion)
        self.assertTrue(
            Notificacion.objects.filter(usuario=self.cliente, mensaje__contains="completado").exists()
        )

    def test_el_codigo_no_distingue_mayusculas(self):
        r = self.finalizar(self.trabajador, codigo=self.codigo.lower(), evidencia=foto())
        self.assertEqual(r.status_code, 302)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.COMPLETADA)

    def test_codigo_incorrecto(self):
        r = self.finalizar(self.trabajador, codigo="ZZZZZZ", evidencia=foto())
        self.assertIn("El código de finalización ingresado es incorrecto.", mensajes(r))
        self.assertRedirects(r, reverse("solicitudes:mis_trabajos"))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.ACEPTADA)

    def test_sin_codigo(self):
        r = self.finalizar(self.trabajador, codigo="  ", evidencia=foto())
        self.assertIn("Debes ingresar el código de finalización.", mensajes(r))

    def test_sin_foto(self):
        r = self.finalizar(self.trabajador, codigo=self.codigo)
        self.assertIn("Debes adjuntar una foto del trabajo terminado.", mensajes(r))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.ACEPTADA)

    def test_archivo_con_extension_no_permitida(self):
        malo = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        r = self.finalizar(self.trabajador, codigo=self.codigo, evidencia=malo)
        self.assertEqual(len(mensajes(r)), 1)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.ACEPTADA)

    def test_archivo_demasiado_grande(self):
        grande = SimpleUploadedFile("grande.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png")
        r = self.finalizar(self.trabajador, codigo=self.codigo, evidencia=grande)
        self.assertIn("La foto no puede superar los 5 MB.", mensajes(r))

    def test_otro_trabajador_no_puede_finalizar(self):
        r = self.finalizar(self.otro, codigo=self.codigo, evidencia=foto())
        self.assertIn("Este trabajo no está asignado a ti.", mensajes(r))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, EstadoSolicitud.ACEPTADA)

    def test_no_se_puede_finalizar_dos_veces(self):
        self.completar()
        r = self.finalizar(self.trabajador, codigo=self.codigo, evidencia=foto())
        self.assertIn("Este trabajo ya no está en curso.", mensajes(r))

    def test_finalizar_exige_post(self):
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("solicitudes:finalizar", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 405)

    def test_un_cliente_no_puede_finalizar(self):
        r = self.finalizar(self.cliente, codigo=self.codigo, evidencia=foto())
        self.assertEqual(r.status_code, 403)

    def test_mis_trabajos_muestra_el_formulario_de_finalizar(self):
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("solicitudes:mis_trabajos"))
        self.assertContains(r, "Finalizar trabajo")
        self.assertContains(r, 'name="evidencia"')

    def test_pagina_de_trabajo_finalizado(self):
        self.completar()
        self.client.force_login(self.trabajador)
        r = self.client.get(reverse("solicitudes:finalizado", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Trabajo finalizado")
        self.assertContains(r, "Espera por el pago del cliente")

    def test_la_pagina_de_finalizado_no_existe_para_otro_trabajador(self):
        self.completar()
        self.client.force_login(self.otro)
        r = self.client.get(reverse("solicitudes:finalizado", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 404)


class CalificarTests(CierreBase):
    def calificar(self, **datos):
        self.client.force_login(self.cliente)
        return self.client.post(reverse("solicitudes:calificar", args=[self.solicitud.id]), datos)

    def test_el_formulario_aparece_solo_en_servicios_completados_sin_calificar(self):
        self.client.force_login(self.cliente)
        url = reverse("solicitudes:mis_solicitudes")
        self.assertNotContains(self.client.get(url), "Califica este servicio")

        self.completar()
        self.assertContains(self.client.get(url), "Califica este servicio")

        self.calificar(puntuacion="5", comentario="Excelente")
        self.assertNotContains(self.client.get(url), "Califica este servicio")

    def test_calificar_recalcula_el_promedio_del_trabajador(self):
        self.completar()
        r = self.calificar(puntuacion="4", comentario="Muy bien")
        self.assertRedirects(r, reverse("solicitudes:mis_solicitudes"))
        self.assertIn("Gracias por calificar el servicio.", mensajes(r))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.calificacion, 4)
        self.assertEqual(self.solicitud.comentario, "Muy bien")
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.calificacion_promedio, 4.0)
        self.assertEqual(self.trabajador.total_calificaciones, 1)

    def test_no_se_puede_calificar_dos_veces(self):
        self.completar()
        self.calificar(puntuacion="5")
        r = self.calificar(puntuacion="1")
        self.assertIn("Este servicio ya fue calificado.", mensajes(r))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.calificacion, 5)

    def test_puntuacion_invalida(self):
        self.completar()
        for valor in ("abc", "", "0", "6"):
            r = self.calificar(puntuacion=valor)
            self.assertIn("La calificación debe estar entre 1 y 5 estrellas.", mensajes(r))
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.calificacion)

    def test_solo_se_califica_un_servicio_completado(self):
        r = self.calificar(puntuacion="5")
        self.assertIn("Solo puedes calificar servicios que ya estén completados.", mensajes(r))

    def test_otro_cliente_no_puede_calificar(self):
        self.completar()
        intruso = crear_usuario("intruso@example.com", Rol.CLIENTE)
        self.client.force_login(intruso)
        r = self.client.post(
            reverse("solicitudes:calificar", args=[self.solicitud.id]), {"puntuacion": "1"}
        )
        self.assertIn("Solo el cliente que solicitó el servicio puede calificarlo.", mensajes(r))

    def test_un_trabajador_no_puede_calificar(self):
        self.completar()
        self.client.force_login(self.trabajador)
        r = self.client.post(
            reverse("solicitudes:calificar", args=[self.solicitud.id]), {"puntuacion": "5"}
        )
        self.assertEqual(r.status_code, 403)

    def test_calificar_exige_post(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("solicitudes:calificar", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 405)


class PerfilTrabajadorTests(CierreBase):
    def test_el_cliente_ve_el_perfil_de_su_trabajador(self):
        self.completar()
        servicios.calificar(self.solicitud.id, 5, "", self.cliente)
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("solicitudes:perfil_trabajador", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<span>trab</span>")
        self.assertContains(r, "★")
        self.assertNotContains(r, "Sin calificaciones aún")
        self.assertContains(r, "1 servicios")

    def test_trabajador_sin_calificaciones(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("solicitudes:perfil_trabajador", args=[self.solicitud.id]))
        self.assertContains(r, "Sin calificaciones aún")

    def test_otro_cliente_no_ve_el_perfil(self):
        intruso = crear_usuario("intruso@example.com", Rol.CLIENTE)
        self.client.force_login(intruso)
        r = self.client.get(reverse("solicitudes:perfil_trabajador", args=[self.solicitud.id]))
        self.assertEqual(r.status_code, 404)

    def test_el_enlace_al_perfil_aparece_en_mis_solicitudes(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("solicitudes:mis_solicitudes"))
        self.assertContains(r, "(ver perfil)")