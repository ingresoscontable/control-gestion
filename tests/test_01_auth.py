

from helpers import (
    login,
)

from app import seed
from app.database import SessionLocal
from app.models import Usuario
from app.security import hash_pin


def test_login_sin_sesion_redirige(client):
    respuesta = client.get("/", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"


def test_pin_incorrecto_no_inicia_sesion(client):
    respuesta = login(client, "jefe", "0000")
    assert respuesta.status_code == 401
    assert "incorrecto" in respuesta.text


def test_pin_se_guarda_hasheado(client):
    db = SessionLocal()
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        assert jefe.pin_hash != "1234"
        assert jefe.pin_hash.startswith("pbkdf2$")
    finally:
        db.close()


def test_jefe_entra_y_ve_su_panel(client):
    assert login(client, "jefe", "1234").status_code == 303
    panel = client.get("/")
    assert panel.status_code == 200
    assert "Resumen de hoy" in panel.text


def test_primer_ingreso_se_borra_cuando_el_jefe_cambia_su_pin(client):
    ruta = seed.guardar_primer_ingreso("jefe", "9876")
    assert ruta.is_file()
    assert "9876" in ruta.read_text(encoding="utf-8")

    login(client, "jefe", "1234")
    cambio = client.post(
        "/mi-pin",
        data={"pin_actual": "1234", "pin_nuevo": "5678"},
        follow_redirects=False,
    )
    assert cambio.status_code == 303
    assert not ruta.exists()

    db = SessionLocal()
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        jefe.pin_hash = hash_pin("1234")
        db.commit()
    finally:
        db.close()


