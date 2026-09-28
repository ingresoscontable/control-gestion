# --------------------------------------------------------------------------
# Fase 1: base de datos (WAL, indices, totales, respaldos)
# --------------------------------------------------------------------------
from datetime import date, timedelta

import pytest
from helpers import (
    login,
)

from app import backup, config
from app.database import SessionLocal
from app.models import Meta, Registro, Usuario


def test_base_trabaja_en_modo_wal():
    from sqlalchemy import text

    db = SessionLocal()
    try:
        modo = db.execute(text("PRAGMA journal_mode")).scalar()
    finally:
        db.close()
    assert modo == "wal"


def test_indices_creados_en_la_base():
    import sqlite3

    conexion = sqlite3.connect(str(config.DATA_DIR / "control.db"))
    try:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    finally:
        conexion.close()
    assert {
        "ix_registros_fecha",
        "ix_registros_usuario_fecha",
        "ix_registros_unico",
        "ix_metas_estado_fecha_limite",
    } <= nombres


def test_totales_no_se_cortan_con_el_limite_de_la_lista(client):
    """La lista pagina de 50 en 50, pero el total tiene que contar todas."""
    db = SessionLocal()
    creados = []
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        existentes = db.query(Registro).all()
        antes = len(existentes)
        horas_antes = sum(r.horas for r in existentes)
        for i in range(505):
            registro = Registro(
                usuario_id=jefe.id,
                fecha=date.today() - timedelta(days=i % 30),
                descripcion=f"trabajo de prueba {i}",
                horas=1.0,
                estado="completado",
            )
            db.add(registro)
            creados.append(registro)
        db.commit()
        ids = [r.id for r in creados]
    finally:
        db.close()

    try:
        assert login(client, "jefe", "1234").status_code == 303
        total = antes + 505
        pagina = client.get("/registros")
        assert pagina.status_code == 200
        assert f"{total} registro(s)" in pagina.text
        assert f"{horas_antes + 505.0:.1f} horas acumuladas" in pagina.text
        assert f"repartidos en {-(-total // 50)} página(s) de 50" in pagina.text
        # Una sola pantalla: encabezado + 50 filas.
        assert pagina.text.count("<tr>") == 51

        segunda = client.get("/registros", params={"page": "2"})
        assert segunda.status_code == 200
        assert "Página 2 de" in segunda.text
        # Pedir una pagina fuera de rango no rompe nada: se acomoda.
        lejana = client.get("/registros", params={"page": "99999"})
        assert lejana.status_code == 200
    finally:
        db = SessionLocal()
        try:
            db.query(Registro).filter(Registro.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()


def test_exportar_no_hace_una_consulta_por_fila(client):
    """La exportacion no trae metas ni usuarios aparte: sin eager loading
    cada fila dispararia su propia consulta para leer la meta."""
    from sqlalchemy import event

    from app.database import engine

    db = SessionLocal()
    creados = []
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        for i in range(40):
            meta = Meta(
                titulo=f"Meta carga rapida {i}",
                fecha_limite=date.today(),
                horas_estimadas=0.0,
            )
            db.add(meta)
            db.flush()
            registro = Registro(
                usuario_id=jefe.id,
                meta_id=meta.id,
                fecha=date.today(),
                descripcion=f"carga rapida {i}",
                horas=1.0,
                estado="en_progreso",
            )
            db.add(registro)
            creados.append(registro)
        db.commit()
        ids_registros = [r.id for r in creados]
        ids_metas = [r.meta_id for r in creados]
    finally:
        db.close()

    consultas: list[str] = []

    def contar(_conexion, _cursor, sentencia, _parametros, _contexto, _muchos):
        consultas.append(sentencia)

    assert login(client, "jefe", "1234").status_code == 303
    event.listen(engine, "before_cursor_execute", contar)
    try:
        export = client.get("/registros/exportar.xlsx")
    finally:
        event.remove(engine, "before_cursor_execute", contar)
        db = SessionLocal()
        try:
            db.query(Registro).filter(Registro.id.in_(ids_registros)).delete(
                synchronize_session=False
            )
            db.query(Meta).filter(Meta.id.in_(ids_metas)).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

    assert export.status_code == 200
    assert len(consultas) < 15


def test_respaldo_invalido_se_borra_y_no_queda_en_la_lista(client, monkeypatch):
    carpeta = backup.asegurar_carpeta()

    def romper(_ruta):
        raise ValueError("el archivo esta corrupto")

    monkeypatch.setattr(backup, "_verificar_sqlite", romper)
    with pytest.raises(ValueError):
        backup.crear_respaldo(etiqueta="malo")

    assert not list(carpeta.glob("*_malo.db"))


def test_borrar_archivos_wal_quita_los_dos(tmp_path, monkeypatch):
    base = tmp_path / "control.db"
    monkeypatch.setattr(backup, "DB_PATH", base)
    wal = tmp_path / "control.db-wal"
    shm = tmp_path / "control.db-shm"
    wal.write_text("viejo", encoding="utf-8")
    shm.write_text("viejo", encoding="utf-8")

    backup._borrar_archivos_wal()

    assert not wal.exists()
    assert not shm.exists()


def test_restaurar_saca_los_archivos_wal(client, monkeypatch):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/respaldos/ahora", follow_redirects=False)
    respaldo = max(
        config.BACKUP_DIR.glob("control_*_manual.db"),
        key=lambda ruta: ruta.stat().st_mtime,
    )

    llamadas = []
    monkeypatch.setattr(
        backup, "_borrar_archivos_wal", lambda: llamadas.append(True)
    )
    respuesta = client.post(
        "/respaldos/restaurar", data={"nombre": respaldo.name}, follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert llamadas


