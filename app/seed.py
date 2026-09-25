"""Datos iniciales: crea el usuario jefe la primera vez que arranca."""

import logging

from . import config
from .database import SessionLocal
from .models import ROL_JEFE, Usuario
from .security import hash_pin

logger = logging.getLogger(__name__)


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
        logger.warning(
            "Usuario jefe creado -> usuario: %s | PIN: %s  (cámbialo al entrar)",
            config.ADMIN_USUARIO,
            config.ADMIN_PIN,
        )
    finally:
        db.close()
