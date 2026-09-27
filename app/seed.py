"""Datos iniciales: crea el usuario jefe la primera vez que arranca."""

import logging
from pathlib import Path

from . import config
from .database import SessionLocal
from .models import ROL_JEFE, Usuario
from .security import hash_pin

logger = logging.getLogger(__name__)

# Credenciales del primer ingreso. Se guardan en un archivo aparte (y no en el
# log del sistema) para que quien instala pueda volver a leerlas, y se borra
# solas apenas el jefe cambia el PIN.
ARCHIVO_INGRESO = config.DATA_DIR / "primer-ingreso.txt"


def guardar_primer_ingreso(usuario: str, pin: str) -> Path:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVO_INGRESO.write_text(
            "Primer ingreso al sistema (cambie el PIN apenas entre):\n"
            f"\n  Usuario: {usuario}\n"
            f"  PIN:     {pin}\n"
            "\nEste archivo se borra solo cuando se cambia el PIN.\n",
            encoding="utf-8",
        )
    except OSError as error:
        logger.warning("No se pudo escribir %s (%s)", ARCHIVO_INGRESO, error)
    return ARCHIVO_INGRESO


def borrar_primer_ingreso() -> None:
    """Queda sin efecto el aviso de primer ingreso cuando ya no sirve."""
    try:
        ARCHIVO_INGRESO.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("No se pudo borrar %s (%s)", ARCHIVO_INGRESO, error)


def crear_datos_iniciales() -> None:
    db = SessionLocal()
    try:
        if db.query(Usuario).count() > 0:
            return
        jefe = Usuario(
            nombre=config.ADMIN_NOMBRE,
            usuario=config.ADMIN_USUARIO,
            pin_hash=hash_pin(config.ADMIN_PIN),
            rol=ROL_JEFE,
            cargo="Jefe de División",
        )
        db.add(jefe)
        db.commit()
        ruta = guardar_primer_ingreso(config.ADMIN_USUARIO, config.ADMIN_PIN)
        logger.warning(
            "Usuario jefe creado -> usuario: %s (PIN inicial en %s)",
            config.ADMIN_USUARIO,
            ruta,
        )
    finally:
        db.close()
