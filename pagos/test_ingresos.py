import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from solicitudes import servicios as servicios_solicitud
from solicitudes.models import CategoriaServicio
from usuarios.models import EstadoVerificacion, Rol, Usuario

from . import cobros, ingresos
from .models import Pago
from .servicios import ErrorPago


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


def en_bogota(dia, hora=0, minuto=0):
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


class IngresosBase(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cli@example.com", Rol.CLIENTE)
        self.trabajador = crear_usuario(
            "trab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        self.otro_trabajador = crear_usuario(
            "otrotrab@example.com", Rol.TRABAJADOR, estado_verificacion=EstadoVerificacion.APROBADO
        )
        # Registrado hace más de un año, para poder probar rangos de fechas.
        Usuario.objects.filter(pk=self.trabajador.pk).update(
            fecha_registro=timezone.now() - timedelta(days=400)
        )
        self.trabajador.refresh_from_db()
        self.hoy = timezone.localdate()

    def pago(self, monto, fecha, estado=Pago.Estado.COMPLETADO, trabajador=None, descripcion="Servicio"):
        trabajador = trabajador or self.trabajador
        monto = Decimal(monto)
        solicitud = servicios_solicitud.crear_solicitud(
            self.cliente, descripcion=descripcion, categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero", barrio="Marly", precio_ofertado=monto,
        )
        comision, neto = cobros.calcular_comision(monto)
        return Pago.objects.create(
            solicitud=solicitud, cliente=self.cliente, trabajador=trabajador,
            monto_total=monto, comision=comision, neto_trabajador=neto,
            estado=estado, fecha_pago=fecha,
        )


class IngresosFuncionesTests(IngresosBase):
    def test_el_total_suma_solo_los_pagos_completados(self):
        ahora = timezone.now()
        self.pago("100000", ahora)                                          # neto 97000.00
        self.pago("27070", ahora)                                           # neto 26257.90
        self.pago("50000", ahora, estado=Pago.Estado.REEMBOLSADO)           # no cuenta
        self.pago("40000", ahora, estado=Pago.Estado.FALLIDO)               # no cuenta
        self.pago("90000", ahora, trabajador=self.otro_trabajador)          # de otro trabajador
        self.assertEqual(ingresos.ingresos_trabajador(self.trabajador), Decimal("123257.90"))

    def test_sin_pagos_el_total_es_cero(self):
        self.assertEqual(ingresos.ingresos_trabajador(self.trabajador), Decimal("0.00"))

    def test_el_historial_incluye_todos_los_estados_del_mas_reciente_al_mas_antiguo(self):
        ahora = timezone.now()
        viejo = self.pago("10000", ahora - timedelta(days=2))
        nuevo = self.pago("20000", ahora, estado=Pago.Estado.FALLIDO)
        self.pago("30000", ahora, trabajador=self.otro_trabajador)
        self.assertEqual(list(ingresos.historial_trabajador(self.trabajador)), [nuevo, viejo])

    def test_rango_de_fechas_incluye_el_dia_completo(self):
        base = self.hoy - timedelta(days=30)
        a = self.pago("10000", en_bogota(base, 23, 30))                       # último minuto del día
        b = self.pago("20000", en_bogota(base + timedelta(days=1), 0, 0))     # primer minuto del siguiente
        c = self.pago("30000", en_bogota(base - timedelta(days=1), 12, 0))
        self.pago("40000", en_bogota(base, 10, 0), estado=Pago.Estado.FALLIDO)

        def en(desde, hasta):
            return list(ingresos.pagos_en_rango(self.trabajador, desde, hasta))

        self.assertEqual(en(base, base), [a])
        self.assertEqual(en(base, base + timedelta(days=1)), [b, a])
        self.assertEqual(en(None, base - timedelta(days=1)), [c])
        self.assertEqual(en(base + timedelta(days=1), None), [b])
        self.assertEqual(en(None, None), [b, a, c])

    def test_normalizar_rango(self):
        inicio, hoy = date(2026, 1, 1), date(2026, 6, 1)
        self.assertEqual(ingresos.normalizar_rango(date(2025, 1, 1), date(2027, 1, 1), inicio, hoy), (inicio, hoy))
        self.assertEqual(ingresos.normalizar_rango(date(2026, 3, 1), None, inicio, hoy), (date(2026, 3, 1), None))
        self.assertEqual(ingresos.normalizar_rango(date(2027, 1, 1), None, inicio, hoy), (hoy, None))
        self.assertEqual(ingresos.normalizar_rango(None, date(2025, 1, 1), inicio, hoy), (None, inicio))
        with self.assertRaisesMessage(ErrorPago, "no puede ser posterior"):
            ingresos.normalizar_rango(date(2026, 5, 1), date(2026, 3, 1), inicio, hoy)

    def test_rango_permitido_empieza_el_dia_del_registro(self):
        inicio, fin = ingresos.rango_permitido(self.trabajador)
        self.assertEqual(inicio, self.hoy - timedelta(days=400))
        self.assertEqual(fin, self.hoy)

    @override_settings(COMISION_PLATAFORMA=0.035)
    def test_porcentaje_con_decimales(self):
        self.assertEqual(cobros.porcentaje_comision(), "3.5")


class IngresosVistaTests(IngresosBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.trabajador)

    def exportar(self, **parametros):
        return self.client.get(reverse("pagos:exportar_ingresos"), parametros)

    def test_la_pantalla_muestra_el_total_y_solo_mis_pagos(self):
        ahora = timezone.now()
        self.pago("100000", ahora, descripcion="Trabajo mio")
        self.pago("90000", ahora, descripcion="Trabajo ajeno", trabajador=self.otro_trabajador)
        r = self.client.get(reverse("pagos:ingresos"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Trabajo mio")
        self.assertNotContains(r, "Trabajo ajeno")
        self.assertContains(r, "Total neto acumulado (tras comisión del 3%)")
        self.assertContains(r, "Descargar PDF")
        self.assertContains(r, "Descargar Excel")
        self.assertContains(r, "Descargar CSV")

    def test_un_pago_no_completado_no_suma(self):
        self.pago("40000", timezone.now(), estado=Pago.Estado.FALLIDO, descripcion="Fallido")
        r = self.client.get(reverse("pagos:ingresos"))
        self.assertContains(r, "no suma a tus ingresos")

    def test_sin_pagos(self):
        r = self.client.get(reverse("pagos:ingresos"))
        self.assertContains(r, "Aún no tienes pagos recibidos.")

    def test_un_cliente_no_entra(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("pagos:ingresos")).status_code, 403)
        self.assertEqual(self.exportar().status_code, 403)

    def test_sin_sesion_va_al_login(self):
        self.client.logout()
        r = self.client.get(reverse("pagos:ingresos"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("usuarios:login"), r["Location"])

    def test_el_enlace_aparece_en_la_barra_del_trabajador(self):
        r = self.client.get(reverse("solicitudes:disponibles"))
        self.assertContains(r, reverse("pagos:ingresos"))

    # ---------- Exportar ----------
    def test_exportar_csv(self):
        ahora = timezone.now()
        self.pago("100000", ahora, descripcion="Cambiar llave")
        self.pago("27070", ahora, descripcion="Arreglar fuga")
        r = self.exportar(formato="csv")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/csv"))
        self.assertIn(f'reporte_ingresos_{self.hoy.isoformat()}.csv', r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"\xef\xbb\xbf"))  # BOM para Excel en Windows
        texto = r.content.decode("utf-8-sig")
        self.assertIn("Reporte de ingresos - trab", texto)
        self.assertIn("Cambiar llave", texto)
        self.assertIn("Total neto,,,,,123257.90", texto)

    def test_el_csv_respeta_el_rango_de_fechas(self):
        base = self.hoy - timedelta(days=60)
        self.pago("100000", en_bogota(base, 12), descripcion="Dentro del rango")
        self.pago("50000", en_bogota(base - timedelta(days=10), 12), descripcion="Fuera del rango")
        r = self.exportar(formato="csv", desde=base.isoformat(), hasta=base.isoformat())
        texto = r.content.decode("utf-8-sig")
        self.assertIn("Dentro del rango", texto)
        self.assertNotIn("Fuera del rango", texto)
        self.assertIn("Total neto,,,,,97000.00", texto)

    def test_el_csv_no_incluye_pagos_de_otros_ni_no_completados(self):
        ahora = timezone.now()
        self.pago("100000", ahora, descripcion="Mio")
        self.pago("50000", ahora, descripcion="Ajeno", trabajador=self.otro_trabajador)
        self.pago("40000", ahora, estado=Pago.Estado.REEMBOLSADO, descripcion="Reembolsado")
        texto = self.exportar(formato="csv").content.decode("utf-8-sig")
        self.assertIn("Mio", texto)
        self.assertNotIn("Ajeno", texto)
        self.assertNotIn("Reembolsado", texto)

    def test_exportar_excel(self):
        ahora = timezone.now()
        self.pago("100000", ahora, descripcion="Cambiar llave")
        self.pago("27070", ahora, descripcion="Arreglar fuga")
        r = self.exportar(formato="excel")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn(".xlsx", r["Content-Disposition"])

        hoja = load_workbook(io.BytesIO(r.content)).active
        filas = {hoja.cell(row=i, column=1).value: i for i in range(1, hoja.max_row + 1)}
        self.assertEqual(hoja["A1"].value, "Cambell")
        self.assertIn("Fecha", filas)
        total = hoja.cell(row=filas["Total neto"], column=6).value
        self.assertAlmostEqual(float(total), 123257.90, places=2)

    def test_exportar_pdf(self):
        self.pago("100000", timezone.now(), descripcion="Cambiar llave")
        r = self.exportar(formato="pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn(".pdf", r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_un_formato_desconocido_descarga_csv(self):
        r = self.exportar(formato="loquesea")
        self.assertTrue(r["Content-Type"].startswith("text/csv"))
        r = self.exportar()
        self.assertTrue(r["Content-Type"].startswith("text/csv"))

    def test_reporte_vacio(self):
        for formato in ("csv", "excel", "pdf"):
            self.assertEqual(self.exportar(formato=formato).status_code, 200)

    def test_rango_invertido_vuelve_a_la_pantalla_con_un_aviso(self):
        desde = (self.hoy - timedelta(days=10)).isoformat()
        hasta = (self.hoy - timedelta(days=20)).isoformat()
        r = self.exportar(formato="csv", desde=desde, hasta=hasta)
        self.assertRedirects(r, reverse("pagos:ingresos"))
        self.assertTrue(any("no puede ser posterior" in m for m in mensajes(r)))

    def test_una_fecha_futura_se_ajusta_a_hoy(self):
        futuro = (self.hoy + timedelta(days=30)).isoformat()
        texto = self.exportar(formato="csv", hasta=futuro).content.decode("utf-8-sig")
        self.assertIn(self.hoy.strftime("%d/%m/%Y"), texto)

    def test_fechas_con_texto_se_ignoran(self):
        r = self.exportar(formato="csv", desde="ayer", hasta="mañana")
        self.assertEqual(r.status_code, 200)

    def test_si_falla_la_generacion_se_avisa_sin_romper(self):
        with mock.patch("pagos.reportes.generar_csv", side_effect=RuntimeError("falló")):
            r = self.exportar(formato="csv")
        self.assertRedirects(r, reverse("pagos:ingresos"))
        self.assertIn("No se pudo generar el reporte. Inténtalo de nuevo.", mensajes(r))