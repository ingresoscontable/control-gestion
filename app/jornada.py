"""Reglas del calendario laboral: que dias cuentan como laborables.

Vive aparte de `metricas` y `novedades` para que las dos puedan usarlo sin
importarse entre si.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import config


def es_laborable(dia: date) -> bool:
    """Si ese dia cuenta como laborable segun CG_DIAS_LABORABLES."""
    return dia.isoweekday() in config.DIAS_LABORABLES


def dias_laborables(desde: date, hasta: date) -> int:
    """Cuantos dias laborables hay en el rango (inclusive)."""
    if hasta < desde:
        return 0
    return sum(
        1
        for i in range((hasta - desde).days + 1)
        if es_laborable(desde + timedelta(days=i))
    )


def describir_dias(dias: tuple[int, ...]) -> str:
    """Nombre legible de los dias laborables, para la documentacion."""
    nombres = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return ", ".join(nombres[dia - 1] for dia in sorted(dias))
