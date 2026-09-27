"""Reporte mensual en PDF (se genera en el momento, no se guarda en disco)."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    ESTADO_ELIMINADA,
    OPCIONES_META,
    OPCIONES_REGISTRO,
    Meta,
    Registro,
    Usuario,
)
from .progreso import progreso_metas

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

AZUL = (30, 58, 138)
GRIS = (107, 114, 128)
NEGRO = (31, 41, 55)
VERDE = (21, 128, 61)
AMBAR = (180, 83, 9)
ANCHO_UTIL = 180
MAX_DETALLE = 400


def _limpiar(texto: object) -> str:
    """Deja el texto en un solo renglon y en un juego de caracteres imprimible."""
    plano = " ".join(str(texto or "").split())
    return plano.encode("latin-1", "replace").decode("latin-1")


def _recortar(pdf: FPDF, texto: object, ancho: float) -> str:
    limpio = _limpiar(texto)
    if pdf.get_string_width(limpio) <= ancho - 2.5:
        return limpio
    while limpio and pdf.get_string_width(limpio + "...") > ancho - 2.5:
        limpio = limpio[:-1]
    return limpio.rstrip() + "..."


class ReportePDF(FPDF):
    def __init__(self, subtitulo: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.subtitulo = _limpiar(subtitulo)
        self.set_auto_page_break(True, margin=16)
        self.set_margins(15, 15, 15)
        self.set_title(self.subtitulo)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(*AZUL)
        self.cell(0, 8, "Control de Gestion")
        self.ln(7)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*GRIS)
        self.cell(0, 6, self.subtitulo)
        self.ln(9)
        self.set_draw_color(219, 225, 234)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRIS)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")


def _titulo_seccion(pdf: FPDF, texto: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 7, texto)
    pdf.ln(8)
    pdf.set_text_color(*NEGRO)


def _tabla(pdf: FPDF, encabezados: list[str], anchos: list[float], filas: list[list]) -> None:
    def encabezado() -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(*NEGRO)
        for texto, ancho in zip(encabezados, anchos, strict=True):
            pdf.cell(ancho, 7, texto, border="B", fill=True)
        pdf.ln(7)
        pdf.set_font("Helvetica", "", 9)

    encabezado()
    for fila in filas:
        if pdf.get_y() + 7 > pdf.h - pdf.b_margin - 6:
            pdf.add_page()
            encabezado()
        for valor, ancho in zip(fila, anchos, strict=True):
            # Un valor puede venir como (texto, color) para pintar la celda.
            color = None
            if isinstance(valor, tuple):
                valor, color = valor
            if color:
                pdf.set_text_color(*color)
            pdf.cell(ancho, 7, _recortar(pdf, valor, ancho), border="B")
            pdf.set_text_color(*NEGRO)
        pdf.ln(7)
    if not filas:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GRIS)
        pdf.cell(0, 7, "Sin datos en el periodo.")
        pdf.ln(7)
        pdf.set_text_color(*NEGRO)


def _datos_del_mes(db: Session, primer_dia: date, ultimo_dia: date):
    registros = list(
        db.scalars(
            select(Registro)
            .where(Registro.fecha >= primer_dia, Registro.fecha <= ultimo_dia)
            .options(*OPCIONES_REGISTRO)
            .order_by(Registro.fecha, Registro.id)
        )
    )
    personas = list(db.scalars(select(Usuario).order_by(Usuario.nombre)))
    metas = list(
        db.scalars(
            select(Meta)
            .where(Meta.estado != ESTADO_ELIMINADA)
            .options(*OPCIONES_META)
            .order_by(
                Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite
            )
        )
    )
    return registros, personas, metas


def generar_pdf_mensual(db: Session, anio: int, mes: int) -> bytes:
    """Devuelve el PDF del mes pedido como bytes, listo para descargar."""
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    registros, personas, metas = _datos_del_mes(db, primer_dia, ultimo_dia)

    pdf = ReportePDF(f"Reporte mensual - {MESES[mes - 1].capitalize()} {anio}")
    pdf.add_page()

    # ---- Resumen general -------------------------------------------------
    total_horas = sum(r.horas for r in registros)
    dias_con_datos = len({r.fecha for r in registros})
    metas_activas = [m for m in metas if m.estado == "activa"]

    avance_por_meta = {fila["meta"].id: fila for fila in progreso_metas(db, metas)}
    avances_activas = [
        (avance_por_meta.get(meta.id) or {}).get("avance", 0) for meta in metas_activas
    ]
    avance_promedio = (
        round(sum(avances_activas) / len(avances_activas)) if avances_activas else 0
    )
    vencidas = [
        meta
        for meta in metas_activas
        if meta.fecha_limite is not None and meta.fecha_limite < date.today()
    ]

    _titulo_seccion(pdf, "Resumen general")
    pdf.set_font("Helvetica", "", 10)
    resumen = [
        f"Periodo: {primer_dia.strftime('%d/%m/%Y')} al {ultimo_dia.strftime('%d/%m/%Y')}",
        f"Reportes cargados: {len(registros)}   |   Horas acumuladas: {total_horas:.1f}",
        f"Personas activas: {sum(1 for p in personas if p.activo)}   |   "
        f"Dias con reportes: {dias_con_datos}   |   Metas activas: {len(metas_activas)}",
        f"Avance promedio de metas activas: {avance_promedio}%   |   "
        f"Metas con plazo vencido: {len(vencidas)}",
    ]
    for linea in resumen:
        pdf.cell(0, 6, _limpiar(linea))
        pdf.ln(6)

    # ---- Por persona -----------------------------------------------------
    por_persona: dict[int, dict] = {}
    for r in registros:
        fila = por_persona.setdefault(
            r.usuario_id, {"reportes": 0, "horas": 0.0, "dias": set(), "completados": 0}
        )
        fila["reportes"] += 1
        fila["horas"] += r.horas
        fila["dias"].add(r.fecha)
        if r.estado == "completado":
            fila["completados"] += 1

    filas_personas = []
    for persona in personas:
        datos = por_persona.get(persona.id)
        filas_personas.append(
            [
                persona.nombre,
                persona.cargo or ("Jefe" if persona.es_jefe else "Empleado"),
                datos["reportes"] if datos else 0,
                len(datos["dias"]) if datos else 0,
                f"{datos['horas']:.1f}" if datos else "0.0",
                datos["completados"] if datos else 0,
            ]
        )

    _titulo_seccion(pdf, "Resumen por persona")
    _tabla(
        pdf,
        ["Persona", "Cargo", "Reportes", "Dias", "Horas", "Completados"],
        [50, 42, 22, 16, 20, 30],
        filas_personas,
    )

    # ---- Metas -----------------------------------------------------------
    conteo_mes: dict[int, int] = dict(
        db.execute(
            select(Registro.meta_id, func.count(Registro.id))
            .where(Registro.fecha >= primer_dia, Registro.fecha <= ultimo_dia)
            .group_by(Registro.meta_id)
        ).all()
    )
    conteo_total: dict[int, int] = dict(
        db.execute(
            select(Registro.meta_id, func.count(Registro.id)).group_by(Registro.meta_id)
        ).all()
    )

    def color_avance(avance: int):
        if avance >= 100:
            return VERDE
        if avance < 50:
            return AMBAR
        return None

    filas_metas = []
    for meta in metas[:25]:
        avance = (avance_por_meta.get(meta.id) or {}).get("avance", 0)
        filas_metas.append(
            [
                meta.titulo,
                meta.asignado.nombre if meta.asignado else "Todo el equipo",
                meta.fecha_limite.strftime("%d/%m/%Y") if meta.fecha_limite else "-",
                (f"{avance}%", color_avance(avance)),
                conteo_mes.get(meta.id, 0),
                conteo_total.get(meta.id, 0),
                meta.estado,
            ]
        )

    _titulo_seccion(pdf, "Metas del periodo")
    _tabla(
        pdf,
        ["Meta", "Asignada a", "Plazo", "Avance", "Avances mes", "Total", "Estado"],
        [50, 32, 20, 18, 20, 14, 26],
        filas_metas,
    )

    # ---- Detalle ---------------------------------------------------------
    detalle = registros[:MAX_DETALLE]
    filas_detalle = [
        [
            r.fecha.strftime("%d/%m"),
            r.usuario.nombre,
            r.meta.titulo if r.meta else "-",
            r.descripcion,
            f"{r.horas:.1f}",
            r.estado.replace("_", " "),
        ]
        for r in detalle
    ]

    _titulo_seccion(pdf, "Detalle de reportes diarios")
    _tabla(
        pdf,
        ["Fecha", "Persona", "Meta", "Que hizo", "Horas", "Estado"],
        [16, 34, 32, 62, 14, 22],
        filas_detalle,
    )
    if len(registros) > MAX_DETALLE:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GRIS)
        pdf.cell(
            0,
            6,
            _limpiar(f"Se listan los primeros {MAX_DETALLE} de {len(registros)} reportes."),
        )
        pdf.ln(6)

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 6, f"Generado el {datetime.now():%d/%m/%Y %H:%M}")

    return bytes(pdf.output())


def generar_pdf_persona(db: Session, persona: Usuario, anio: int, mes: int) -> bytes:
    """PDF mensual de una sola persona: lo que cargo en el mes y sus metas.

    Es el mismo mes y el mismo detalle del reporte general, pero acotado a una
    persona, para que el jefe se lo pueda mandar sin filtrar a mano.
    """
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    registros, _personas, metas = _datos_del_mes(db, primer_dia, ultimo_dia)
    registros = [r for r in registros if r.usuario_id == persona.id]

    pdf = ReportePDF(f"{persona.nombre} - {MESES[mes - 1].capitalize()} {anio}")
    pdf.add_page()

    horas = sum(r.horas for r in registros)
    dias_con_datos = len({r.fecha for r in registros})
    completados = sum(1 for r in registros if r.estado == "completado")

    _titulo_seccion(pdf, "Resumen del mes")
    pdf.set_font("Helvetica", "", 10)
    resumen = [
        f"Persona: {persona.nombre} ({persona.cargo or ('Jefe' if persona.es_jefe else 'Empleado')})",
        f"Periodo: {primer_dia.strftime('%d/%m/%Y')} al {ultimo_dia.strftime('%d/%m/%Y')}",
        f"Reportes cargados: {len(registros)}   |   Dias con reportes: {dias_con_datos}",
        f"Horas acumuladas: {horas:.1f}   |   Reportes completados: {completados}",
    ]
    for linea in resumen:
        pdf.cell(0, 6, _limpiar(linea))
        pdf.ln(6)

    propias = [
        m
        for m in metas
        if m.asignado_a == persona.id or m.asignado_a is None
    ]
    avance_por_meta = {fila["meta"].id: fila for fila in progreso_metas(db, propias)}

    def color_avance(avance: int):
        if avance >= 100:
            return VERDE
        if avance < 50:
            return AMBAR
        return None

    filas_metas = []
    for meta in propias[:25]:
        avance = (avance_por_meta.get(meta.id) or {}).get("avance", 0)
        filas_metas.append(
            [
                meta.titulo,
                meta.fecha_limite.strftime("%d/%m/%Y") if meta.fecha_limite else "-",
                (f"{avance}%", color_avance(avance)),
                meta.estado,
            ]
        )

    _titulo_seccion(pdf, "Metas del periodo")
    _tabla(
        pdf,
        ["Meta", "Plazo", "Avance", "Estado"],
        [78, 30, 30, 42],
        filas_metas,
    )

    filas_detalle = [
        [
            r.fecha.strftime("%d/%m/%Y"),
            r.meta.titulo if r.meta else "-",
            r.descripcion,
            f"{r.horas:.1f}",
            r.estado.replace("_", " "),
        ]
        for r in registros[:MAX_DETALLE]
    ]

    _titulo_seccion(pdf, "Detalle de reportes diarios")
    _tabla(
        pdf,
        ["Fecha", "Meta", "Que hizo", "Horas", "Estado"],
        [24, 38, 74, 14, 30],
        filas_detalle,
    )
    if len(registros) > MAX_DETALLE:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GRIS)
        pdf.cell(
            0,
            6,
            _limpiar(f"Se listan los primeros {MAX_DETALLE} de {len(registros)} reportes."),
        )
        pdf.ln(6)

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 6, f"Generado el {datetime.now():%d/%m/%Y %H:%M}")

    return bytes(pdf.output())
