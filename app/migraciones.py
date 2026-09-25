"""Migraciones livianas.

`create_all` crea tablas que no existen, pero no agrega columnas a tablas ya
creadas. Como el sistema ya puede estar instalado en la oficina, acá se agregan
las columnas nuevas sin perder datos.
"""

import logging

from .database import engine

logger = logging.getLogger(__name__)

# (tabla, columna, definicion SQL)
COLUMNAS_NUEVAS = [
    ("registros", "comentario", "TEXT DEFAULT ''"),
    ("registros", "comentado_en", "DATETIME"),
    ("metas", "horas_estimadas", "FLOAT DEFAULT 0"),
]


def aplicar_migraciones() -> None:
    with engine.begin() as conexion:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            existentes = {
                fila[1]
                for fila in conexion.exec_driver_sql(f"PRAGMA table_info({tabla})")
            }
            if not existentes:
                # La tabla todavia no existe: la crea create_all().
                continue
            if columna not in existentes:
                logger.info("Agregando columna %s.%s", tabla, columna)
                conexion.exec_driver_sql(
                    f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
                )

