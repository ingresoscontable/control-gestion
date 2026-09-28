"""Metricas del panel: resumen semanal, horas por semana y calendario."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .jornada import dias_laborables, es_laborable
from .models import Registro, Usuario
from .novedades import laborables_del_rango

COLORES = 6


def _iniciales(nombre: str) -> str:
    """Hasta dos letras para mostrar en una celda chica del calendario."""
    partes = [p for p in nombre.split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def rango_semana(dia: date) -> tuple[date, date]:
    """Lunes y domingo de la semana a la que pertenece el dia."""
    lunes = dia - timedelta(days=dia.weekday())
    return lunes, lunes + timedelta(days=6)


def expresion_en_fecha():
    """Expresion SQL: el reporte se cargo el mismo dia del trabajo.

    `creado_en` es cuando se apreto Guardar y `fecha` el dia que se informa.
    No pueden coincidir al reves (el sistema no deja cargar en el futuro), asi
    que "en fecha" es exactamente que las dos fechas sean iguales.
    """
    return func.date(Registro.creado_en) == Registro.fecha


def puntualidad(db: Session, usuario_id: int, desde: date, hasta: date) -> dict:
    """Cuanto de lo cargado se cargo el mismo dia en que se hizo el trabajo."""
    total, en_fecha = db.execute(
        select(
            func.count(Registro.id),
            func.coalesce(func.sum(case((expresion_en_fecha(), 1), else_=0)), 0),
        ).where(
            Registro.usuario_id == usuario_id,
            Registro.fecha >= desde,
            Registro.fecha <= hasta,
        )
    ).one()
    total = int(total or 0)
    en_fecha = int(en_fecha or 0)
    return {
        "total": total,
        "en_fecha": en_fecha,
        "tarde": total - en_fecha,
        "porcentaje": round(en_fecha / total * 100) if total else None,
    }


def _cumplimiento(dias: int, laborables: int) -> str:
    """Etiqueta de cumplimiento: al_dia / parcial / baja / sin_laborables."""
    if laborables <= 0:
        return "sin_laborables"
    if dias >= laborables:
        return "al_dia"
    if dias * 5 >= laborables * 3:
        return "parcial"
    return "baja"


def resumen_semanal(
    db: Session, equipo: list[Usuario], hoy: date
) -> tuple[list[dict], date]:
    """Totales de la semana en curso (lunes a domingo) por persona.

    Los "dias" cuentan solo los laborables (CG_DIAS_LABORABLES): cargar un
    sabado no infla el cumplimiento. `laborables` es la referencia de esa
    semana para esa persona, que las novedades (vacaciones, licencia) bajan.
    """
    inicio, fin = rango_semana(hoy)
    total_laborables = dias_laborables(inicio, fin)

    filas = db.execute(
        select(
            Registro.usuario_id,
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
            func.coalesce(func.sum(case((expresion_en_fecha(), 1), else_=0)), 0),
        )
        .where(Registro.fecha >= inicio, Registro.fecha <= fin)
        .group_by(Registro.usuario_id)
    ).all()
    por_usuario = {fila[0]: fila for fila in filas}

    fechas = db.execute(
        select(Registro.usuario_id, Registro.fecha)
        .where(Registro.fecha >= inicio, Registro.fecha <= fin)
        .distinct()
    ).all()
    dias_por_usuario: dict[int, set[date]] = {}
    for usuario_id, fecha in fechas:
        if es_laborable(fecha):
            dias_por_usuario.setdefault(usuario_id, set()).add(fecha)

    resumen = []
    for persona in equipo:
        fila = por_usuario.get(persona.id)
        dias = len(dias_por_usuario.get(persona.id, ()))
        laborables = laborables_del_rango(db, persona.id, inicio, fin, total_laborables)
        registros = fila[1] if fila else 0
        en_fecha = int(fila[3]) if fila else 0
        resumen.append(
            {
                "usuario": persona,
                "registros": registros,
                "horas": float(fila[2]) if fila else 0.0,
                "en_fecha": en_fecha,
                "puntualidad": round(en_fecha / registros * 100) if registros else None,
                "dias": dias,
                "laborables": laborables,
                "cumplimiento": _cumplimiento(dias, laborables),
            }
        )
    return resumen, inicio


def horas_por_semana(
    db: Session, equipo: list[Usuario], hoy: date, semanas: int = 8
) -> dict:
    """Horas cargadas por persona en cada una de las ultimas semanas.

    Devuelve las barras ya escaladas (en % de alto) para que la plantilla no
    tenga que hacer cuentas.
    """
    inicio_actual, _ = rango_semana(hoy)
    inicio = inicio_actual - timedelta(weeks=semanas - 1)
    fin = inicio_actual + timedelta(days=6)

    filas = db.execute(
        select(Registro.fecha, Registro.usuario_id, Registro.horas).where(
            Registro.fecha >= inicio, Registro.fecha <= fin
        )
    ).all()

    bloques = []
    for posicion in range(semanas):
        desde = inicio + timedelta(weeks=posicion)
        bloques.append(
            {
                "desde": desde,
                "hasta": desde + timedelta(days=6),
                "valores": {},
                "total": 0.0,
                "actual": desde == inicio_actual,
            }
        )

    for fecha, usuario_id, horas in filas:
        indice = (fecha - inicio).days // 7
        if 0 <= indice < semanas:
            bloque = bloques[indice]
            bloque["valores"][usuario_id] = bloque["valores"].get(usuario_id, 0.0) + horas
            bloque["total"] += horas

    maximo = max(
        (valor for bloque in bloques for valor in bloque["valores"].values()),
        default=0.0,
    )

    for bloque in bloques:
        barras = []
        for posicion, persona in enumerate(equipo):
            horas = bloque["valores"].get(persona.id, 0.0)
            alto = round(horas / maximo * 100) if maximo else 0
            if horas > 0 and alto < 3:
                alto = 3  # que una hora suelta siga siendo visible
            barras.append(
                {
                    "usuario": persona,
                    "horas": horas,
                    "alto": alto,
                    "clase": f"c{posicion % COLORES + 1}",
                }
            )
        bloque["barras"] = barras

    return {
        "bloques": bloques,
        "maximo": maximo,
        "leyenda": [
            {"usuario": persona, "clase": f"c{posicion % COLORES + 1}"}
            for posicion, persona in enumerate(equipo)
        ],
        "hay_datos": maximo > 0,
    }


def calendario_mes(db: Session, equipo: list[Usuario], anio: int, mes: int) -> dict:
    """Quien cargo, dia por dia, durante el mes pedido.

    Cada celda trae una linea por persona del equipo para que se vean los dias
    sin reporte sin tener que contarlos a mano.
    """
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    filas = db.execute(
        select(
            Registro.fecha,
            Registro.usuario_id,
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
        )
        .where(Registro.fecha >= primer_dia, Registro.fecha <= ultimo_dia)
        .group_by(Registro.fecha, Registro.usuario_id)
    ).all()

    cargado: dict[date, dict[int, dict]] = {}
    for fecha, usuario_id, reportes, horas in filas:
        cargado.setdefault(fecha, {})[usuario_id] = {
            "reportes": reportes,
            "horas": float(horas),
        }

    dias = []
    dia = primer_dia
    while dia <= ultimo_dia:
        del_dia = cargado.get(dia, {})
        celdas = []
        for posicion, persona in enumerate(equipo):
            dato = del_dia.get(persona.id)
            celdas.append(
                {
                    "usuario": persona,
                    "iniciales": _iniciales(persona.nombre),
                    "cargado": dato is not None,
                    "horas": dato["horas"] if dato else 0.0,
                    "reportes": dato["reportes"] if dato else 0,
                    "clase": f"c{posicion % COLORES + 1}",
                }
            )

        dias.append(
            {
                "fecha": dia,
                "num": dia.day,
                "finde": dia.weekday() >= 5,
                "celdas": celdas,
                "total": sum(dato["horas"] for dato in del_dia.values()),
                "reportaron": len(del_dia),
            }
        )
        dia += timedelta(days=1)

    return {
        "anio": anio,
        "mes": mes,
        "dias": dias,
        # dias del mes anterior que hay que dejar en blanco al principio
        "huecos": primer_dia.weekday(),
        "total_horas": sum(dia["total"] for dia in dias),
        "dias_con_carga": sum(1 for dia in dias if dia["reportaron"]),
    }
