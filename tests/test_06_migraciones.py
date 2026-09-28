import tempfile
from pathlib import Path

from app import migraciones


def test_migracion_agrega_columnas_a_una_base_vieja():
    import sqlite3

    from sqlalchemy import create_engine

    carpeta = Path(tempfile.mkdtemp(prefix="cg-migracion-"))
    archivo = carpeta / "viejo.db"

    conexion = sqlite3.connect(archivo)
    conexion.execute("CREATE TABLE registros (id INTEGER PRIMARY KEY, descripcion TEXT)")
    conexion.execute("CREATE TABLE metas (id INTEGER PRIMARY KEY, titulo TEXT)")
    conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, usuario TEXT)")
    conexion.execute("INSERT INTO usuarios (usuario) VALUES ('jefe')")
    conexion.commit()
    conexion.close()

    motor = create_engine(f"sqlite:///{archivo}")
    original = migraciones.engine
    migraciones.engine = motor
    try:
        migraciones.aplicar_migraciones()
    finally:
        migraciones.engine = original

    conexion = sqlite3.connect(archivo)
    try:
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(registros)")}
        columnas_metas = {
            fila[1] for fila in conexion.execute("PRAGMA table_info(metas)")
        }
        columnas_usuarios = {
            fila[1] for fila in conexion.execute("PRAGMA table_info(usuarios)")
        }
        token = conexion.execute(
            "SELECT sesion_token FROM usuarios WHERE usuario = 'jefe'"
        ).fetchone()[0]
    finally:
        conexion.close()
    assert {"comentario", "comentado_en"} <= columnas
    assert {
        "estado_revision",
        "revisado_por",
        "revisado_en",
        "observacion_revision",
    } <= columnas
    assert "horas_estimadas" in columnas_metas
    # El token se agrega y se completa: sin backfill las sesiones viejas
    # quedarian con NULL y la comprobacion no podria aplicarse.
    assert "sesion_token" in columnas_usuarios
    assert token


