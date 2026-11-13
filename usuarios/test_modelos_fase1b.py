"""Pruebas de los modelos agregados en la Fase 1B.

Cubre Horario (disponibilidad semanal), Archivo (registro de archivos
sensibles) y Verificacion (expediente de identidad).
"""
import hashlib
import shutil
import tempfile
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Archivo, EstadoVerificacion, Horario, Rol, Usuario, Verificacion

PASSWORD = "Clave1234"
MEDIA_TEMPORAL = tempfile.mkdtemp()


def crear_trabajador(correo="trab@example.com", telefono="3001112233"):
    return Usuario.objects.create_user(
        correo,
        PASSWORD,
        nombre="Trabajador de Prueba",
        rol=Rol.TRABAJADOR,
        estado_verificacion=EstadoVerificacion.PENDIENTE,
        telefono=telefono,
    )


class HorarioTests(TestCase):
    def test_cubre_el_dia_y_la_hora(self):
        trabajador = crear_trabajador()
        horario = Horario.objects.create(
            trabajador=trabajador,
            dia_semana=Horario.Dia.LUNES,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
        )

        # 16 de noviembre de 2026 es lunes.
        lunes_9 = timezone.make_aware(datetime(2026, 11, 16, 9, 0))
        lunes_13 = timezone.make_aware(datetime(2026, 11, 16, 13, 0))
        martes_9 = timezone.make_aware(datetime(2026, 11, 17, 9, 0))

        self.assertTrue(horario.cubre(lunes_9))
        self.assertFalse(horario.cubre(lunes_13))
        self.assertFalse(horario.cubre(martes_9))

    def test_horario_inactivo_no_cubre(self):
        trabajador = crear_trabajador()
        horario = Horario.objects.create(
            trabajador=trabajador,
            dia_semana=Horario.Dia.LUNES,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
            activo=False,
        )
        lunes_9 = timezone.make_aware(datetime(2026, 11, 16, 9, 0))
        self.assertFalse(horario.cubre(lunes_9))

    def test_rechaza_hora_fin_anterior_al_inicio(self):
        trabajador = crear_trabajador()
        horario = Horario(
            trabajador=trabajador,
            dia_semana=Horario.Dia.MARTES,
            hora_inicio=time(18, 0),
            hora_fin=time(8, 0),
        )
        with self.assertRaises(ValidationError):
            horario.full_clean()

    def test_no_permite_bloque_duplicado(self):
        trabajador = crear_trabajador()
        datos = {
            "trabajador": trabajador,
            "dia_semana": Horario.Dia.MIERCOLES,
            "hora_inicio": time(8, 0),
            "hora_fin": time(18, 0),
        }
        Horario.objects.create(**datos)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Horario.objects.create(**datos)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class ArchivoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def test_completa_nombre_tamano_y_hash(self):
        trabajador = crear_trabajador()
        contenido = b"documento de prueba con contenido"
        subido = SimpleUploadedFile(
            "documento.pdf", contenido, content_type="application/pdf"
        )

        archivo = Archivo.objects.create(
            propietario=trabajador,
            tipo=Archivo.Tipo.DOCUMENTO,
            archivo=subido,
        )

        self.assertEqual(archivo.nombre_original, "documento.pdf")
        self.assertEqual(archivo.tamano_bytes, len(contenido))
        self.assertEqual(archivo.hash_sha256, hashlib.sha256(contenido).hexdigest())
        self.assertEqual(archivo.version, 1)
        self.assertTrue(archivo.vigente)
        self.assertFalse(archivo.cifrado)

    def test_calcular_hash_devuelve_el_mismo_valor(self):
        trabajador = crear_trabajador()
        subido = SimpleUploadedFile("selfie.png", b"imagen-demo", content_type="image/png")
        archivo = Archivo.objects.create(
            propietario=trabajador,
            tipo=Archivo.Tipo.SELFIE,
            archivo=subido,
        )
        self.assertEqual(archivo.calcular_hash(), archivo.hash_sha256)
        self.assertTrue(archivo.archivo.name.startswith("archivos/"))


class VerificacionTests(TestCase):
    def test_estado_inicial_y_propiedad_aprobada(self):
        trabajador = crear_trabajador()
        verificacion = Verificacion.objects.create(trabajador=trabajador)

        self.assertEqual(verificacion.estado, Verificacion.Estado.PENDIENTE)
        self.assertEqual(verificacion.origen, Verificacion.Origen.AUTOMATICA)
        self.assertFalse(verificacion.aprobada)

        verificacion.estado = Verificacion.Estado.APROBADA
        self.assertTrue(verificacion.aprobada)

    def test_guarda_resultado_y_revisor(self):
        trabajador = crear_trabajador()
        admin = Usuario.objects.create_user(
            "admin@example.com",
            PASSWORD,
            nombre="Administrador",
            rol=Rol.ADMINISTRADOR,
            estado_verificacion=EstadoVerificacion.APROBADO,
        )
        verificacion = Verificacion.objects.create(
            trabajador=trabajador,
            estado=Verificacion.Estado.REVISION_MANUAL,
            origen=Verificacion.Origen.MANUAL,
            porcentaje_coincidencia=72.5,
            revisor=admin,
            motivo="La foto no es clara.",
        )

        self.assertEqual(verificacion.porcentaje_coincidencia, 72.5)
        self.assertEqual(verificacion.revisor, admin)
        self.assertFalse(verificacion.aprobada)

    def test_porcentaje_fuera_de_rango_no_es_valido(self):
        trabajador = crear_trabajador()
        verificacion = Verificacion(
            trabajador=trabajador,
            porcentaje_coincidencia=120,
        )
        with self.assertRaises(ValidationError):
            verificacion.full_clean()

    def test_orden_por_fecha_mas_reciente(self):
        trabajador = crear_trabajador()
        vieja = Verificacion.objects.create(
            trabajador=trabajador,
            fecha_creacion=timezone.now() - timedelta(days=1),
        )
        nueva = Verificacion.objects.create(trabajador=trabajador)

        self.assertEqual(list(trabajador.verificaciones.all()), [nueva, vieja])
