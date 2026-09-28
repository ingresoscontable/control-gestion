from datetime import date

from helpers import (
    _id_meta,
    _id_usuario,
    login,
)

from app.database import SessionLocal
from app.models import Meta


def test_alerta_de_metas_vencidas(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/metas",
        data={
            "titulo": "Presentar declaracion atrasada",
            "asignado_a": str(_id_usuario("mperez")),
            "fecha_limite": "2020-01-31",
        },
        follow_redirects=False,
    )

    panel = client.get("/")
    assert "meta(s) con el plazo vencido" in panel.text
    assert "Presentar declaracion atrasada" in panel.text
    assert "de atraso" in panel.text

    # La analista ve el aviso, pero referido a sus metas.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert "entre las tuyas" in client.get("/").text

    # Al cerrar la meta, el aviso desaparece.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    meta_id = _id_meta("Presentar declaracion atrasada")
    client.post(
        f"/metas/{meta_id}/estado",
        data={"estado": "cerrada"},
        follow_redirects=False,
    )
    assert "Presentar declaracion atrasada" not in client.get("/").text


def test_editar_meta(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/metas",
        data={"titulo": "Meta a editar", "horas_estimadas": "10"},
        follow_redirects=False,
    )
    meta_id = _id_meta("Meta a editar")

    formulario = client.get(f"/metas/{meta_id}/editar")
    assert formulario.status_code == 200
    assert "Meta a editar" in formulario.text
    assert "Avance actual" in formulario.text

    # Maria carga 5 horas contra las 10 previstas => 50%.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "Avance", "horas": "5"},
    )

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    assert "50% · 1 reporte(s)" in client.get(f"/metas/{meta_id}/editar").text

    # Un titulo vacio no se acepta.
    assert client.post(
        f"/metas/{meta_id}", data={"titulo": "   "}, follow_redirects=False
    ).headers["location"].startswith(f"/metas/{meta_id}/editar")

    respuesta = client.post(
        f"/metas/{meta_id}",
        data={
            "titulo": "Meta editada",
            "descripcion": "Ajustada al nuevo formato",
            "asignado_a": str(_id_usuario("mperez")),
            "fecha_limite": "2030-12-31",
            "horas_estimadas": "20",
            "estado": "activa",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/metas?msg=Meta%20actualizada"

    db = SessionLocal()
    try:
        meta = db.get(Meta, meta_id)
        assert meta.titulo == "Meta editada"
        assert meta.descripcion == "Ajustada al nuevo formato"
        assert meta.horas_estimadas == 20
        assert meta.asignado_a == _id_usuario("mperez")
        assert meta.fecha_limite == date(2030, 12, 31)
    finally:
        db.close()

    # Con las mismas 5 horas pero 20 previstas, el avance baja a 25%.
    formulario = client.get(f"/metas/{meta_id}/editar")
    assert "25% · 1 reporte(s)" in formulario.text
    assert "Meta editada" in client.get("/metas").text

    # Un empleado no puede abrir el formulario de edicion.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get(
        f"/metas/{meta_id}/editar", follow_redirects=False
    ).headers["location"].startswith("/?msg=")


def test_pagina_ayuda_muestra_instrucciones(client):
    assert login(client, "jefe", "1234").status_code == 303
    ayuda = client.get("/ayuda")
    assert ayuda.status_code == 200
    assert "netsh advfirewall firewall add rule" in ayuda.text


def test_resumen_semanal_en_panel_del_jefe(client):
    assert login(client, "jefe", "1234").status_code == 303
    panel = client.get("/")
    assert "Resumen de la semana" in panel.text
    assert "Maria Perez" in panel.text
    assert "de 5" in panel.text

    # El empleado no ve el resumen del equipo.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert "Resumen de la semana" not in client.get("/").text


