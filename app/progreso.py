"""Avance de las metas y deteccion de plazos vencidos.

Vive aparte de `main` y de `reportes` para que la pantalla de progreso y el
reporte en PDF usen exactamente el mismo calculo.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Meta, Registro

# Colores por nivel de avance (se usan tambien en el PDF).
NIVEL_COMPLETA = "completa"
NIVEL_MEDIA = "media"
NIVEL_BAJA = "baja"


def _calcular_avance(
    estado: str, horas: float, estimadas: float, reportes: int, completados: int
) -> int:
    if estado == "cerrada":
        return 100
    if estimadas and estimadas > 0:
        return min(100, round(horas / estimadas * 100))
    if reportes:
        return round(completados / reportes * 100)
    return 0


def progreso_metas(db: Session, metas: list[Meta]) -> list[dict]:
    """Calcula el avance de cada meta a partir de los reportes cargados.

    El porcentaje sale de las horas estimadas si la meta las tiene; si no, de la
    proporcion de reportes marcados como completados. Una meta cerrada cuenta
    como 100%.
    """
    if not metas:
        return []

    filas = db.execute(
        select(
            Registro.meta_id,
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
            func.coalesce(
                func.sum(case((Registro.estado == "completado", 1), else_=0)), 0
            ),
        )
        .where(Registro.meta_id.in_([meta.id for meta in metas]))
        .group_by(Registro.meta_id)
    ).all()
    acumulado = {fila[0]: fila for fila in filas}

    resultado = []
    for meta in metas:
        fila = acumulado.get(meta.id)
        reportes = int(fila[1]) if fila else 0
        horas = float(fila[2]) if fila else 0.0
        completados = int(fila[3]) if fila else 0

        avance = _calcular_avance(
            meta.estado, horas, meta.horas_estimadas or 0, reportes, completados
        )
        resultado.append(
            {
                "meta": meta,
                "reportes": reportes,
                "horas": horas,
                "completados": completados,
                "avance": avance,
                "nivel": (
                    NIVEL_COMPLETA
                    if avance >= 100
                    else NIVEL_MEDIA
                    if avance >= 50
                    else NIVEL_BAJA
                ),
            }
        )
    return resultado


def progreso_por_id(db: Session, metas: list[Meta]) -> dict[int, dict]:
    return {fila["meta"].id: fila for fila in progreso_metas(db, metas)}


def metas_vencidas(metas: list[Meta], hoy: date) -> list[dict]:
    """Metas activas cuya fecha limite ya paso, con los dias de atraso."""
    vencidas = [
        {"meta": meta, "dias": (hoy - meta.fecha_limite).days}
        for meta in metas
        if meta.estado == "activa"
        and meta.fecha_limite is not None
        and meta.fecha_limite < hoy
    ]
    vencidas.sort(key=lambda item: item["dias"], reverse=True)
    return vencidas
