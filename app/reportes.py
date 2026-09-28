"""Reporte mensual en PDF (se genera en el momento, no se guarda en disco)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from fpdf import FPDF
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .jornada import dias_laborables
from .metricas import expresion_en_fecha
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


def _datos_del_rango(db: Session, desde: date, hasta: date):
    """Los tres conjuntos que necesitan los informes, ya cargados."""
    registros = list(
        db.scalars(
            select(Registro)
            .where(Registro.fecha >= desde, Registro.fecha <= hasta)
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


def resumen_periodo(db: Session, desde: date, hasta: date) -> dict:
    """Totales del rango y detalle por persona, para la pantalla y el PDF.

    El informe mensual es un rango mas (del dia 1 al ultimo del mes), asi que
    los dos salen de esta misma funcion y no hay cuentas duplicadas.
    """
    en_fecha = expresion_en_fecha()
    completados = case((Registro.estado == "completado", 1), else_=0)

    por_persona = {
        fila[0]: fila
        for fila in db.execute(
            select(
                Registro.usuario_id,
                func.count(Registro.id),
                func.coalesce(func.sum(Registro.horas), 0.0),
                func.coalesce(func.sum(Registro.cantidad), 0.0),
                func.count(func.distinct(Registro.fecha)),
                func.coalesce(func.sum(completados), 0),
                func.coalesce(func.sum(case((en_fecha, 1), else_=0)), 0),
            )
            .where(Registro.fecha >= desde, Registro.fecha <= hasta)
            .group_by(Registro.usuario_id)
        ).all()
    }

    totales = db.execute(
        select(
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
            func.coalesce(func.sum(Registro.cantidad), 0.0),
            func.count(func.distinct(Registro.fecha)),
            func.coalesce(func.sum(completados), 0),
            func.coalesce(func.sum(case((en_fecha, 1), else_=0)), 0),
        ).where(Registro.fecha >= desde, Registro.fecha <= hasta)
    ).one()

    filas = []
    for persona in db.scalars(select(Usuario).order_by(Usuario.nombre)):
        datos = por_persona.get(persona.id)
        filas.append(
            {
                "usuario": persona,
                "cargo": persona.cargo or ("Jefe" if persona.es_jefe else "Empleado"),
                "reportes": int(datos[1]) if datos else 0,
                "horas": float(datos[2]) if datos else 0.0,
                "cantidad": float(datos[3]) if datos else 0.0,
                "dias": int(datos[4]) if datos else 0,
                "completados": int(datos[5]) if datos else 0,
                "en_fecha": int(datos[6]) if datos else 0,
            }
        )

    reportes = int(totales[0] or 0)
    en_fecha_total = int(totales[5] or 0)
    return {
        "desde": desde,
        "hasta": hasta,
        "laborables": dias_laborables(desde, hasta),
        "totales": {
            "reportes": reportes,
            "horas": float(totales[1] or 0.0),
            "cantidad": float(totales[2] or 0.0),
            "dias": int(totales[3] or 0),
            "completados": int(totales[4] or 0),
            "en_fecha": en_fecha_total,
            "puntualidad": (
                round(en_fecha_total / reportes * 100) if reportes else None
            ),
        },
        "por_persona": filas,
    }


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    """Periodo inmediatamente anterior, de la misma cantidad de dias."""
    largo = (hasta - desde).days + 1
    return desde - timedelta(days=largo), desde - timedelta(days=1)


def _comparar_cifra(actual: float, anterior: float, decimales: int = 0) -> dict:
    """Valor del periodo, del anterior y la diferencia ya resuelta.

    La pantalla y el PDF solo tienen que mostrar `texto` con el color de
    `sentido`: las cuentas no se repiten en cada lugar.
    """
    diferencia = actual - anterior
    if diferencia > 0:
        sentido = "sube"
    elif diferencia < 0:
        sentido = "baja"
    else:
        sentido = "igual"
    return {
        "actual": actual,
        "anterior": anterior,
        "sentido": sentido,
        "texto": f"{diferencia:+.{decimales}f}" if diferencia else "=",
    }


def comparativa(db: Session, desde: date, hasta: date) -> dict:
    """Compara el rango con el periodo anterior de igual duracion."""
    desde_anterior, hasta_anterior = periodo_anterior(desde, hasta)
    actual = resumen_periodo(db, desde, hasta)
    anterior = resumen_periodo(db, desde_anterior, hasta_anterior)
    previo = {fila["usuario"].id: fila for fila in anterior["por_persona"]}

    filas = []
    for fila in actual["por_persona"]:
        antes = previo.get(fila["usuario"].id, {})
        filas.append(
            {
                "usuario": fila["usuario"],
                "reportes": _comparar_cifra(fila["reportes"], antes.get("reportes", 0)),
                "horas": _comparar_cifra(
                    fila["horas"], antes.get("horas", 0.0), decimales=1
                ),
                "dias": _comparar_cifra(fila["dias"], antes.get("dias", 0)),
                "en_fecha": _comparar_cifra(
                    fila["en_fecha"], antes.get("en_fecha", 0)
                ),
            }
        )

    totales_actual = actual["totales"]
    totales_anterior = anterior["totales"]
    return {
        "desde": desde_anterior,
        "hasta": hasta_anterior,
        "actual": actual,
        "anterior": anterior,
        "filas": filas,
        "reportes": _comparar_cifra(
            totales_actual["reportes"], totales_anterior["reportes"]
        ),
        "horas": _comparar_cifra(
            totales_actual["horas"], totales_anterior["horas"], decimales=1
        ),
        "dias": _comparar_cifra(totales_actual["dias"], totales_anterior["dias"]),
        "en_fecha": _comparar_cifra(
            totales_actual["en_fecha"], totales_anterior["en_fecha"]
        ),
    }


def _delta_celda(dato: dict):
    """Celda de la comparacion: el texto de la diferencia y su color."""
    colores = {"sube": VERDE, "baja": AMBAR}
    return (dato["texto"], colores.get(dato["sentido"]))


def _comparacion_pdf(pdf: FPDF, comparacion: dict, totales: dict) -> None:
    """Seccion de comparacion contra el periodo anterior."""
    _titulo_seccion(pdf, "Comparacion con el periodo anterior")
    pdf.set_font("Helvetica", "", 10)
    antes = comparacion["anterior"]["totales"]
    lineas = [
        f"Periodo anterior: {comparacion['desde'].strftime('%d/%m/%Y')} al "
        f"{comparacion['hasta'].strftime('%d/%m/%Y')}",
        f"Reportes: antes {antes['reportes']} / ahora {totales['reportes']}   |   "
        f"Horas: antes {antes['horas']:.1f} / ahora {totales['horas']:.1f}",
        f"Dias con reportes: antes {antes['dias']} / ahora {totales['dias']}   |   "
        f"Cargados en fecha: antes {antes['en_fecha']} / ahora {totales['en_fecha']}",
        f"Cantidad informada: antes {antes['cantidad']:.0f} / "
        f"ahora {totales['cantidad']:.0f}",
    ]
    for linea in lineas:
        pdf.cell(0, 6, _limpiar(linea))
        pdf.ln(6)
    pdf.ln(1)

    filas = [
        [
            fila["usuario"].nombre,
            fila["reportes"]["actual"],
            _delta_celda(fila["reportes"]),
            f"{fila['horas']['actual']:.1f}",
            _delta_celda(fila["horas"]),
            fila["dias"]["actual"],
            _delta_celda(fila["dias"]),
            fila["en_fecha"]["actual"],
            _delta_celda(fila["en_fecha"]),
        ]
        for fila in comparacion["filas"]
    ]
    _tabla(
        pdf,
        [
            "Persona",
            "Rep.",
            "Delta",
            "Horas",
            "Delta",
            "Dias",
            "Delta",
            "En fecha",
            "Delta",
        ],
        [40, 20, 16, 22, 16, 16, 16, 20, 14],
        filas,
    )


def generar_pdf_rango(
    db: Session,
    desde: date,
    hasta: date,
    comparar: bool = False,
    titulo: str = "",
) -> bytes:
    """PDF de un rango de fechas cualquiera, listo para descargar.

    El informe mensual es un caso particular (del dia 1 al ultimo del mes), asi
    que los dos salen de aca y no hay dos reportes que mantener en paralelo.
    """
    registros, personas, metas = _datos_del_rango(db, desde, hasta)

    comparacion = None
    if comparar:
        comparacion = comparativa(db, desde, hasta)
        resumen = comparacion["actual"]
    else:
        resumen = resumen_periodo(db, desde, hasta)
    totales = resumen["totales"]

    pdf = ReportePDF(titulo or f"Reporte del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}")
    pdf.add_page()

    # ---- Resumen general -------------------------------------------------
    metas_activas = [m for m in metas if m.estado == "activa"]
    puntualidad_txt = (
        f"{totales['puntualidad']}%" if totales["puntualidad"] is not None else "-"
    )

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
    resumen_general = [
        f"Periodo: {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}",
        f"Reportes cargados: {totales['reportes']}   |   "
        f"Horas acumuladas: {totales['horas']:.1f}   |   "
        f"Cantidad informada: {totales['cantidad']:.0f}",
        f"Personas activas: {sum(1 for p in personas if p.activo)}   |   "
        f"Dias con reportes: {totales['dias']}   |   "
        f"Dias laborables del periodo: {resumen['laborables']}",
        f"Cargados el mismo dia del trabajo: {totales['en_fecha']} de "
        f"{totales['reportes']} ({puntualidad_txt})",
        f"Metas activas: {len(metas_activas)}   |   "
        f"Avance promedio de metas activas: {avance_promedio}%   |   "
        f"Metas con plazo vencido: {len(vencidas)}",
    ]
    for linea in resumen_general:
        pdf.cell(0, 6, _limpiar(linea))
        pdf.ln(6)

    # ---- Por persona -----------------------------------------------------
    filas_personas = [
        [
            fila["usuario"].nombre,
            fila["cargo"],
            fila["reportes"],
            fila["dias"],
            f"{fila['horas']:.1f}",
            fila["en_fecha"],
            f"{fila['cantidad']:.0f}" if fila["cantidad"] else "-",
            fila["completados"],
        ]
        for fila in resumen["por_persona"]
    ]

    _titulo_seccion(pdf, "Resumen por persona")
    _tabla(
        pdf,
        [
            "Persona",
            "Cargo",
            "Reportes",
            "Dias",
            "Horas",
            "En fecha",
            "Cant.",
            "Completados",
        ],
        [40, 32, 20, 14, 18, 18, 14, 24],
        filas_personas,
    )

    # ---- Comparacion con el periodo anterior -----------------------------
    if comparacion is not None:
        _comparacion_pdf(pdf, comparacion, totales)

    # ---- Metas -----------------------------------------------------------
    conteo_periodo: dict[int, int] = dict(
        db.execute(
            select(Registro.meta_id, func.count(Registro.id))
            .where(Registro.fecha >= desde, Registro.fecha <= hasta)
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
                conteo_periodo.get(meta.id, 0),
                conteo_total.get(meta.id, 0),
                meta.estado,
            ]
        )

    _titulo_seccion(pdf, "Metas del periodo")
    _tabla(
        pdf,
        [
            "Meta",
            "Asignada a",
            "Plazo",
            "Avance",
            "Avances periodo",
            "Total",
            "Estado",
        ],
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
            f"{r.cantidad:.0f}" if r.cantidad else "-",
            r.estado.replace("_", " "),
        ]
        for r in detalle
    ]

    _titulo_seccion(pdf, "Detalle de reportes diarios")
    _tabla(
        pdf,
        ["Fecha", "Persona", "Meta", "Que hizo", "Horas", "Cant.", "Estado"],
        [16, 32, 30, 48, 14, 12, 28],
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


def generar_pdf_mensual(db: Session, anio: int, mes: int) -> bytes:
    """Devuelve el PDF del mes pedido como bytes, listo para descargar."""
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    titulo = f"Reporte mensual - {MESES[mes - 1].capitalize()} {anio}"
    return generar_pdf_rango(db, primer_dia, ultimo_dia, titulo=titulo)


def generar_pdf_persona(db: Session, persona: Usuario, anio: int, mes: int) -> bytes:
    """PDF mensual de una sola persona: lo que cargo en el mes y sus metas.

    Es el mismo mes y el mismo detalle del reporte general, pero acotado a una
    persona, para que el jefe se lo pueda mandar sin filtrar a mano.
    """
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    registros, _personas, metas = _datos_del_rango(db, primer_dia, ultimo_dia)
    registros = [r for r in registros if r.usuario_id == persona.id]

    pdf = ReportePDF(f"{persona.nombre} - {MESES[mes - 1].capitalize()} {anio}")
    pdf.add_page()

    horas = sum(r.horas for r in registros)
    dias_con_datos = len({r.fecha for r in registros})
    completados = sum(1 for r in registros if r.estado == "completado")
    en_fecha = sum(
        1 for r in registros if r.creado_en and r.creado_en.date() == r.fecha
    )
    cantidad = sum(r.cantidad for r in registros)
    porcentaje_en_fecha = round(en_fecha / len(registros) * 100) if registros else 0

    _titulo_seccion(pdf, "Resumen del mes")
    pdf.set_font("Helvetica", "", 10)
    resumen = [
        f"Persona: {persona.nombre} ({persona.cargo or ('Jefe' if persona.es_jefe else 'Empleado')})",
        f"Periodo: {primer_dia.strftime('%d/%m/%Y')} al {ultimo_dia.strftime('%d/%m/%Y')}",
        f"Reportes cargados: {len(registros)}   |   Dias con reportes: {dias_con_datos}",
        f"Horas acumuladas: {horas:.1f}   |   Reportes completados: {completados}",
        f"Cargados el mismo dia del trabajo: {en_fecha} de {len(registros)} "
        f"({porcentaje_en_fecha}%)",
        f"Cantidad informada en el periodo: {cantidad:.0f}",
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
            f"{r.cantidad:.0f}" if r.cantidad else "-",
            r.estado.replace("_", " "),
        ]
        for r in registros[:MAX_DETALLE]
    ]

    _titulo_seccion(pdf, "Detalle de reportes diarios")
    _tabla(
        pdf,
        ["Fecha", "Meta", "Que hizo", "Horas", "Cant.", "Estado"],
        [22, 36, 60, 14, 12, 36],
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
