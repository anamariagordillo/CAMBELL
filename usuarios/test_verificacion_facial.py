"""Pruebas de la Fase 1D: patrón Strategy y verificación de identidad.

La estrategia manual es la que se usa cuando no hay credenciales de Face++; la
de Face++ se prueba con una respuesta simulada para no llamar a internet.
"""
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .estrategias_verificacion import (
    EstrategiaVerificacion,
    VerificacionFacePlusPlus,
    VerificacionManual,
    estrategia_actual,
)
from .models import Archivo, EstadoVerificacion, Rol, Usuario, Verificacion
from .verificacion_facial import (
    evaluar_automatica,
    evaluar_y_registrar,
    registrar_archivo,
)

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()


def imagen(nombre="foto.png"):
    return SimpleUploadedFile(
        nombre, b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png"
    )


def crear_trabajador(correo, con_archivos=False, **extra):
    trabajador = Usuario.objects.create_user(
        correo,
        PASSWORD,
        nombre=correo.split("@")[0],
        rol=Rol.TRABAJADOR,
        numero_documento=extra.pop("numero_documento", "1012345678"),
        **extra,
    )
    if con_archivos:
        trabajador.documento = imagen("documento.png")
        trabajador.selfie = imagen("selfie.png")
        trabajador.save(update_fields=["documento", "selfie"])
    return trabajador


class EstrategiaFija(EstrategiaVerificacion):
    """Estrategia de prueba: devuelve el porcentaje que se le indique."""

    automatica = True

    def __init__(self, valor):
        self.valor = valor

    def verificar(self, ruta_documento, ruta_selfie):
        return self.valor


class SeleccionDeEstrategiaTests(TestCase):
    @override_settings(FACEPP_API_KEY="", FACEPP_API_SECRET="")
    def test_sin_credenciales_se_usa_la_manual(self):
        self.assertIsInstance(estrategia_actual(), VerificacionManual)

    @override_settings(FACEPP_API_KEY="clave", FACEPP_API_SECRET="secreto")
    def test_con_credenciales_se_usa_face_plus_plus(self):
        estrategia = estrategia_actual()
        self.assertIsInstance(estrategia, VerificacionFacePlusPlus)
        self.assertTrue(estrategia.automatica)

    def test_la_manual_nunca_compara(self):
        self.assertEqual(VerificacionManual().verificar("a.png", "b.png"), -1.0)

    @mock.patch.object(VerificacionFacePlusPlus, "_comparar")
    def test_face_plus_plus_devuelve_la_confianza(self, comparar):
        comparar.return_value = {"confidence": 88.5}
        estrategia = VerificacionFacePlusPlus("clave", "secreto")
        self.assertEqual(estrategia.verificar("doc.png", "selfie.png"), 88.5)

    @mock.patch.object(VerificacionFacePlusPlus, "_comparar")
    def test_face_plus_plus_sin_confidence_devuelve_menos_uno(self, comparar):
        comparar.return_value = {"error_message": "sin rostro"}
        self.assertEqual(
            VerificacionFacePlusPlus("clave", "secreto").verificar("a", "b"), -1.0
        )

    @mock.patch.object(
        VerificacionFacePlusPlus, "_comparar", side_effect=OSError("sin red")
    )
    def test_face_plus_plus_sin_red_no_rompe(self, _comparar):
        self.assertEqual(
            VerificacionFacePlusPlus("clave", "secreto").verificar("a", "b"), -1.0
        )


@override_settings(UMBRAL_VERIFICACION_FACIAL=75)
class EvaluacionAutomaticaTests(TestCase):
    def test_sin_numero_de_documento_queda_pendiente(self):
        resultado = evaluar_automatica("a.png", "b.png", numero_documento="")
        self.assertEqual(resultado.estado, EstadoVerificacion.PENDIENTE)

    def test_estrategia_manual_queda_para_revision(self):
        resultado = evaluar_automatica(
            "a.png", "b.png", "1012345678", estrategia=VerificacionManual()
        )
        self.assertEqual(resultado.estado, EstadoVerificacion.PENDIENTE)
        self.assertIn("revisión manual", resultado.motivo)

    def test_similitud_sobre_el_umbral_aprueba(self):
        resultado = evaluar_automatica(
            "a.png", "b.png", "1012345678", estrategia=EstrategiaFija(90)
        )
        self.assertEqual(resultado.estado, EstadoVerificacion.APROBADO)
        self.assertEqual(resultado.confianza, 90)

    def test_similitud_justo_en_el_umbral_aprueba(self):
        resultado = evaluar_automatica(
            "a.png", "b.png", "1012345678", estrategia=EstrategiaFija(75)
        )
        self.assertEqual(resultado.estado, EstadoVerificacion.APROBADO)

    def test_similitud_bajo_el_umbral_queda_pendiente(self):
        resultado = evaluar_automatica(
            "a.png", "b.png", "1012345678", estrategia=EstrategiaFija(60)
        )
        self.assertEqual(resultado.estado, EstadoVerificacion.PENDIENTE)
        self.assertIn("60.0%", resultado.motivo)

    def test_servicio_sin_respuesta_no_rechaza(self):
        resultado = evaluar_automatica(
            "a.png", "b.png", "1012345678", estrategia=EstrategiaFija(-1)
        )
        self.assertEqual(resultado.estado, EstadoVerificacion.PENDIENTE)
        self.assertIn("no pudo completarse", resultado.motivo)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class RegistroDeVerificacionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def test_sin_documento_ni_selfie_no_hace_nada(self):
        trabajador = crear_trabajador("sindocs@example.com")
        self.assertIsNone(evaluar_y_registrar(trabajador))
        self.assertFalse(Verificacion.objects.exists())

    def test_evaluar_y_registrar_guarda_estado_y_expediente(self):
        trabajador = crear_trabajador("trabajador@example.com", con_archivos=True)
        verificacion = evaluar_y_registrar(trabajador)

        trabajador.refresh_from_db()
        self.assertEqual(trabajador.estado_verificacion, EstadoVerificacion.PENDIENTE)
        self.assertEqual(verificacion.estado, Verificacion.Estado.PENDIENTE)
        self.assertEqual(verificacion.origen, Verificacion.Origen.MANUAL)
        self.assertIsNotNone(verificacion.documento)
        self.assertIsNotNone(verificacion.selfie)
        self.assertEqual(
            Archivo.objects.filter(propietario=trabajador, vigente=True).count(), 2
        )

    def test_una_estrategia_automatica_aprueba_y_guarda_el_porcentaje(self):
        trabajador = crear_trabajador("auto@example.com", con_archivos=True)
        verificacion = evaluar_y_registrar(
            trabajador, estrategia=EstrategiaFija(92.4)
        )

        trabajador.refresh_from_db()
        self.assertEqual(trabajador.estado_verificacion, EstadoVerificacion.APROBADO)
        self.assertEqual(verificacion.origen, Verificacion.Origen.AUTOMATICA)
        self.assertEqual(verificacion.estado, Verificacion.Estado.APROBADA)
        self.assertEqual(verificacion.porcentaje_coincidencia, 92.4)
        self.assertIsNotNone(verificacion.fecha_decision)

    def test_un_nuevo_intento_desmarca_los_archivos_anteriores(self):
        trabajador = crear_trabajador("version@example.com", con_archivos=True)
        evaluar_y_registrar(trabajador)

        registrar_archivo(
            trabajador, Archivo.Tipo.DOCUMENTO, trabajador.documento.name
        )
        self.assertEqual(
            Archivo.objects.filter(
                propietario=trabajador,
                tipo=Archivo.Tipo.DOCUMENTO,
                vigente=True,
            ).count(),
            1,
        )
        self.assertEqual(
            Archivo.objects.filter(
                propietario=trabajador,
                tipo=Archivo.Tipo.DOCUMENTO,
                vigente=False,
            ).count(),
            1,
        )


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class VerificacionEnElRegistroTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def datos_trabajador(self):
        return {
            "nombre": "Luis Gomez",
            "correo": "luis@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "rol": "TRABAJADOR",
            "telefono": "3109876543",
            "localidad": "Suba",
            "oficio": "Plomería",
            "anios_experiencia": "5",
            "cuenta_bancaria": "Banco Demo Ahorros 000111",
            "numero_documento": "1012345678",
            "documento": imagen("doc.png"),
            "selfie": imagen("selfie.png"),
            "acepta_terminos": "true",
            "acepta_datos": "true",
        }

    @mock.patch("usuarios.verificacion_facial.evaluar_y_registrar")
    def test_el_registro_de_trabajador_dispara_la_evaluacion(self, evaluar):
        r = self.client.post(reverse("usuarios:registro"), self.datos_trabajador())
        self.assertRedirects(r, reverse("usuarios:login"))
        evaluar.assert_called_once()
        self.assertEqual(evaluar.call_args.args[0].correo, "luis@example.com")

    def test_el_registro_deja_el_expediente_manual(self):
        self.client.post(reverse("usuarios:registro"), self.datos_trabajador())
        trabajador = Usuario.objects.get(correo="luis@example.com")
        self.assertEqual(
            trabajador.estado_verificacion, EstadoVerificacion.PENDIENTE
        )
        verificacion = Verificacion.objects.get(trabajador=trabajador)
        self.assertEqual(verificacion.origen, Verificacion.Origen.MANUAL)
        self.assertEqual(
            Archivo.objects.filter(propietario=trabajador, vigente=True).count(), 2
        )


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class ReintentoConEstrategiaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    @mock.patch(
        "usuarios.verificacion_facial.estrategia_actual",
        return_value=EstrategiaFija(99),
    )
    def test_reintento_puede_aprobarse_automaticamente(self, _estrategia):
        trabajador = crear_trabajador("reintento@example.com")
        trabajador.estado_verificacion = EstadoVerificacion.RECHAZADO
        trabajador.save(update_fields=["estado_verificacion"])

        self.client.force_login(trabajador)
        r = self.client.post(
            reverse("verificacion:reintentar"),
            {"documento": imagen("documento.png"), "selfie": imagen("selfie.png")},
        )
        self.assertRedirects(r, reverse("solicitudes:disponibles"))

        trabajador.refresh_from_db()
        self.assertEqual(trabajador.estado_verificacion, EstadoVerificacion.APROBADO)
        verificacion = Verificacion.objects.get(trabajador=trabajador)
        self.assertEqual(verificacion.estado, Verificacion.Estado.APROBADA)
        self.assertEqual(verificacion.porcentaje_coincidencia, 99.0)
