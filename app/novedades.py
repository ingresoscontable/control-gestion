"""Novedades que bajan los dias esperados de una persona.

Una novedad (vacaciones, licencia, feriado) saca dias del cumplimiento: quien
estuvo de licencia no es un incumplidor.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .jornada import es_laborable
from .models import OPCIONES_NOVEDAD, Novedad


def etiqueta(tipo: str) -> str:
    """Nombre del tipo de novedad (por si llega un valor viejo o raro)."""
    from .models import TIPOS_NOVEDAD

    return dict(TIPOS_NOVEDAD).get(tipo, tipo)


def novedades_del_rango(db: Session, desde: date, hasta: date) -> list[Novedad]:
    """Novedades cargadas que tocan el rango, de la mas nueva a la mas vieja."""
    return list(
        db.scalars(
            select(Novedad)
            .where(Novedad.desde <= hasta, Novedad.hasta >= desde)
            .options(*OPCIONES_NOVEDAD)
            .order_by(Novedad.desde.desc(), Novedad.id.desc())
        )
    )


def _tocan_a(usuario_id: int):
    """Novedades propias o de todo el equipo."""
    return or_(Novedad.usuario_id.is_(None), Novedad.usuario_id == usuario_id)


def dias_de_novedad(db: Session, usuario_id: int, desde: date, hasta: date) -> int:
    """Dias laborables del rango que esa persona tiene cubiertos por novedades."""
    filas = list(
        db.scalars(
            select(Novedad).where(
                Novedad.desde <= hasta,
                Novedad.hasta >= desde,
                _tocan_a(usuario_id),
            )
        )
    )
    cubiertos: set[date] = set()
    for novedad in filas:
        dia = max(desde, novedad.desde)
        fin = min(hasta, novedad.hasta)
        while dia <= fin:
            if es_laborable(dia):
                cubiertos.add(dia)
            dia += timedelta(days=1)
    return len(cubiertos)


def laborables_del_rango(
    db: Session, usuario_id: int, desde: date, hasta: date, total: int
) -> int:
    """Dias laborables que le quedan despues de descontar sus novedades."""
    return max(0, total - dias_de_novedad(db, usuario_id, desde, hasta))


def hay_novedad(db: Session, usuario_id: int, dia: date) -> bool:
    """Si ese dia a esa persona no se le exige reportar."""
    return (
        db.scalar(
            select(Novedad.id).where(
                Novedad.desde <= dia,
                Novedad.hasta >= dia,
                _tocan_a(usuario_id),
            )
        )
        is not None
    )
