"""Pruebas de la Fase 1D: los 9 trabajos programados.

Equivale a TareasProgramadasService.java. Cada prueba prepara solo los datos que
necesita el trabajo y revisa que el resultado y las notificaciones sean los
esperados.
"""
import os
import shutil
import tempfile
from datetime import time, timedelta
from decimal import Decimal
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from mensajeria.models import Notificacion
from pagos.models import Pago, Suscripcion
from seguridad.models import ReporteSeguridad
from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud
from usuarios.models import (
    Archivo,
    CoberturaTrabajador,
    EstadoVerificacion,
    Rol,
    Usuario,
)

from .trabajos import (
    avisar_suscripciones_por_vencer,
    avisar_vencimiento_documentos,
    cerrar_solicitudes_no_atendidas,
    limpiar_archivos_obsoletos,
    reasignar_solicitudes_sin_respuesta,
    recordar_calificaciones,
    renovar_suscripciones,
    suspender_cuentas_con_reportes,
    transferir_pagos_netos,
)

MEDIA_TEMPORAL = tempfile.mkdtemp()


def crear_usuario(correo, rol=Rol.CLIENTE, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def crear_trabajador(correo, **extra):
    return crear_usuario(
        correo,
        Rol.TRABAJADOR,
        estado_verificacion=EstadoVerificacion.APROBADO,
        **extra,
    )


def crear_solicitud(cliente, trabajador=None, **extra):
    datos = {
        "descripcion": "Arreglar una fuga",
        "categoria": CategoriaServicio.PLOMERIA,
        "localidad": "Chapinero",
        "barrio": "Marly",
        "precio_ofertado": 50000,
        "trabajador": trabajador,
    }
    datos.update(extra)
    return Solicitud.objects.create(cliente=cliente, **datos)


def crear_cobertura(trabajador):
    """Cobertura de día completo: los avisos usan la hora real del sistema."""
    return CoberturaTrabajador.objects.create(
        trabajador=trabajador,
        radio_km=10,
        localidades=["Chapinero"],
        categorias=[CategoriaServicio.PLOMERIA],
        hora_inicio=time(0, 0),
        hora_fin=time(23, 59),
    )


class ReasignacionTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com")
        self.trabajador = crear_trabajador("trabajador@example.com")
        crear_cobertura(self.trabajador)

    def test_reasigna_las_pendientes_antiguas(self):
        solicitud = crear_solicitud(
            self.cliente, fecha_creacion=timezone.now() - timedelta(hours=2)
        )

        resultado = reasignar_solicitudes_sin_respuesta()

        solicitud.refresh_from_db()
        self.assertEqual(resultado, {"revisadas": 1, "reasignadas": 1})
        self.assertIsNotNone(solicitud.fecha_ultima_reasignacion)
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.trabajador, tipo="ASIGNACION", solicitud=solicitud
            ).exists()
        )

    def test_no_toca_las_pendientes_recientes(self):
        solicitud = crear_solicitud(self.cliente, fecha_creacion=timezone.now())

        resultado = reasignar_solicitudes_sin_respuesta()

        solicitud.refresh_from_db()
        self.assertEqual(resultado["reasignadas"], 0)
        self.assertIsNone(solicitud.fecha_ultima_reasignacion)


class NoAtendidasTests(TestCase):
    def test_cierra_las_pendientes_de_mas_de_24_horas(self):
        cliente = crear_usuario("cliente@example.com")
        vieja = crear_solicitud(
            cliente, fecha_creacion=timezone.now() - timedelta(hours=25)
        )
        reciente = crear_solicitud(cliente, fecha_creacion=timezone.now())

        resultado = cerrar_solicitudes_no_atendidas()

        vieja.refresh_from_db()
        reciente.refresh_from_db()
        self.assertEqual(resultado, {"cerradas": 1})
        self.assertEqual(vieja.estado, EstadoSolicitud.NO_ATENDIDA)
        self.assertEqual(reciente.estado, EstadoSolicitud.PENDIENTE)
        self.assertTrue(
            Notificacion.objects.filter(usuario=cliente, tipo="SOLICITUD").exists()
        )


class DocumentosTests(TestCase):
    def test_avisa_vencidos_y_por_vencer(self):
        hoy = timezone.localdate()
        vencido = crear_trabajador(
            "vencido@example.com", fecha_vencimiento_documento=hoy - timedelta(days=1)
        )
        por_vencer = crear_trabajador(
            "porvencer@example.com", fecha_vencimiento_documento=hoy + timedelta(days=10)
        )
        al_dia = crear_trabajador(
            "aldia@example.com", fecha_vencimiento_documento=hoy + timedelta(days=90)
        )

        resultado = avisar_vencimiento_documentos()

        self.assertEqual(resultado, {"vencidos": 1, "por_vencer": 1})
        self.assertEqual(vencido.notificaciones.filter(tipo="DOCUMENTO").count(), 1)
        self.assertEqual(por_vencer.notificaciones.filter(tipo="DOCUMENTO").count(), 1)
        self.assertFalse(al_dia.notificaciones.exists())


class ReportesTests(TestCase):
    def test_suspende_al_superar_el_umbral_y_avisa_a_los_admins(self):
        reportante = crear_usuario("reportante@example.com")
        reportado = crear_trabajador("reportado@example.com")
        admin = crear_usuario("admin@example.com", Rol.ADMINISTRADOR)

        for _ in range(3):
            ReporteSeguridad.objects.create(
                reportante=reportante,
                reportado=reportado,
                motivo="Mala conducta",
                estado=ReporteSeguridad.Estado.EN_REVISION,
            )

        resultado = suspender_cuentas_con_reportes()

        reportado.refresh_from_db()
        self.assertEqual(resultado, {"suspendidas": 1})
        self.assertTrue(reportado.bloqueado)
        self.assertTrue(
            reportado.notificaciones.filter(tipo="SEGURIDAD").exists()
        )
        self.assertTrue(admin.notificaciones.filter(tipo="SEGURIDAD").exists())

    def test_no_suspende_por_debajo_del_umbral(self):
        reportante = crear_usuario("reportante@example.com")
        reportado = crear_trabajador("reportado@example.com")
        ReporteSeguridad.objects.create(
            reportante=reportante, reportado=reportado, motivo="Una queja"
        )

        resultado = suspender_cuentas_con_reportes()

        reportado.refresh_from_db()
        self.assertEqual(resultado, {"suspendidas": 0})
        self.assertFalse(reportado.bloqueado)


class CalificacionesTests(TestCase):
    def test_recuerda_solo_las_completadas_sin_calificar(self):
        cliente = crear_usuario("cliente@example.com")
        trabajador = crear_trabajador("trabajador@example.com")

        pendiente = crear_solicitud(
            cliente,
            trabajador,
            estado=EstadoSolicitud.COMPLETADA,
            fecha_finalizacion=timezone.now() - timedelta(days=3),
        )
        calificada = crear_solicitud(
            cliente,
            trabajador,
            estado=EstadoSolicitud.COMPLETADA,
            fecha_finalizacion=timezone.now() - timedelta(days=3),
            calificacion=5,
        )
        reciente = crear_solicitud(
            cliente,
            trabajador,
            estado=EstadoSolicitud.COMPLETADA,
            fecha_finalizacion=timezone.now(),
        )

        resultado = recordar_calificaciones()

        self.assertEqual(resultado, {"recordados": 1})
        self.assertEqual(
            Notificacion.objects.filter(
                usuario=cliente, tipo="CALIFICACION", solicitud=pendiente
            ).count(),
            1,
        )
        self.assertFalse(
            Notificacion.objects.filter(solicitud__in=[calificada, reciente]).exists()
        )


class SuscripcionesTests(TestCase):
    def setUp(self):
        self.trabajador = crear_trabajador("premium@example.com")

    def test_renueva_las_vencidas_con_renovacion_automatica(self):
        suscripcion = Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            renovacion_automatica=True,
            fecha_vencimiento=timezone.now() - timedelta(days=1),
        )

        resultado = renovar_suscripciones()

        suscripcion.refresh_from_db()
        self.assertEqual(resultado["renovadas"], 1)
        self.assertGreater(suscripcion.fecha_vencimiento, timezone.now())
        self.assertTrue(
            self.trabajador.notificaciones.filter(tipo="SUSCRIPCION").exists()
        )

    @override_settings(PROBABILIDAD_PAGO_APROBADO=0.0)
    def test_si_el_cobro_falla_avisa_y_no_renueva(self):
        vencimiento = timezone.now() - timedelta(days=1)
        suscripcion = Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            renovacion_automatica=True,
            fecha_vencimiento=vencimiento,
        )

        resultado = renovar_suscripciones()

        suscripcion.refresh_from_db()
        self.assertEqual(resultado["rechazadas"], 1)
        self.assertEqual(suscripcion.fecha_vencimiento, vencimiento)
        self.assertTrue(
            self.trabajador.notificaciones.filter(tipo="SUSCRIPCION").exists()
        )

    def test_no_renueva_si_la_renovacion_esta_apagada(self):
        Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            renovacion_automatica=False,
            fecha_vencimiento=timezone.now() - timedelta(days=1),
        )

        self.assertEqual(renovar_suscripciones()["vencidas"], 0)

    def test_avisa_las_que_vencen_pronto(self):
        proxima = Suscripcion.objects.create(
            trabajador=self.trabajador,
            activa=True,
            fecha_vencimiento=timezone.now() + timedelta(days=5),
        )
        lejana = crear_trabajador("lejana@example.com")
        Suscripcion.objects.create(
            trabajador=lejana,
            activa=True,
            fecha_vencimiento=timezone.now() + timedelta(days=30),
        )

        resultado = avisar_suscripciones_por_vencer()

        self.assertEqual(resultado, {"avisadas": 1})
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.trabajador, tipo="SUSCRIPCION"
            ).exists()
        )
        self.assertFalse(lejana.notificaciones.exists())


class TransferenciasTests(TestCase):
    def test_transfiere_los_netos_pendientes(self):
        cliente = crear_usuario("cliente@example.com")
        trabajador = crear_trabajador("trabajador@example.com")

        bueno = Pago.objects.create(
            solicitud=crear_solicitud(cliente, trabajador),
            cliente=cliente,
            trabajador=trabajador,
            monto_total=Decimal("100000"),
            comision=Decimal("3000"),
            neto_trabajador=Decimal("97000"),
            estado=Pago.Estado.COMPLETADO,
        )
        sin_neto = Pago.objects.create(
            solicitud=crear_solicitud(cliente, trabajador),
            cliente=cliente,
            trabajador=trabajador,
            monto_total=Decimal("0"),
            neto_trabajador=Decimal("0"),
            estado=Pago.Estado.COMPLETADO,
        )

        resultado = transferir_pagos_netos()

        bueno.refresh_from_db()
        sin_neto.refresh_from_db()
        self.assertEqual(resultado, {"revisados": 2, "transferidos": 1, "fallidos": 1})
        self.assertEqual(
            bueno.estado_transferencia, Pago.EstadoTransferencia.TRANSFERIDO
        )
        self.assertIsNotNone(bueno.fecha_transferencia)
        self.assertEqual(
            sin_neto.estado_transferencia, Pago.EstadoTransferencia.FALLIDO
        )

    def test_no_toca_los_pagos_que_no_estan_completados(self):
        cliente = crear_usuario("cliente@example.com")
        trabajador = crear_trabajador("trabajador@example.com")
        pago = Pago.objects.create(
            solicitud=crear_solicitud(cliente, trabajador),
            cliente=cliente,
            trabajador=trabajador,
            monto_total=Decimal("100000"),
            neto_trabajador=Decimal("97000"),
            estado=Pago.Estado.PENDIENTE,
        )

        resultado = transferir_pagos_netos()

        pago.refresh_from_db()
        self.assertEqual(resultado["revisados"], 0)
        self.assertEqual(pago.estado_transferencia, Pago.EstadoTransferencia.PENDIENTE)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class LimpiezaDeArchivosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def crear_archivo(self, trabajador, vigente=True):
        return Archivo.objects.create(
            propietario=trabajador,
            tipo=Archivo.Tipo.DOCUMENTO,
            archivo=SimpleUploadedFile(
                "documento.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * 32,
                content_type="image/png",
            ),
            vigente=vigente,
        )

    def test_borra_el_archivo_fisico_pero_conserva_el_registro(self):
        trabajador = crear_trabajador("trabajador@example.com")
        archivo = self.crear_archivo(trabajador, vigente=False)
        ruta = archivo.archivo.path
        self.assertTrue(os.path.exists(ruta))

        resultado = limpiar_archivos_obsoletos()

        self.assertEqual(resultado, {"borrados": 1})
        self.assertFalse(os.path.exists(ruta))
        self.assertTrue(Archivo.objects.filter(pk=archivo.pk).exists())

    def test_nunca_borra_un_archivo_que_usa_el_perfil(self):
        trabajador = crear_trabajador("trabajador@example.com")
        archivo = self.crear_archivo(trabajador, vigente=False)
        ruta = archivo.archivo.path

        trabajador.documento = archivo.archivo.name
        trabajador.save(update_fields=["documento"])

        resultado = limpiar_archivos_obsoletos()

        self.assertEqual(resultado, {"borrados": 0})
        self.assertTrue(os.path.exists(ruta))

    def test_no_borra_los_archivos_vigentes_y_recientes(self):
        trabajador = crear_trabajador("trabajador@example.com")
        archivo = self.crear_archivo(trabajador, vigente=True)

        resultado = limpiar_archivos_obsoletos()

        self.assertEqual(resultado, {"borrados": 0})
        self.assertTrue(os.path.exists(archivo.archivo.path))


class ComandoTests(TestCase):
    def test_lista_las_tareas_disponibles(self):
        salida = StringIO()
        call_command("tareas_programadas", "--listar", stdout=salida)
        texto = salida.getvalue()
        for nombre in (
            "reasignar",
            "cerrar-no-atendidas",
            "avisar-documentos",
            "suspender-reportadas",
            "recordar-calificaciones",
            "renovar-suscripciones",
            "avisar-suscripciones",
            "transferir-pagos",
            "limpiar-archivos",
        ):
            self.assertIn(nombre, texto)

    def test_ejecuta_todas_las_tareas(self):
        salida = StringIO()
        call_command("tareas_programadas", stdout=salida)
        self.assertIn("Reasignar solicitudes sin respuesta", salida.getvalue())

    def test_ejecuta_una_sola_tarea(self):
        salida = StringIO()
        call_command(
            "tareas_programadas", "--tarea", "transferir-pagos", stdout=salida
        )
        self.assertIn("Transferir pagos a trabajadores", salida.getvalue())
        self.assertNotIn("Reasignar solicitudes", salida.getvalue())
