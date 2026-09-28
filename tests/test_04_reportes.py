from datetime import date

from helpers import (
    _id_registro_de,
    login,
)

from app import config


def test_comentario_del_jefe(client):
    registro_id = _id_registro_de("mperez")

    # Un empleado no puede comentar.
    assert login(client, "mperez", "4821").status_code == 303
    assert client.post(
        f"/registros/{registro_id}/comentario",
        data={"comentario": "comentario indebido"},
        follow_redirects=False,
    ).headers["location"].startswith("/?msg=")

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303

    aviso = "Buen avance, revisar el IVA del periodo."
    respuesta = client.post(
        f"/registros/{registro_id}/comentario",
        data={"comentario": aviso, "volver": "/registros"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/registros?msg=Comentario%20guardado"
    assert aviso in client.get("/registros").text
    assert aviso in client.get("/").text

    # El empleado lo ve en su panel (sin formulario para editar).
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    panel = client.get("/")
    assert aviso in panel.text
    assert f"/registros/{registro_id}/comentario" not in panel.text

    # Un comentario vacío lo borra.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    assert client.post(
        f"/registros/{registro_id}/comentario",
        data={"comentario": "   ", "volver": "/registros"},
        follow_redirects=False,
    ).status_code == 303
    assert aviso not in client.get("/registros").text


def test_reporte_mensual_pdf(client):
    assert login(client, "jefe", "1234").status_code == 303
    hoy = date.today()

    respuesta = client.get(
        "/reportes/mensual.pdf", params={"anio": hoy.year, "mes": hoy.month}
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
    assert len(respuesta.content) > 2000
    assert f"reporte_{hoy.year}-{hoy.month:02d}.pdf" in respuesta.headers[
        "content-disposition"
    ]

    # Un mes sin datos tambien genera un PDF valido.
    vacio = client.get("/reportes/mensual.pdf", params={"anio": 2000, "mes": 1})
    assert vacio.status_code == 200
    assert vacio.content.startswith(b"%PDF")

    # Periodo invalido.
    assert client.get(
        "/reportes/mensual.pdf", params={"mes": "13"}, follow_redirects=False
    ).headers["location"].startswith("/registros?msg=")

    # Un empleado no puede bajarlo.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get(
        "/reportes/mensual.pdf", follow_redirects=False
    ).headers["location"].startswith("/?msg=")


def test_respaldos_automaticos_y_manuales(client):
    assert login(client, "jefe", "1234").status_code == 303

    # El respaldo automatico se crea al arrancar la aplicacion.
    automaticos = list(config.BACKUP_DIR.glob("control_*.db"))
    assert automaticos

    assert client.post("/respaldos/ahora", follow_redirects=False).status_code == 303
    todos = list(config.BACKUP_DIR.glob("control_*.db"))
    assert len(todos) == len(automaticos) + 1
    assert any(archivo.name.endswith("_manual.db") for archivo in todos)

    pagina = client.get("/respaldos")
    assert pagina.status_code == 200
    assert "Respaldos existentes" in pagina.text

    # Un empleado no entra a respaldos.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get(
        "/respaldos", follow_redirects=False
    ).headers["location"].startswith("/?msg=")


