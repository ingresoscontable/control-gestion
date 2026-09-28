from datetime import date
from urllib.parse import unquote

from helpers import (
    login,
)

from app.database import SessionLocal
from app.models import Usuario


def test_flujo_completo_jefe_y_empleado(client):
    assert login(client, "jefe", "1234").status_code == 303

    # El jefe crea dos accesos, uno con PIN inválido (debe rebotar).
    assert (
        client.post(
            "/equipo",
            data={"nombre": "Maria Perez", "usuario": "mperez", "pin": "12", "rol": "empleado"},
            follow_redirects=False,
        ).headers["location"]
        .startswith("/equipo")
    )
    assert client.post(
        "/equipo",
        data={
            "nombre": "Maria Perez",
            "usuario": "mperez",
            "cargo": "Analista contable",
            "pin": "4821",
            "rol": "empleado",
        },
        follow_redirects=False,
    ).status_code == 303

    # El jefe crea una meta asignada a Maria.
    db = SessionLocal()
    try:
        maria = db.query(Usuario).filter_by(usuario="mperez").one()
        maria_id = maria.id
    finally:
        db.close()

    assert client.post(
        "/metas",
        data={
            "titulo": "Conciliacion bancaria septiembre",
            "descripcion": "Cerrar la conciliacion del mes",
            "asignado_a": str(maria_id),
            "fecha_limite": "2026-10-05",
        },
        follow_redirects=False,
    ).status_code == 303
    assert "Conciliacion bancaria septiembre" in client.get("/metas").text

    # Maria entra y registra su trabajo del dia.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303

    panel = client.get("/")
    assert "Conciliacion bancaria septiembre" in panel.text

    assert client.post(
        "/registros",
        data={
            "descripcion": "Revisadas 40 facturas pendientes",
            "horas": "6,5",
            "estado": "en_progreso",
            "fecha": date.today().isoformat(),
        },
        follow_redirects=False,
    ).status_code == 303

    panel = client.get("/")
    assert "Revisadas 40 facturas pendientes" in panel.text

    # Un empleado no puede administrar metas ni ver el equipo.
    assert client.get("/metas", follow_redirects=False).headers["location"].startswith("/?msg=")
    assert client.get("/equipo", follow_redirects=False).headers["location"].startswith("/?msg=")


def test_jefe_ve_registros_y_horas(client):
    assert login(client, "jefe", "1234").status_code == 303
    respuesta = client.get("/registros")
    assert respuesta.status_code == 200
    assert "Revisadas 40 facturas pendientes" in respuesta.text
    assert "6.5 horas acumuladas" in respuesta.text


def test_texto_vacio_no_crea_registro(client):
    assert login(client, "jefe", "1234").status_code == 303
    respuesta = client.post(
        "/registros", data={"descripcion": "   "}, follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert "no puede estar vacía" in unquote(respuesta.headers["location"])


