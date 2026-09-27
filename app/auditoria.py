"""Auditoria: deja registro de las acciones que cambian o borran datos."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Auditoria, Usuario


def registrar(
    db: Session,
    usuario: Usuario | None,
    accion: str,
    objeto_tipo: str = "",
    objeto_id: int | None = None,
    resumen: str = "",
) -> None:
    """Agrega una fila a la auditoria.

    No hace commit: la fila entra en la misma transaccion que la accion, asi
    o quedan las dos o no queda ninguna. Quien restaure un respaldo tiene que
    llamarlo despues, con una sesion nueva, porque la base cambio abajo.
    """
    db.add(
        Auditoria(
            usuario_id=usuario.id if usuario is not None else None,
            accion=accion,
            objeto_tipo=objeto_tipo,
            objeto_id=objeto_id,
            resumen=resumen.strip()[:255],
        )
    )
