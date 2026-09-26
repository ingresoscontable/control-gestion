"""Respaldos de la base de datos.

Se usa la API de respaldo de SQLite (no una copia de archivo) para que la
copia quede consistente aunque alguien esté escribiendo en ese momento.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from . import config
from .database import DB_PATH, engine
from .migraciones import aplicar_migraciones

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


def _verificar_sqlite(ruta: Path) -> None:
    """Abre el archivo y lo valida. Lanza ValueError si no sirve."""
    try:
        conexion = sqlite3.connect(str(ruta))
    except sqlite3.Error as error:
        raise ValueError(f"no se pudo abrir el archivo ({error})") from error
    try:
        try:
            fila = conexion.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as error:
            raise ValueError(f"el archivo no es una base sqlite valida ({error})") from error
        if not fila or fila[0] != "ok":
            raise ValueError("el archivo esta corrupto")
        tablas = {
            registro[0]
            for registro in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"usuarios", "metas", "registros"} <= tablas:
            raise ValueError("el archivo no es una base de Control de Gestion")
    finally:
        conexion.close()


def respaldos_en_mismo_disco() -> bool:
    """True si los respaldos caen en el mismo disco que la base de datos.

    En ese caso una falla de disco se lleva la base y las copias juntas, asi
    que la pagina de respaldos lo avisa.
    """
    try:
        return DB_PATH.stat().st_dev == asegurar_carpeta().stat().st_dev
    except OSError:
        return False


def _reemplazar(origen: Path, destino: Path) -> None:
    """Muelve encima de la base esperando a que se liberen los bloqueos.

    En Windows no se puede reemplazar un archivo que este abierto. Si en ese
    exacto momento alguien mas esta usando el sistema, se reintenta un par de
    veces antes de rendirse.
    """
    ultimo_error: OSError | None = None
    for intento in range(6):
        try:
            origen.replace(destino)
            return
        except OSError as error:
            ultimo_error = error
            if intento < 5:
                time.sleep(0.3)
    raise ValueError(
        "la base esta ocupada en este momento, intente de nuevo en unos segundos"
    ) from ultimo_error


def restaurar_respaldo(nombre: str) -> Path:
    """Reemplaza la base actual por un respaldo guardado.

    Antes de tocar nada deja un respaldo de seguridad del estado actual y
    valida el archivo elegido. El reemplazo es atomico: si falla a mitad de
    camino, la base sigue quedando como estaba.
    """
    carpeta = asegurar_carpeta().resolve()
    origen = (carpeta / nombre).resolve()

    # Solo archivos de esta carpeta y con el formato que genera el sistema.
    if origen.parent != carpeta:
        raise ValueError("Ese archivo no esta en la carpeta de respaldos")
    if not origen.is_file():
        raise ValueError("Ese respaldo ya no existe")
    if not origen.name.startswith("control_") or not origen.name.endswith(".db"):
        raise ValueError("Ese archivo no es un respaldo de Control de Gestion")

    _verificar_sqlite(origen)
    seguridad = crear_respaldo(etiqueta="antes-de-restaurar")

    # Se cierran las conexiones abiertas por el pool.
    engine.dispose()
    temporal = DB_PATH.with_name(DB_PATH.name + ".restaurando")
    try:
        shutil.copyfile(origen, temporal)
        _verificar_sqlite(temporal)
        _reemplazar(temporal, DB_PATH)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise

    # La base restaurada puede ser mas vieja que el codigo: se agregan las
    # columnas que falten.
    engine.dispose()
    aplicar_migraciones()
    logger.info("Base restaurada desde %s", origen.name)
    return seguridad


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
