import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from anuncios.models import Anuncio
from pagos.models import Pago
from seguridad.models import ReporteSeguridad
from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud
from usuarios.models import Rol, Usuario

from . import estadisticas
from .servicios import ErrorAdmin

PASSWORD = "Clave1234"


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, PASSWORD, nombre=correo.split("@")[0], rol=rol, **extra
    )


def en_bogota(dia, hora=12):
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class EstadisticasBase(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.admin = Usuario.objects.create_superuser("adm@example.com", PASSWORD, nombre="Adm")
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario("trab@example.com", Rol.TRABAJADOR)
        self.aliado = crear_usuario("aliado@example.com", Rol.ALIADO_COMERCIAL)

        # Fechas de registro distintas para probar los filtros de usuarios.
        Usuario.objects.filter(pk=self.admin.pk).update(
            fecha_registro=en_bogota(self.hoy - timedelta(days=100))
        )
        Usuario.objects.filter(pk=self.cliente.pk).update(
            fecha_registro=en_bogota(self.hoy - timedelta(days=60))
        )
        Usuario.objects.filter(pk=self.trabajador.pk).update(
            fecha_registro=en_bogota(self.hoy - timedelta(days=30))
        )
        Usuario.objects.filter(pk=self.aliado.pk).update(
            fecha_registro=en_bogota(self.hoy - timedelta(days=10))
        )

        self.client.force_login(self.admin)

    # ---------- Ayudas para crear datos ----------
    def crear_solicitud(self, estado=EstadoSolicitud.PENDIENTE, fecha=None,
                        descripcion="Arreglar fuga", trabajador=None, precio="100000.00"):
        return Solicitud.objects.create(
            cliente=self.cliente,
            trabajador=trabajador,
            estado=estado,
            descripcion=descripcion,
            categoria=CategoriaServicio.PLOMERIA,
            zona="Norte",
            localidad="Chapinero",
            barrio="Marly",
            precio_ofertado=Decimal(precio),
            fecha_creacion=fecha or timezone.now(),
        )

    def crear_pago(self, solicitud, monto="100000.00", comision="3000.00",
                   estado=Pago.Estado.COMPLETADO, fecha=None):
        return Pago.objects.create(
            solicitud=solicitud,
            cliente=solicitud.cliente,
            trabajador=solicitud.trabajador or self.trabajador,
            monto_total=Decimal(monto),
            comision=Decimal(comision),
            neto_trabajador=Decimal(monto) - Decimal(comision),
            estado=estado,
            fecha_pago=fecha,
        )


class CalculoTests(EstadisticasBase):
    def setUp(self):
        super().setUp()
        self.completada = self.crear_solicitud(
            estado=EstadoSolicitud.COMPLETADA,
            fecha=en_bogota(self.hoy - timedelta(days=2)),
            descripcion="Instalar lavaplatos",
            trabajador=self.trabajador,
        )
        self.pendiente = self.crear_solicitud(
            estado=EstadoSolicitud.PENDIENTE,
            fecha=en_bogota(self.hoy - timedelta(days=1)),
            descripcion="Revisar toma",
        )
        self.aceptada = self.crear_solicitud(
            estado=EstadoSolicitud.ACEPTADA,
            fecha=en_bogota(self.hoy - timedelta(days=40)),
            descripcion="Cambiar interruptor",
            trabajador=self.trabajador,
            precio="50000.00",
        )
        self.pago_ok = self.crear_pago(
            self.completada, fecha=en_bogota(self.hoy - timedelta(days=1))
        )
        self.pago_fallido = self.crear_pago(
            self.aceptada, monto="50000.00", comision="1500.00",
            estado=Pago.Estado.FALLIDO, fecha=en_bogota(self.hoy - timedelta(days=40)),
        )
        Anuncio.objects.create(
            aliado=self.aliado, titulo="Ferretería", descripcion="Tornillos",
            estado=Anuncio.Estado.PENDIENTE,
            fecha_creacion=en_bogota(self.hoy - timedelta(days=3)),
        )
        Anuncio.objects.create(
            aliado=self.aliado, titulo="Pinturas", descripcion="Vinilo",
            estado=Anuncio.Estado.PUBLICADO,
            fecha_creacion=en_bogota(self.hoy - timedelta(days=4)),
        )
        ReporteSeguridad.objects.create(
            reportante=self.cliente, reportado=self.trabajador, motivo="Llegó tarde",
            estado=ReporteSeguridad.Estado.EN_REVISION,
            fecha=en_bogota(self.hoy - timedelta(days=2)),
        )
        ReporteSeguridad.objects.create(
            reportante=self.cliente, reportado=self.trabajador, motivo="Otro",
            estado=ReporteSeguridad.Estado.DESCARTADO,
            fecha=en_bogota(self.hoy - timedelta(days=3)),
        )

    def test_indicadores_generales(self):
        reporte = estadisticas.armar_reporte()
        self.assertEqual(reporte.total_usuarios, 4)
        self.assertEqual(reporte.clientes, 1)
        self.assertEqual(reporte.trabajadores, 1)
        self.assertEqual(reporte.aliados, 1)
        self.assertEqual(reporte.usuarios_por_rol, {
            "Clientes": 1, "Trabajadores": 1, "Aliados": 1,
        })

        self.assertEqual(reporte.total_solicitudes, 3)
        self.assertEqual(reporte.conteo_solicitudes["pendiente"], 1)
        self.assertEqual(reporte.conteo_solicitudes["aceptada"], 1)
        self.assertEqual(reporte.conteo_solicitudes["completada"], 1)
        self.assertEqual(reporte.conteo_solicitudes["rechazada"], 0)
        self.assertEqual(reporte.conteo_solicitudes["cancelada"], 0)
        self.assertEqual(reporte.conteo_solicitudes["no_atendida"], 0)

        self.assertEqual(reporte.total_pagos_completados, 1)
        self.assertEqual(reporte.ingresos_brutos, Decimal("100000.00"))
        self.assertEqual(reporte.comision_total, Decimal("3000.00"))

        self.assertEqual(reporte.anuncios_pendientes, 1)
        self.assertEqual(reporte.reportes_en_revision, 1)

    def test_filtro_por_rol_no_cambia_las_solicitudes(self):
        reporte = estadisticas.armar_reporte(rol=Rol.CLIENTE)
        self.assertEqual(reporte.total_usuarios, 1)
        self.assertEqual(reporte.clientes, 1)
        self.assertEqual(reporte.trabajadores, 0)
        self.assertEqual(reporte.aliados, 0)
        self.assertEqual(reporte.usuarios_por_rol, {"Clientes": 1})
        # En Java el rol filtra usuarios, no solicitudes ni pagos.
        self.assertEqual(reporte.total_solicitudes, 3)

    def test_filtro_por_estado_de_solicitud(self):
        reporte = estadisticas.armar_reporte(estado_solicitud=EstadoSolicitud.ACEPTADA)
        self.assertEqual(reporte.total_solicitudes, 1)
        self.assertEqual(reporte.solicitudes[0].id, self.aceptada.id)
        self.assertEqual(reporte.conteo_solicitudes["aceptada"], 1)
        self.assertEqual(reporte.conteo_solicitudes["pendiente"], 0)
        self.assertEqual(reporte.conteo_solicitudes["completada"], 0)
        # Los pagos no se filtran por el estado de la solicitud.
        self.assertEqual(reporte.total_pagos_completados, 1)

    def test_filtro_por_estado_de_pago_usa_ese_estado(self):
        reporte = estadisticas.armar_reporte(estado_pago=Pago.Estado.FALLIDO)
        self.assertEqual(reporte.total_pagos_completados, 1)
        self.assertEqual(reporte.ingresos_brutos, Decimal("50000.00"))
        self.assertEqual(reporte.comision_total, Decimal("1500.00"))
        self.assertEqual(reporte.pagos[0].id, self.pago_fallido.id)

    def test_los_filtros_invalidos_se_ignoran(self):
        reporte = estadisticas.armar_reporte(
            rol="SUPERMAN", estado_solicitud="LOQUESEA", estado_pago="NOEXISTE"
        )
        self.assertIsNone(reporte.rol)
        self.assertIsNone(reporte.estado_solicitud)
        self.assertIsNone(reporte.estado_pago)
        self.assertEqual(reporte.total_usuarios, 4)
        self.assertEqual(reporte.total_solicitudes, 3)
        self.assertEqual(reporte.total_pagos_completados, 1)

    def test_filtro_por_fechas_en_cada_tabla(self):
        desde = self.hoy - timedelta(days=3)
        hasta = self.hoy
        reporte = estadisticas.armar_reporte(desde=desde, hasta=hasta)

        # Ningún usuario se registró en esos días.
        self.assertEqual(reporte.total_usuarios, 0)
        # Dos solicitudes creadas en el rango.
        self.assertEqual(reporte.total_solicitudes, 2)
        # Un pago completado (el fallido es de hace 40 días).
        self.assertEqual(reporte.total_pagos_completados, 1)
        self.assertEqual(reporte.anuncios_pendientes, 1)
        self.assertEqual(reporte.reportes_en_revision, 1)

    def test_filtro_por_fechas_deja_fuera_lo_viejo(self):
        reporte = estadisticas.armar_reporte(
            desde=self.hoy - timedelta(days=50),
            hasta=self.hoy - timedelta(days=35),
        )
        self.assertEqual(reporte.total_solicitudes, 1)
        self.assertEqual(reporte.solicitudes[0].id, self.aceptada.id)
        # Sin filtro de estado solo cuentan los pagos completados.
        self.assertEqual(reporte.total_pagos_completados, 0)
        self.assertEqual(reporte.ingresos_brutos, Decimal("0.00"))
        self.assertEqual(reporte.anuncios_pendientes, 0)
        self.assertEqual(reporte.reportes_en_revision, 0)

    def test_serie_mensual_ordenada_y_con_sumas(self):
        enero = self.crear_solicitud(
            estado=EstadoSolicitud.COMPLETADA, fecha=en_bogota(date(2025, 1, 15)),
            descripcion="Enero", trabajador=self.trabajador,
        )
        febrero = self.crear_solicitud(
            estado=EstadoSolicitud.COMPLETADA, fecha=en_bogota(date(2025, 2, 10)),
            descripcion="Febrero", trabajador=self.trabajador,
        )
        self.crear_pago(enero, fecha=en_bogota(date(2025, 1, 20)))
        self.crear_pago(
            febrero, monto="50000.00", comision="1500.00",
            fecha=en_bogota(date(2025, 2, 12)),
        )

        reporte = estadisticas.armar_reporte(
            desde=date(2025, 1, 1), hasta=date(2025, 2, 28)
        )

        self.assertEqual(reporte.labels_meses, ["2025-01", "2025-02"])
        self.assertEqual(reporte.solicitudes_por_mes, {"2025-01": 1, "2025-02": 1})
        self.assertEqual(reporte.ingresos_por_mes, {
            "2025-01": Decimal("100000.00"),
            "2025-02": Decimal("50000.00"),
        })
        self.assertEqual(reporte.serie_mensual, [
            {"mes": "2025-01", "solicitudes": 1, "ingresos": Decimal("100000.00")},
            {"mes": "2025-02", "solicitudes": 1, "ingresos": Decimal("50000.00")},
        ])

    def test_un_pago_sin_fecha_suma_pero_no_entra_en_la_serie_mensual(self):
        sin_fecha = self.crear_solicitud(
            estado=EstadoSolicitud.COMPLETADA,
            fecha=en_bogota(self.hoy - timedelta(days=1)),
            descripcion="Sin fecha de pago",
            trabajador=self.trabajador,
        )
        self.crear_pago(sin_fecha, fecha=None)

        reporte = estadisticas.armar_reporte()
        self.assertEqual(reporte.total_pagos_completados, 2)
        self.assertEqual(reporte.ingresos_brutos, Decimal("200000.00"))
        # La serie mensual solo cuenta pagos con fecha.
        self.assertNotIn(
            "None", reporte.ingresos_por_mes
        )


class RangosTests(EstadisticasBase):
    def test_fecha_primer_registro(self):
        self.assertEqual(
            estadisticas.fecha_primer_registro(),
            self.hoy - timedelta(days=100),
        )

    def test_normalizar_rango_ajusta_al_rango_permitido(self):
        inicio = self.hoy - timedelta(days=100)
        self.assertEqual(estadisticas.normalizar_rango(None, None, inicio, self.hoy), (None, None))
        self.assertEqual(
            estadisticas.normalizar_rango(
                inicio - timedelta(days=10), self.hoy + timedelta(days=10), inicio, self.hoy
            ),
            (inicio, self.hoy),
        )

    def test_normalizar_rango_rechaza_fechas_al_reves(self):
        inicio = self.hoy - timedelta(days=100)
        with self.assertRaisesRegex(ErrorAdmin, "no puede ser posterior"):
            estadisticas.normalizar_rango(
                self.hoy, self.hoy - timedelta(days=5), inicio, self.hoy
            )

    def test_etiquetas_del_reporte(self):
        self.assertEqual(estadisticas.etiqueta_periodo(None, None), "Toda la historia")
        self.assertEqual(
            estadisticas.etiqueta_periodo(date(2026, 1, 1), date(2026, 1, 31)),
            "01/01/2026 al 31/01/2026",
        )
        self.assertEqual(estadisticas.etiqueta_rol(None), "Todos")
        self.assertEqual(estadisticas.etiqueta_rol("ALIADO_COMERCIAL"), "ALIADO COMERCIAL")
        self.assertEqual(estadisticas.etiqueta_solicitud(None), "Todas")
        self.assertEqual(
            estadisticas.etiqueta_solicitud(EstadoSolicitud.NO_ATENDIDA), "No atendidas"
        )
        self.assertIn("pagos completados", estadisticas.etiqueta_pago(None))


class VistaTests(EstadisticasBase):
    def setUp(self):
        super().setUp()
        self.completada = self.crear_solicitud(
            estado=EstadoSolicitud.COMPLETADA,
            fecha=en_bogota(self.hoy - timedelta(days=2)),
            descripcion="Instalar lavaplatos",
            trabajador=self.trabajador,
        )
        self.pendiente = self.crear_solicitud(
            estado=EstadoSolicitud.PENDIENTE,
            fecha=en_bogota(self.hoy - timedelta(days=1)),
            descripcion="Revisar toma",
        )
        self.crear_pago(self.completada, fecha=en_bogota(self.hoy - timedelta(days=1)))

    def test_solo_el_administrador_entra(self):
        for usuario in (self.cliente, self.trabajador, self.aliado):
            self.client.force_login(usuario)
            self.assertEqual(
                self.client.get(reverse("panel_admin:estadisticas")).status_code, 403
            )
            self.assertEqual(
                self.client.get(
                    reverse("panel_admin:exportar_estadisticas", args=["pdf"])
                ).status_code,
                403,
            )

    def test_sin_sesion_va_al_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("panel_admin:estadisticas"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_la_pantalla_muestra_tarjetas_y_graficas(self):
        respuesta = self.client.get(reverse("panel_admin:estadisticas"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Reportes y estadísticas de operación")
        self.assertContains(respuesta, "Usuarios totales")
        self.assertContains(respuesta, "Solicitudes completadas")
        self.assertContains(respuesta, "Ingresos brutos")
        self.assertContains(respuesta, "Solicitudes e ingresos por mes")
        self.assertContains(respuesta, "chartSolicitudes")
        self.assertContains(respuesta, "chartLine")
        self.assertContains(respuesta, "Detalle del reporte")

    def test_la_pantalla_incluye_los_enlaces_de_descarga(self):
        respuesta = self.client.get(reverse("panel_admin:estadisticas"))
        self.assertContains(
            respuesta, reverse("panel_admin:exportar_estadisticas", args=["pdf"])
        )
        self.assertContains(
            respuesta, reverse("panel_admin:exportar_estadisticas", args=["excel"])
        )

    def test_el_enlace_aparece_en_la_barra_del_administrador(self):
        respuesta = self.client.get(reverse("panel_admin:usuarios"))
        self.assertContains(respuesta, reverse("panel_admin:estadisticas"))

    def test_filtros_llegan_al_contexto_y_a_los_enlaces(self):
        respuesta = self.client.get(reverse("panel_admin:estadisticas"), {
            "rol": "CLIENTE",
            "estado_solicitud": "COMPLETADA",
            "estado_pago": "COMPLETADO",
            "desde": (self.hoy - timedelta(days=5)).isoformat(),
            "hasta": self.hoy.isoformat(),
        })
        self.assertEqual(respuesta.status_code, 200)
        reporte = respuesta.context["reporte"]
        self.assertEqual(reporte.rol, "CLIENTE")
        self.assertEqual(reporte.estado_solicitud, "COMPLETADA")
        self.assertEqual(reporte.estado_pago, "COMPLETADO")
        self.assertContains(respuesta, "rol=CLIENTE")
        self.assertContains(respuesta, "estado_solicitud=COMPLETADA")

    def test_una_fecha_futura_se_ajusta_a_hoy(self):
        respuesta = self.client.get(reverse("panel_admin:estadisticas"), {
            "hasta": (self.hoy + timedelta(days=30)).isoformat(),
        })
        self.assertEqual(respuesta.context["reporte"].hasta, self.hoy)

    def test_rango_invertido_vuelve_a_la_pantalla_con_un_aviso(self):
        respuesta = self.client.get(reverse("panel_admin:estadisticas"), {
            "desde": self.hoy.isoformat(),
            "hasta": (self.hoy - timedelta(days=10)).isoformat(),
        })
        self.assertRedirects(respuesta, reverse("panel_admin:estadisticas"))
        self.assertTrue(any("no puede ser posterior" in m for m in mensajes(respuesta)))

    def test_exportar_pdf(self):
        respuesta = self.client.get(
            reverse("panel_admin:exportar_estadisticas", args=["pdf"])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn(
            f"estadisticas_{self.hoy.isoformat()}.pdf", respuesta["Content-Disposition"]
        )
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_exportar_excel(self):
        respuesta = self.client.get(
            reverse("panel_admin:exportar_estadisticas", args=["excel"])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("spreadsheetml", respuesta["Content-Type"])
        self.assertIn(
            f"estadisticas_{self.hoy.isoformat()}.xlsx", respuesta["Content-Disposition"]
        )

        libro = load_workbook(io.BytesIO(respuesta.content))
        self.assertEqual(libro.sheetnames, ["Resumen", "Detalle solicitudes"])

        resumen = libro["Resumen"]
        self.assertEqual(resumen["A1"].value, "Cambell")
        textos = [resumen.cell(row=f, column=1).value for f in range(1, resumen.max_row + 1)]
        self.assertIn("INDICADORES", textos)
        self.assertIn("SOLICITUDES POR ESTADO", textos)
        self.assertIn("USUARIOS POR ROL", textos)
        self.assertIn("SOLICITUDES E INGRESOS POR MES", textos)

        detalle = libro["Detalle solicitudes"]
        self.assertEqual(detalle.cell(row=4, column=1).value, "Id")
        self.assertEqual(detalle.cell(row=4, column=3).value, "Descripción")
        descripciones = [
            detalle.cell(row=f, column=3).value
            for f in range(5, detalle.max_row + 1)
        ]
        self.assertIn("Instalar lavaplatos", descripciones)
        self.assertIn("Revisar toma", descripciones)

    def test_el_excel_respeta_el_filtro_de_estado(self):
        respuesta = self.client.get(
            reverse("panel_admin:exportar_estadisticas", args=["excel"]),
            {"estado_solicitud": "COMPLETADA"},
        )
        detalle = load_workbook(io.BytesIO(respuesta.content))["Detalle solicitudes"]
        descripciones = [
            detalle.cell(row=f, column=3).value
            for f in range(5, detalle.max_row + 1)
        ]
        self.assertEqual(descripciones, ["Instalar lavaplatos"])

    def test_exportar_con_rango_invertido_avisa_y_vuelve(self):
        respuesta = self.client.get(
            reverse("panel_admin:exportar_estadisticas", args=["pdf"]),
            {
                "desde": self.hoy.isoformat(),
                "hasta": (self.hoy - timedelta(days=10)).isoformat(),
            },
        )
        self.assertRedirects(respuesta, reverse("panel_admin:estadisticas"))
        self.assertTrue(any("no puede ser posterior" in m for m in mensajes(respuesta)))

    def test_si_falla_la_generacion_se_avisa_sin_romper(self):
        with mock.patch(
            "panel_admin.estadisticas.generar_excel", side_effect=RuntimeError("falló")
        ), self.assertLogs("panel_admin.views", level="ERROR"):
            respuesta = self.client.get(
                reverse("panel_admin:exportar_estadisticas", args=["excel"])
            )
        self.assertRedirects(respuesta, reverse("panel_admin:estadisticas"))
        self.assertIn(
            "No se pudo generar el reporte. Inténtalo de nuevo.", mensajes(respuesta)
        )

    def test_reporte_vacio_se_puede_exportar(self):
        Solicitud.objects.all().delete()
        Pago.objects.all().delete()
        for formato in ("pdf", "excel"):
            respuesta = self.client.get(
                reverse("panel_admin:exportar_estadisticas", args=[formato])
            )
            self.assertEqual(respuesta.status_code, 200)
