"""Respaldos de la base de datos.

Se usa la API de respaldo de SQLite (no una copia de archivo) para que la
copia quede consistente aunque alguien esté escribiendo en ese momento.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config
from .database import DB_PATH

logger = logging.getLogger(__name__)


def asegurar_carpeta() -> Path:
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return config.BACKUP_DIR


def crear_respaldo(etiqueta: str = "") -> Path:
    """Crea una copia de la base y devuelve la ruta del archivo generado."""
    carpeta = asegurar_carpeta()
    sufijo = f"_{etiqueta}" if etiqueta else ""
    destino = carpeta / f"control_{datetime.now():%Y%m%d_%H%M%S}{sufijo}.db"

    origen = sqlite3.connect(str(DB_PATH))
    try:
        copia = sqlite3.connect(str(destino))
        try:
            with copia:
                origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()

    logger.info("Respaldo creado: %s", destino.name)
    return destino


def limpiar_respaldos_antiguos() -> list[Path]:
    """Borra los respaldos mas viejos, conservando los ultimos N."""
    respaldos = listar_respaldos()  # ya vienen del mas nuevo al mas viejo
    borrados: list[Path] = []
    for item in respaldos[config.BACKUP_CONSERVAR:]:
        try:
            item["ruta"].unlink()
            borrados.append(item["ruta"])
        except OSError:
            logger.warning("No se pudo borrar el respaldo %s", item["ruta"])
    return borrados


def listar_respaldos() -> list[dict]:
    """Lista los respaldos existentes, del mas reciente al mas antiguo."""
    carpeta = asegurar_carpeta()
    items = []
    for archivo in carpeta.glob("control_*.db"):
        try:
            estadistica = archivo.stat()
        except OSError:
            continue
        items.append(
            {
                "nombre": archivo.name,
                "ruta": archivo,
                "tamano_kb": estadistica.st_size / 1024,
                "fecha": datetime.fromtimestamp(estadistica.st_mtime),
            }
        )
    items.sort(key=lambda i: i["fecha"], reverse=True)
    return items


async def respaldo_periodico() -> None:
    """Crea un respaldo al arrancar y luego cada BACKUP_HORAS horas."""
    while True:
        try:
            crear_respaldo()
            limpiar_respaldos_antiguos()
        except Exception:  # noqa: BLE001 - un fallo de respaldo no debe tumbar la app
            logger.exception("No se pudo crear el respaldo automatico")
        await asyncio.sleep(max(1, config.BACKUP_HORAS) * 3600)
