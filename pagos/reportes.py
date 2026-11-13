"""Reporte de ingresos del trabajador en CSV, Excel y PDF (ReporteIngresosService.java)."""
import csv
import io

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

MARCA = "Cambell"
SLOGAN = "Conectamos el talento de tu barrio, con seguridad"
COLUMNAS = ["Fecha", "Solicitud", "Cliente", "Monto total", "Comision (3%)", "Neto recibido"]
NARANJA_HEX = "FF6B00"


def _fecha_hora(fecha):
    return timezone.localtime(fecha).strftime("%d/%m/%Y %H:%M") if fecha else ""


def _ahora():
    return timezone.localtime().strftime("%d/%m/%Y %H:%M")


def etiqueta_periodo(desde, hasta):
    if desde is None and hasta is None:
        return "Todo el historial"
    inicio = desde.strftime("%d/%m/%Y") if desde else "el inicio"
    fin = hasta.strftime("%d/%m/%Y") if hasta else "hoy"
    return f"{inicio} a {fin}"


def _filas(pagos):
    """[(fecha, solicitud, cliente, monto, comision, neto), ...] y el total neto."""
    filas, total = [], 0
    for p in pagos:
        neto = p.neto_trabajador or 0
        total += neto
        filas.append((
            _fecha_hora(p.fecha_pago),
            p.solicitud.descripcion,
            p.cliente.nombre,
            p.monto_total or 0,
            p.comision or 0,
            neto,
        ))
    return filas, total


def _dinero(valor):
    return f"{valor:,.2f}"


# ---------------------------------------------------------------- CSV
def generar_csv(pagos, trabajador, desde, hasta):
    filas, total = _filas(pagos)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([MARCA])
    escritor.writerow([SLOGAN])
    escritor.writerow([f"Reporte de ingresos - {trabajador.nombre}"])
    escritor.writerow([f"Periodo: {etiqueta_periodo(desde, hasta)} | Generado: {_ahora()}"])
    escritor.writerow([])
    escritor.writerow(COLUMNAS)
    for fecha, solicitud, cliente, monto, comision, neto in filas:
        # Números "limpios" (12345.60, sin separador de miles) para poder usarlos en una hoja de cálculo.
        escritor.writerow([fecha, solicitud, cliente, f"{monto:.2f}", f"{comision:.2f}", f"{neto:.2f}"])
    escritor.writerow([])
    escritor.writerow(["Total neto", "", "", "", "", f"{total:.2f}"])
    # El BOM (\ufeff) hace que Excel en Windows muestre bien las tildes.
    return ("\ufeff" + salida.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- Excel
def generar_excel(pagos, trabajador, desde, hasta):
    filas, total = _filas(pagos)
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte de ingresos"

    for i, ancho in enumerate([18, 38, 26, 14, 14, 15], start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho

    def fila_unida(numero, texto, fuente):
        hoja.merge_cells(start_row=numero, start_column=1, end_row=numero, end_column=6)
        celda = hoja.cell(row=numero, column=1, value=texto)
        celda.font = fuente
        return celda

    fila_unida(1, MARCA, Font(size=18, bold=True, color=NARANJA_HEX))
    fila_unida(2, SLOGAN, Font(size=12, italic=True, color="6B6B6B"))
    fila_unida(3, f"Reporte de ingresos - {trabajador.nombre}", Font(size=14, bold=True, color="1A1A1A"))
    fila_unida(4, f"Periodo: {etiqueta_periodo(desde, hasta)}   |   Generado: {_ahora()}",
               Font(size=11, color="666666"))

    encabezado = 5
    relleno_naranja = PatternFill("solid", start_color=NARANJA_HEX)
    for c, titulo in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=encabezado, column=c, value=titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno_naranja
        celda.alignment = Alignment(horizontal="center")

    fila = encabezado + 1
    zebra = PatternFill("solid", start_color="FFF6EE")
    for i, (fecha, solicitud, cliente, monto, comision, neto) in enumerate(filas):
        valores = [fecha, solicitud, cliente, float(monto), float(comision), float(neto)]
        for c, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=c, value=valor)
            if c >= 4:
                celda.number_format = "#,##0.00"
            if i % 2 == 1:
                celda.fill = zebra
        fila += 1

    hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=5)
    etiqueta = hoja.cell(row=fila, column=1, value="Total neto")
    etiqueta.font = Font(bold=True, color="1A1A1A")
    etiqueta.alignment = Alignment(horizontal="right")
    etiqueta.fill = PatternFill("solid", start_color="FFE8D4")
    valor_total = hoja.cell(row=fila, column=6, value=float(total))
    valor_total.font = Font(bold=True, color=NARANJA_HEX)
    valor_total.number_format = "#,##0.00"
    valor_total.fill = PatternFill("solid", start_color="FFE8D4")

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# ---------------------------------------------------------------- PDF
def generar_pdf(pagos, trabajador, desde, hasta):
    filas, total = _filas(pagos)
    salida = io.BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=40, bottomMargin=40,
        title="Reporte de ingresos - Cambell",
    )
    ancho_util = A4[0] - 72
    naranja = colors.HexColor("#FF6B00")
    gris = colors.HexColor("#6B6B6B")
    texto = colors.HexColor("#1A1A1A")

    estilo_marca = ParagraphStyle("marca", fontName="Helvetica-Bold", fontSize=24, textColor=naranja, leading=28)
    estilo_slogan = ParagraphStyle("slogan", fontName="Helvetica-Oblique", fontSize=11, textColor=gris, leading=14)
    estilo_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, textColor=texto, leading=20)
    estilo_celda = ParagraphStyle("celda", fontName="Helvetica", fontSize=9, textColor=texto, leading=11)
    estilo_pie = ParagraphStyle("pie", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#8A8A8A"))

    def celda(valor):
        return Paragraph(escape(str(valor)), estilo_celda)

    elementos = [
        Paragraph(MARCA, estilo_marca),
        Paragraph(SLOGAN, estilo_slogan),
        Spacer(1, 12),
        Paragraph("Reporte de ingresos", estilo_titulo),
        Spacer(1, 6),
    ]

    datos = Table(
        [
            [celda("Trabajador"), celda(trabajador.nombre)],
            [celda("Periodo"), celda(etiqueta_periodo(desde, hasta))],
            [celda("Generado"), celda(_ahora())],
        ],
        colWidths=[110, ancho_util - 110],
    )
    datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    elementos += [datos, Spacer(1, 12)]

    proporciones = [16, 26, 20, 13, 13, 12]
    anchos = [ancho_util * p / sum(proporciones) for p in proporciones]
    estilo_encabezado = ParagraphStyle(
        "encabezado", parent=estilo_celda, fontName="Helvetica-Bold", textColor=colors.white
    )
    tabla_datos = [[Paragraph(escape(c), estilo_encabezado) for c in COLUMNAS]]
    for fecha, solicitud, cliente, monto, comision, neto in filas:
        tabla_datos.append([
            celda(fecha), celda(solicitud), celda(cliente),
            celda(f"$ {_dinero(monto)}"), celda(f"$ {_dinero(comision)}"), celda(f"$ {_dinero(neto)}"),
        ])
    estilo_total = ParagraphStyle(
        "total", parent=estilo_celda, fontName="Helvetica-Bold", fontSize=10, alignment=2
    )
    # El total ocupa toda la fila para que el valor nunca se parta en dos líneas.
    tabla_datos.append([
        Paragraph(f'Total neto&nbsp;&nbsp;&nbsp;<font color="#FF6B00">$ {escape(_dinero(total))}</font>',
                  estilo_total),
        "", "", "", "", "",
    ])

    ultima = len(tabla_datos) - 1
    estilos = [
        ("BACKGROUND", (0, 0), (-1, 0), naranja),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, ultima - 1), 0.25, colors.HexColor("#DDDDDD")),
        ("SPAN", (0, ultima), (5, ultima)),
        ("BACKGROUND", (0, ultima), (-1, ultima), colors.HexColor("#FFE8D4")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, ultima):
        if i % 2 == 0:
            estilos.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF6EE")))

    tabla = Table(tabla_datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle(estilos))
    elementos += [tabla, Spacer(1, 12),
                  Paragraph("Documento generado por Cambell - Servicios a domicilio.", estilo_pie)]

    documento.build(elementos)
    return salida.getvalue()


# ---------------------------------------------------------------- Selector
def generar(formato, pagos, trabajador, desde, hasta):
    """Devuelve (contenido en bytes, tipo MIME, extensión) según el formato pedido."""
    formato = (formato or "csv").lower()
    if formato == "pdf":
        return generar_pdf(pagos, trabajador, desde, hasta), "application/pdf", "pdf"
    if formato in ("excel", "xlsx"):
        return (
            generar_excel(pagos, trabajador, desde, hasta),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    return generar_csv(pagos, trabajador, desde, hasta), "text/csv; charset=utf-8", "csv"