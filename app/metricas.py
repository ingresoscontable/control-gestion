"""Metricas del panel: resumen semanal y horas por semana."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Registro, Usuario

COLORES = 6


def rango_semana(dia: date) -> tuple[date, date]:
    """Lunes y domingo de la semana a la que pertenece el dia."""
    lunes = dia - timedelta(days=dia.weekday())
    return lunes, lunes + timedelta(days=6)


def resumen_semanal(
    db: Session, equipo: list[Usuario], hoy: date
) -> tuple[list[dict], date]:
    """Totales de la semana en curso (lunes a domingo) por persona."""
    inicio, fin = rango_semana(hoy)

    filas = db.execute(
        select(
            Registro.usuario_id,
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
            func.count(func.distinct(Registro.fecha)),
        )
        .where(Registro.fecha >= inicio, Registro.fecha <= fin)
        .group_by(Registro.usuario_id)
    ).all()
    por_usuario = {fila[0]: fila for fila in filas}

    resumen = []
    for persona in equipo:
        fila = por_usuario.get(persona.id)
        resumen.append(
            {
                "usuario": persona,
                "registros": fila[1] if fila else 0,
                "horas": float(fila[2]) if fila else 0.0,
                "dias": fila[3] if fila else 0,
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
