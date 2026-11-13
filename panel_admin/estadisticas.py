"""Reporte multicriterio global y estadísticas del administrador.

Replica `AdminService.armarReporte()` y `ReporteEstadisticasService.java`:
los filtros (rol, estado de solicitud, estado de pago y rango de fechas) se
combinan entre sí para recalcular los indicadores, la serie mensual y las
exportaciones en PDF y Excel.

Nota sobre los pagos: igual que en Java, si NO se filtra por estado de pago
solo se usan los pagos COMPLETADOS para ingresos y comisión. Si se filtra por
un estado, se usan los pagos de ese estado (aunque no estén completados).
"""
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from anuncios.models import Anuncio
from pagos.models import Pago
from seguridad.models import ReporteSeguridad
from solicitudes.models import EstadoSolicitud, Solicitud
from usuarios.models import Rol, Usuario

from .servicios import ErrorAdmin

CENTAVOS = Decimal("0.01")
MARCA = "Cambell"
SLOGAN = "Conectamos el talento de tu barrio, con seguridad"
NARANJA_HEX = "FF6B00"
NARANJA = colors.HexColor("#FF6B00")
TEXTO = colors.HexColor("#1A1A1A")
GRIS = colors.HexColor("#6B6B6B")

# Etiquetas en plural que usa el reporte de Java para la gráfica y el PDF.
ETIQUETAS_ESTADO = {
    EstadoSolicitud.PENDIENTE: "Pendientes",
    EstadoSolicitud.ACEPTADA: "Aceptadas",
    EstadoSolicitud.RECHAZADA: "Rechazadas",
    EstadoSolicitud.COMPLETADA: "Completadas",
    EstadoSolicitud.CANCELADA: "Canceladas",
    EstadoSolicitud.NO_ATENDIDA: "No atendidas",
}

COLUMNAS_DETALLE = [
    "Id", "Estado", "Descripción", "Zona", "Localidad", "Barrio",
    "Cliente", "Trabajador", "Precio ofertado", "Fecha creación", "Fecha finalización",
]


@dataclass
class ReporteEstadisticas:
    """Todo lo que necesitan la pantalla y las exportaciones."""

    rol: str = None
    estado_solicitud: str = None
    estado_pago: str = None
    desde: date = None
    hasta: date = None

    total_usuarios: int = 0
    clientes: int = 0
    trabajadores: int = 0
    aliados: int = 0
    usuarios_por_rol: dict = field(default_factory=dict)

    total_solicitudes: int = 0
    conteo_solicitudes: dict = field(default_factory=dict)
    solicitudes_por_estado: dict = field(default_factory=dict)
    solicitudes: list = field(default_factory=list)

    total_pagos_completados: int = 0
    ingresos_brutos: Decimal = Decimal("0")
    comision_total: Decimal = Decimal("0")
    pagos: list = field(default_factory=list)

    anuncios_pendientes: int = 0
    reportes_en_revision: int = 0

    labels_meses: list = field(default_factory=list)
    solicitudes_por_mes: dict = field(default_factory=dict)
    ingresos_por_mes: dict = field(default_factory=dict)
    serie_mensual: list = field(default_factory=list)


# ------------------------------------------------------------------ Fechas
def _inicio_del_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def _dinero(valor):
    """Redondea a centavos, como Math.round(... * 100) / 100 en Java."""
    return (valor or Decimal("0")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _dinero_texto(valor):
    return f"{_dinero(valor):,.2f}"


def _texto(valor):
    return str(valor if valor is not None else 0)


def fecha_primer_registro():
    """Día del usuario más antiguo; si no hay usuarios, hoy."""
    primera = (
        Usuario.objects.order_by("fecha_registro")
        .values_list("fecha_registro", flat=True)
        .first()
    )
    return timezone.localtime(primera).date() if primera else timezone.localdate()


def normalizar_rango(desde, hasta, inicio, hoy):
    """Ajusta las fechas al rango permitido y rechaza un rango al revés."""
    if desde and desde < inicio:
        desde = inicio
    if desde and desde > hoy:
        desde = hoy
    if hasta and hasta > hoy:
        hasta = hoy
    if hasta and hasta < inicio:
        hasta = inicio
    if desde and hasta and desde > hasta:
        raise ErrorAdmin(
            "El rango de fechas es inválido: la fecha 'desde' no puede ser posterior a 'hasta'."
        )
    return desde, hasta


def _filtrar_por_fechas(consulta, campo, desde, hasta):
    """Filtra un DateTimeField: 'desde' incluido y 'hasta' con el día completo."""
    if desde is not None:
        consulta = consulta.filter(**{f"{campo}__gte": _inicio_del_dia(desde)})
    if hasta is not None:
        consulta = consulta.filter(**{f"{campo}__lt": _inicio_del_dia(hasta + timedelta(days=1))})
    return consulta


# ------------------------------------------------------------------ Cálculo
def armar_reporte(rol=None, estado_solicitud=None, estado_pago=None, desde=None, hasta=None):
    """Aplica los filtros y devuelve un `ReporteEstadisticas` completo.

    Los valores que no existen en los catálogos se ignoran (no rompen la
    pantalla ni las exportaciones).
    """
    rol = rol if rol in Rol.values else None
    estado_solicitud = estado_solicitud if estado_solicitud in EstadoSolicitud.values else None
    estado_pago = estado_pago if estado_pago in Pago.Estado.values else None

    reporte = ReporteEstadisticas(
        rol=rol,
        estado_solicitud=estado_solicitud,
        estado_pago=estado_pago,
        desde=desde,
        hasta=hasta,
    )

    # ---------- Usuarios (fecha de registro) ----------
    usuarios = Usuario.objects.all()
    if rol in Rol.values:
        usuarios = usuarios.filter(rol=rol)
    usuarios = _filtrar_por_fechas(usuarios, "fecha_registro", desde, hasta)

    reporte.total_usuarios = usuarios.count()
    for atributo, etiqueta, valor_rol in (
        ("clientes", "Clientes", Rol.CLIENTE),
        ("trabajadores", "Trabajadores", Rol.TRABAJADOR),
        ("aliados", "Aliados", Rol.ALIADO_COMERCIAL),
    ):
        # Si se filtra por otro rol, los demás contadores quedan en cero (igual que Java).
        cantidad = 0 if (rol and rol != valor_rol) else usuarios.filter(rol=valor_rol).count()
        setattr(reporte, atributo, cantidad)
        if cantidad:
            reporte.usuarios_por_rol[etiqueta] = cantidad

    # ---------- Solicitudes (fecha de creación) ----------
    solicitudes = Solicitud.objects.select_related("cliente", "trabajador")
    if estado_solicitud in EstadoSolicitud.values:
        solicitudes = solicitudes.filter(estado=estado_solicitud)
    solicitudes = _filtrar_por_fechas(solicitudes, "fecha_creacion", desde, hasta)
    reporte.solicitudes = list(solicitudes.order_by("id"))
    reporte.total_solicitudes = len(reporte.solicitudes)

    reporte.conteo_solicitudes = {}
    reporte.solicitudes_por_estado = {}
    for valor, _ in EstadoSolicitud.choices:
        cantidad = sum(1 for s in reporte.solicitudes if s.estado == valor)
        reporte.conteo_solicitudes[valor.lower()] = cantidad
        reporte.solicitudes_por_estado[ETIQUETAS_ESTADO[valor]] = cantidad

    # ---------- Pagos (fecha de pago) ----------
    pagos = Pago.objects.select_related("solicitud", "cliente", "trabajador")
    if estado_pago in Pago.Estado.values:
        pagos = pagos.filter(estado=estado_pago)
    pagos = _filtrar_por_fechas(pagos, "fecha_pago", desde, hasta)
    pagos = list(pagos)

    if estado_pago:
        # Con filtro de estado se respeta ese estado (aunque no esté completado).
        pagos_ingreso = pagos
    else:
        pagos_ingreso = [p for p in pagos if p.estado == Pago.Estado.COMPLETADO]

    reporte.pagos = pagos_ingreso
    reporte.total_pagos_completados = len(pagos_ingreso)
    reporte.ingresos_brutos = _dinero(
        sum((p.monto_total or Decimal("0") for p in pagos_ingreso), Decimal("0"))
    )
    reporte.comision_total = _dinero(
        sum((p.comision or Decimal("0") for p in pagos_ingreso), Decimal("0"))
    )

    # ---------- Anuncios y reportes ----------
    anuncios = Anuncio.objects.filter(estado=Anuncio.Estado.PENDIENTE)
    anuncios = _filtrar_por_fechas(anuncios, "fecha_creacion", desde, hasta)
    reporte.anuncios_pendientes = anuncios.count()

    reportes = ReporteSeguridad.objects.filter(estado=ReporteSeguridad.Estado.EN_REVISION)
    reportes = _filtrar_por_fechas(reportes, "fecha", desde, hasta)
    reporte.reportes_en_revision = reportes.count()

    # ---------- Serie mensual (claves YYYY-MM ordenadas) ----------
    solicitudes_por_mes = {}
    for s in reporte.solicitudes:
        if not s.fecha_creacion:
            continue
        mes = timezone.localtime(s.fecha_creacion).strftime("%Y-%m")
        solicitudes_por_mes[mes] = solicitudes_por_mes.get(mes, 0) + 1

    ingresos_por_mes = {}
    for p in pagos_ingreso:
        if not p.fecha_pago:
            continue
        mes = timezone.localtime(p.fecha_pago).strftime("%Y-%m")
        acumulado = ingresos_por_mes.get(mes, Decimal("0")) + (p.monto_total or Decimal("0"))
        ingresos_por_mes[mes] = _dinero(acumulado)

    reporte.labels_meses = sorted(set(solicitudes_por_mes) | set(ingresos_por_mes))
    reporte.solicitudes_por_mes = solicitudes_por_mes
    reporte.ingresos_por_mes = ingresos_por_mes
    # Lista lista para recorrer en la plantilla (y para las gráficas).
    reporte.serie_mensual = [
        {
            "mes": mes,
            "solicitudes": solicitudes_por_mes.get(mes, 0),
            "ingresos": ingresos_por_mes.get(mes),
        }
        for mes in reporte.labels_meses
    ]
    return reporte


# ------------------------------------------------------------------ Etiquetas
def etiqueta_periodo(desde, hasta):
    if desde is None and hasta is None:
        return "Toda la historia"
    inicio = desde.strftime("%d/%m/%Y") if desde else "inicio"
    fin = hasta.strftime("%d/%m/%Y") if hasta else "hoy"
    return f"{inicio} al {fin}"


def etiqueta_rol(rol):
    return rol.replace("_", " ") if rol else "Todos"


def etiqueta_solicitud(estado):
    return ETIQUETAS_ESTADO.get(estado, "Todas") if estado else "Todas"


def etiqueta_pago(estado):
    return estado if estado else "Todos (ingresos con pagos completados)"


def etiqueta_estado_solicitud(solicitud):
    return solicitud.estado.replace("_", " ") if solicitud.estado else "-"


def _ahora():
    return timezone.localtime().strftime("%d/%m/%Y %H:%M")


def _fecha_hora(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M") if valor else ""


# ------------------------------------------------------------------ PDF
def generar_pdf(reporte):
    """PDF con marca, filtros, indicadores, estados, roles y serie mensual."""
    salida = io.BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=40, bottomMargin=40,
        title="Reporte y estadísticas - Cambell",
    )
    ancho = A4[0] - 72

    estilo_marca = ParagraphStyle(
        "marca", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=NARANJA
    )
    estilo_slogan = ParagraphStyle(
        "slogan", fontName="Helvetica-Oblique", fontSize=11, leading=14, textColor=GRIS
    )
    estilo_titulo = ParagraphStyle(
        "titulo", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=TEXTO
    )
    estilo_seccion = ParagraphStyle(
        "seccion", fontName="Helvetica-Bold", fontSize=11, leading=14,
        textColor=NARANJA, spaceBefore=10, spaceAfter=4,
    )
    estilo_celda = ParagraphStyle(
        "celda", fontName="Helvetica", fontSize=9, leading=11, textColor=colors.HexColor("#333333")
    )
    estilo_celda_derecha = ParagraphStyle("celda_derecha", parent=estilo_celda, alignment=TA_RIGHT)
    estilo_negrita = ParagraphStyle(
        "negrita", parent=estilo_celda, fontName="Helvetica-Bold", textColor=TEXTO
    )
    estilo_negrita_derecha = ParagraphStyle("negrita_derecha", parent=estilo_negrita, alignment=TA_RIGHT)
    estilo_encabezado = ParagraphStyle(
        "encabezado", parent=estilo_celda, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER,
    )
    estilo_pie = ParagraphStyle(
        "pie", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#8A8A8A")
    )

    def celda(valor, estilo=estilo_celda):
        return Paragraph(escape(str(valor if valor is not None else "-")), estilo)

    def tabla_pares(filas):
        """Tabla de dos columnas sin encabezado (indicadores)."""
        datos = [
            [celda(clave, estilo_celda), celda(valor, estilo_negrita_derecha)]
            for clave, valor in filas
        ]
        tabla = Table(datos, colWidths=[ancho - 130, 130])
        tabla.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return tabla

    def tabla_con_encabezado(encabezados, filas, proporciones, alineaciones):
        anchos = [ancho * p / sum(proporciones) for p in proporciones]
        datos = [[celda(titulo, estilo_encabezado) for titulo in encabezados]]
        for fila in filas:
            datos.append([
                celda(valor, estilo_negrita_derecha if alineaciones[i] == "right" else estilo_celda)
                for i, valor in enumerate(fila)
            ])
        estilos = [
            ("BACKGROUND", (0, 0), (-1, 0), NARANJA),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i in range(1, len(datos)):
            if i % 2 == 0:
                estilos.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF6EE")))
        tabla = Table(datos, colWidths=anchos, repeatRows=1)
        tabla.setStyle(TableStyle(estilos))
        return tabla

    elementos = [
        Paragraph(MARCA, estilo_marca),
        Paragraph(SLOGAN, estilo_slogan),
        Spacer(1, 12),
        Paragraph("Reporte y estadísticas de operación", estilo_titulo),
        Spacer(1, 6),
        tabla_pares([
            ("Generado", _ahora()),
            ("Periodo", etiqueta_periodo(reporte.desde, reporte.hasta)),
            ("Rol de usuario", etiqueta_rol(reporte.rol)),
            ("Estado de solicitud", etiqueta_solicitud(reporte.estado_solicitud)),
            ("Estado de pago", etiqueta_pago(reporte.estado_pago)),
        ]),
        Paragraph("1. Indicadores", estilo_seccion),
        tabla_pares([
            ("Usuarios totales", reporte.total_usuarios),
            ("Clientes", reporte.clientes),
            ("Trabajadores", reporte.trabajadores),
            ("Aliados comerciales", reporte.aliados),
            ("Solicitudes totales", reporte.total_solicitudes),
            ("Solicitudes pendientes", _texto(reporte.conteo_solicitudes.get("pendiente"))),
            ("Solicitudes aceptadas", _texto(reporte.conteo_solicitudes.get("aceptada"))),
            ("Solicitudes completadas", _texto(reporte.conteo_solicitudes.get("completada"))),
            ("Solicitudes canceladas", _texto(reporte.conteo_solicitudes.get("cancelada"))),
            ("Pagos completados", reporte.total_pagos_completados),
            ("Ingresos brutos", "$ " + _dinero_texto(reporte.ingresos_brutos)),
            ("Comisión (3%) acumulada", "$ " + _dinero_texto(reporte.comision_total)),
            ("Anuncios pendientes", reporte.anuncios_pendientes),
            ("Reportes en revisión", reporte.reportes_en_revision),
        ]),
        Paragraph("2. Solicitudes por estado", estilo_seccion),
        tabla_con_encabezado(
            ["Estado", "Cantidad"],
            list(reporte.solicitudes_por_estado.items()),
            [370, 130], ["left", "right"],
        ),
        Paragraph("3. Usuarios por rol", estilo_seccion),
        tabla_con_encabezado(
            ["Rol", "Cantidad"],
            list(reporte.usuarios_por_rol.items()),
            [370, 130], ["left", "right"],
        ),
        Paragraph("4. Solicitudes e ingresos por mes", estilo_seccion),
        tabla_con_encabezado(
            ["Mes", "Solicitudes", "Ingresos"],
            [
                (
                    mes,
                    _texto(reporte.solicitudes_por_mes.get(mes)),
                    "$ " + _dinero_texto(reporte.ingresos_por_mes[mes])
                    if mes in reporte.ingresos_por_mes else "-",
                )
                for mes in reporte.labels_meses
            ],
            [130, 170, 200], ["left", "right", "right"],
        ),
        Spacer(1, 12),
        Paragraph("Documento generado por Cambell - Servicios a domicilio.", estilo_pie),
    ]
    documento.build(elementos)
    return salida.getvalue()


# ------------------------------------------------------------------ Excel
def generar_excel(reporte):
    """Excel con hoja Resumen (indicadores) y hoja Detalle solicitudes."""
    libro = Workbook()
    resumen = libro.active
    resumen.title = "Resumen"
    resumen.column_dimensions["A"].width = 34
    resumen.column_dimensions["B"].width = 24

    relleno_naranja = PatternFill("solid", start_color=NARANJA_HEX)
    relleno_titulo = PatternFill("solid", start_color="FFE8D4")
    zebra = PatternFill("solid", start_color="FFF6EE")

    def unir(fila, texto, fuente):
        resumen.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        celda = resumen.cell(row=fila, column=1, value=texto)
        celda.font = fuente
        return celda

    def cabecera(fila, titulo, columnas=("Indicador", "Valor")):
        resumen.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        celda = resumen.cell(row=fila, column=1, value=titulo)
        celda.font = Font(size=12, bold=True, color="1A1A1A")
        celda.fill = relleno_titulo
        fila += 1
        for columna, texto in enumerate(columnas, start=1):
            celda = resumen.cell(row=fila, column=columna, value=texto)
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = relleno_naranja
        return fila + 1

    def bloque(fila, titulo, filas):
        fila = cabecera(fila, titulo)
        for i, (clave, valor) in enumerate(filas):
            for columna, texto in ((1, clave), (2, valor)):
                celda = resumen.cell(row=fila, column=columna, value=texto)
                if i % 2 == 1:
                    celda.fill = zebra
            fila += 1
        return fila

    unir(1, MARCA, Font(size=18, bold=True, color=NARANJA_HEX))
    unir(2, SLOGAN, Font(size=12, italic=True, color="6B6B6B"))
    unir(3, "Reporte y estadísticas de operación", Font(size=14, bold=True, color="1A1A1A"))
    unir(
        4,
        f"Periodo: {etiqueta_periodo(reporte.desde, reporte.hasta)}"
        f"   |   Rol: {etiqueta_rol(reporte.rol)}"
        f"   |   Estado de solicitud: {etiqueta_solicitud(reporte.estado_solicitud)}"
        f"   |   Estado de pago: {etiqueta_pago(reporte.estado_pago)}"
        f"   |   Generado: {_ahora()}",
        Font(size=11, color="666666"),
    )

    fila = 6
    fila = bloque(fila, "INDICADORES", [
        ("Usuarios totales", reporte.total_usuarios),
        ("Clientes", reporte.clientes),
        ("Trabajadores", reporte.trabajadores),
        ("Aliados comerciales", reporte.aliados),
        ("Solicitudes totales", reporte.total_solicitudes),
        ("Solicitudes pendientes", _texto(reporte.conteo_solicitudes.get("pendiente"))),
        ("Solicitudes aceptadas", _texto(reporte.conteo_solicitudes.get("aceptada"))),
        ("Solicitudes completadas", _texto(reporte.conteo_solicitudes.get("completada"))),
        ("Solicitudes canceladas", _texto(reporte.conteo_solicitudes.get("cancelada"))),
        ("Pagos completados", reporte.total_pagos_completados),
        ("Ingresos brutos", "$ " + _dinero_texto(reporte.ingresos_brutos)),
        ("Comisión (3%) acumulada", "$ " + _dinero_texto(reporte.comision_total)),
        ("Anuncios pendientes", reporte.anuncios_pendientes),
        ("Reportes en revisión", reporte.reportes_en_revision),
    ]) + 1
    fila = bloque(fila, "SOLICITUDES POR ESTADO", list(reporte.solicitudes_por_estado.items())) + 1
    fila = bloque(fila, "USUARIOS POR ROL", list(reporte.usuarios_por_rol.items())) + 1

    fila = cabecera(fila, "SOLICITUDES E INGRESOS POR MES", ("Mes", "Solicitudes / Ingresos"))
    for mes in reporte.labels_meses:
        ingresos = (
            "$ " + _dinero_texto(reporte.ingresos_por_mes[mes])
            if mes in reporte.ingresos_por_mes else "-"
        )
        resumen.cell(row=fila, column=1, value=mes)
        resumen.cell(
            row=fila, column=2,
            value=f"{_texto(reporte.solicitudes_por_mes.get(mes))} solicitudes | {ingresos}",
        )
        fila += 1
    fila += 1
    unir(fila, "Documento generado por Cambell - Servicios a domicilio.",
         Font(size=10, color="8A8A8A"))

    # ---------------- Hoja Detalle solicitudes ----------------
    detalle = libro.create_sheet("Detalle solicitudes")
    anchos = [8, 18, 40, 12, 14, 14, 24, 24, 14, 18, 18]
    for i, valor in enumerate(anchos, start=1):
        detalle.column_dimensions[get_column_letter(i)].width = valor

    detalle.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(anchos))
    detalle.cell(row=1, column=1, value="Detalle de solicitudes filtradas").font = Font(
        size=14, bold=True, color="1A1A1A"
    )
    detalle.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(anchos))
    detalle.cell(
        row=2, column=1,
        value=(
            f"Periodo: {etiqueta_periodo(reporte.desde, reporte.hasta)}"
            f"   |   Estado de solicitud: {etiqueta_solicitud(reporte.estado_solicitud)}"
        ),
    ).font = Font(size=11, color="666666")

    for columna, titulo in enumerate(COLUMNAS_DETALLE, start=1):
        celda = detalle.cell(row=4, column=columna, value=titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno_naranja

    for i, solicitud in enumerate(reporte.solicitudes):
        fila_detalle = 5 + i
        valores = [
            solicitud.id,
            etiqueta_estado_solicitud(solicitud),
            solicitud.descripcion,
            solicitud.zona,
            solicitud.localidad,
            solicitud.barrio,
            solicitud.cliente.nombre if solicitud.cliente else "",
            solicitud.trabajador.nombre if solicitud.trabajador else "",
            "$ " + _dinero_texto(solicitud.precio_ofertado) if solicitud.precio_ofertado is not None else "-",
            _fecha_hora(solicitud.fecha_creacion),
            _fecha_hora(solicitud.fecha_finalizacion),
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = detalle.cell(row=fila_detalle, column=columna, value=valor)
            if i % 2 == 1:
                celda.fill = zebra

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# ------------------------------------------------------------------ Selector
def generar(formato, reporte):
    """Devuelve (contenido en bytes, tipo MIME, extensión) para la descarga."""
    if (formato or "").lower() == "pdf":
        return generar_pdf(reporte), "application/pdf", "pdf"
    return (
        generar_excel(reporte),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    )
