# --------------------------------------------------------------------------
# Integridad de datos (Fase 2)
# --------------------------------------------------------------------------

from datetime import date, timedelta
from urllib.parse import unquote

from helpers import (
    _id_meta,
    _usuario_id,
    login,
)

from app import config
from app.database import SessionLocal
from app.models import Meta, Registro


def test_no_se_puede_cargar_en_el_futuro(client):
    assert login(client, "jefe", "1234").status_code == 303
    respuesta = client.post(
        "/registros",
        data={
            "descripcion": "Tarea de manana",
            "fecha": (date.today() + timedelta(days=1)).isoformat(),
        },
        follow_redirects=False,
    )
    assert "fecha%20futura" in respuesta.headers["location"]


def test_no_se_puede_cargar_fuera_del_rango(client):
    assert login(client, "jefe", "1234").status_code == 303
    tarde = (date.today() - timedelta(days=config.DIAS_ATRASO + 1)).isoformat()
    respuesta = client.post(
        "/registros",
        data={"descripcion": "Del ano pasado", "fecha": tarde},
        follow_redirects=False,
    )
    assert "Fuera%20de%20rango" in respuesta.headers["location"]

    # Justo en el limite: se acepta.
    limite = (date.today() - timedelta(days=config.DIAS_ATRASO)).isoformat()
    ok = client.post(
        "/registros",
        data={"descripcion": "Ultimo dia valido", "fecha": limite},
        follow_redirects=False,
    )
    assert "Registro%20guardado" in ok.headers["location"]


def test_un_solo_reporte_por_dia_y_meta(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta diaria"})
    meta_id = _id_meta("Meta diaria")

    primera = client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "un trabajo"},
        follow_redirects=False,
    )
    assert "Registro%20guardado" in primera.headers["location"]

    duplicado = client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "otro trabajo"},
        follow_redirects=False,
    )
    assert "Ya%20hay%20un%20registro" in duplicado.headers["location"]

    # Sin meta tambien aplica, aunque el indice unico no cubre los NULL.
    dia_prueba = date.today() - timedelta(days=25)
    db = SessionLocal()
    try:
        jefe = _usuario_id("jefe")
        db.query(Registro).filter_by(
            usuario_id=jefe, fecha=dia_prueba, meta_id=None
        ).delete()
        db.commit()
    finally:
        db.close()

    libre = client.post(
        "/registros",
        data={"descripcion": "sin meta", "fecha": dia_prueba.isoformat()},
        follow_redirects=False,
    )
    assert "Registro%20guardado" in libre.headers["location"]
    libre_dup = client.post(
        "/registros",
        data={"descripcion": "sin meta otra vez", "fecha": dia_prueba.isoformat()},
        follow_redirects=False,
    )
    assert "Ya%20hay%20un%20registro" in libre_dup.headers["location"]


def test_no_se_puede_reportar_sobre_una_meta_ajena(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/metas",
        data={"titulo": "Meta solo del jefe", "asignado_a": str(_usuario_id("jefe"))},
    )
    client.post(
        "/metas",
        data={"titulo": "Meta solo de Maria", "asignado_a": str(_usuario_id("mperez"))},
    )
    ajena = _id_meta("Meta solo del jefe")
    propia = _id_meta("Meta solo de Maria")

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303

    denegado = client.post(
        "/registros",
        data={"meta_id": str(ajena), "descripcion": "me meto en la ajena"},
        follow_redirects=False,
    )
    assert "no%20te%20corresponde" in denegado.headers["location"]

    propia_ok = client.post(
        "/registros",
        data={"meta_id": str(propia), "descripcion": "mi trabajo"},
        follow_redirects=False,
    )
    assert "Registro%20guardado" in propia_ok.headers["location"]

    # Una meta sin asignar es de todo el equipo.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta de todos"})
    equipo = _id_meta("Meta de todos")
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    libre = client.post(
        "/registros",
        data={"meta_id": str(equipo), "descripcion": "para todos"},
        follow_redirects=False,
    )
    assert "Registro%20guardado" in libre.headers["location"]


def test_archivar_meta_conserva_los_reportes(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta a archivar"})
    meta_id = _id_meta("Meta a archivar")

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "avance"},
        follow_redirects=False,
    )

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    archivar = client.post(f"/metas/{meta_id}/eliminar", follow_redirects=False)
    assert archivar.status_code == 303
    assert "archivada" in unquote(archivar.headers["location"])

    db = SessionLocal()
    try:
        meta = db.get(Meta, meta_id)
        assert meta.estado == "eliminada"
        assert db.query(Registro).filter_by(meta_id=meta_id).count() == 1
    finally:
        db.close()

    # Sigue visible para el jefe, marcada y con la opcion de restaurar.
    pagina = client.get("/metas")
    assert "archivada" in pagina.text
    assert "Restaurar" in pagina.text

    # El empleado ya no la puede elegir para cargar (en su lista de metas si
    # aparece, porque el reporte viejo conserva el vinculo).
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    panel = client.get("/")
    assert f'<option value="{meta_id}"' not in panel.text
    assert "Meta a archivar" in panel.text

    # Se restaura y vuelve a aparecer.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    restaurar = client.post(
        f"/metas/{meta_id}/estado", data={"estado": "activa"}, follow_redirects=False
    )
    assert restaurar.status_code == 303

    db = SessionLocal()
    try:
        assert db.get(Meta, meta_id).estado == "activa"
    finally:
        db.close()
    assert "Meta a archivar" in client.get("/metas").text


def test_el_indice_unico_no_rompe_si_hay_duplicados_viejos():
    """Una base de la oficina puede traer duplicados previos: avisa y sigue."""
    from sqlalchemy import create_engine

    from app.migraciones import _asegurar_indice_unico

    motor = create_engine("sqlite://")
    with motor.begin() as conexion:
        conexion.exec_driver_sql("CREATE TABLE usuarios (id INTEGER, nombre TEXT)")
        conexion.exec_driver_sql("INSERT INTO usuarios VALUES (1, 'Maria')")
        conexion.exec_driver_sql(
            "CREATE TABLE registros (usuario_id INTEGER, fecha DATE, meta_id INTEGER)"
        )
        conexion.exec_driver_sql("INSERT INTO registros VALUES (1, '2026-09-01', 7)")
        conexion.exec_driver_sql("INSERT INTO registros VALUES (1, '2026-09-01', 7)")
        _asegurar_indice_unico(conexion)
        nombres = {
            fila[0]
            for fila in conexion.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "ix_registros_unico" not in nombres

    motor = create_engine("sqlite://")
    with motor.begin() as conexion:
        conexion.exec_driver_sql("CREATE TABLE usuarios (id INTEGER, nombre TEXT)")
        conexion.exec_driver_sql(
            "CREATE TABLE registros (usuario_id INTEGER, fecha DATE, meta_id INTEGER)"
        )
        _asegurar_indice_unico(conexion)
        nombres = {
            fila[0]
            for fila in conexion.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "ix_registros_unico" in nombres


