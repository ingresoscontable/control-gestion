"""Migraciones livianas.

`create_all` crea tablas que no existen, pero no agrega columnas a tablas ya
creadas ni indices a tablas ya creadas. Como el sistema ya puede estar
instalado en la oficina, acá se agregan las columnas y los indices nuevos sin
perder datos.
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

# (nombre, tabla, columnas). Solo se crean si la tabla ya tiene esas columnas,
# asi una base vieja a medio migrar no rompe el arranque.
INDICES_NUEVOS = [
    ("ix_registros_fecha", "registros", ["fecha"]),
    ("ix_registros_usuario_fecha", "registros", ["usuario_id", "fecha"]),
    ("ix_metas_estado_fecha_limite", "metas", ["estado", "fecha_limite"]),
]


def _columnas(conexion, tabla: str) -> set[str]:
    return {
        fila[1] for fila in conexion.exec_driver_sql(f"PRAGMA table_info({tabla})")
    }


def _registros_duplicados(conexion) -> tuple[int, list]:
    """Grupos (usuario, fecha, meta) con mas de un reporte, con su conteo."""
    filas = conexion.exec_driver_sql(
        """SELECT u.nombre, r.fecha, r.meta_id, COUNT(*) AS n
           FROM registros r
           JOIN usuarios u ON u.id = r.usuario_id
           GROUP BY r.usuario_id, r.fecha, r.meta_id
           HAVING COUNT(*) > 1
           ORDER BY n DESC"""
    ).fetchall()
    return len(filas), filas


def _asegurar_indice_unico(conexion) -> None:
    """Crea el indice unico solo si no hay duplicados guardados.

    La aplicacion ya no deja cargar duplicados, pero una base de la oficina
    puede tener algunos viejos (doble clic, "Repetir" seguido). Antes de
    romper el arranque con un IntegrityError se listan en el log y se deja
    el indice para el proximo arranque, cuando ya esten depurados.
    """
    columnas = {"usuario_id", "fecha", "meta_id"}
    if not set(columnas) <= _columnas(conexion, "registros"):
        return
    total, filas = _registros_duplicados(conexion)
    if total:
        for nombre, fecha, meta_id, cantidad in filas[:10]:
            logger.warning(
                "Duplicado: %s cargo %s veces el %s para la meta %s",
                nombre,
                cantidad,
                fecha,
                meta_id if meta_id is not None else "sin meta",
            )
        logger.warning(
            "Indice unico ix_registros_unico NO creado: %s reportes duplicados "
            "(usuario, fecha, meta). Borra los de mas desde Registros y al "
            "reiniciar se crea solo.",
            total,
        )
        return
    logger.info("Asegurando indice ix_registros_unico en registros")
    conexion.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_registros_unico "
        "ON registros (usuario_id, fecha, meta_id)"
    )


def aplicar_migraciones() -> None:
    with engine.begin() as conexion:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            existentes = _columnas(conexion, tabla)
            if not existentes:
                # La tabla todavia no existe: la crea create_all().
                continue
            if columna not in existentes:
                logger.info("Agregando columna %s.%s", tabla, columna)
                conexion.exec_driver_sql(
                    f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
                )

        for nombre, tabla, columnas in INDICES_NUEVOS:
            existentes = _columnas(conexion, tabla)
            if not existentes or not set(columnas) <= existentes:
                continue
            logger.info("Asegurando indice %s en %s", nombre, tabla)
            conexion.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} ({', '.join(columnas)})"
            )

        _asegurar_indice_unico(conexion)
