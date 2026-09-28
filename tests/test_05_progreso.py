from datetime import date, timedelta

from helpers import (
    _id_meta,
    login,
)


def test_progreso_de_metas(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/metas",
        data={"titulo": "Cierre contable octubre", "horas_estimadas": "10"},
        follow_redirects=False,
    )
    client.post(
        "/metas", data={"titulo": "Meta sin estimacion"}, follow_redirects=False
    )
    meta_horas = _id_meta("Cierre contable octubre")
    meta_sin = _id_meta("Meta sin estimacion")

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303

    # 4 horas contra una meta de 10 previstas => 40%.
    client.post(
        "/registros",
        data={"meta_id": str(meta_horas), "descripcion": "Avance uno", "horas": "4"},
    )
    panel = client.get("/")
    assert "Mis metas y su avance" in panel.text
    assert "Cierre contable octubre" in panel.text
    assert "40%" in panel.text

    # Sin horas estimadas: 1 de 2 reportes completados => 50%.
    client.post(
        "/registros",
        data={
            "meta_id": str(meta_sin),
            "descripcion": "Paso uno",
            "estado": "completado",
        },
    )
    client.post(
        "/registros",
        data={
            "meta_id": str(meta_sin),
            "descripcion": "Paso dos",
            "fecha": (date.today() - timedelta(days=1)).isoformat(),
            "estado": "en_progreso",
        },
    )
    assert "50%" in client.get("/").text

    # La analista no entra a la vista del jefe.
    assert client.get(
        "/metas/progreso", follow_redirects=False
    ).headers["location"].startswith("/?msg=")

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get("/metas/progreso")
    assert pagina.status_code == 200
    assert "Progreso de metas" in pagina.text
    assert "40%" in pagina.text
    assert "50%" in pagina.text
    assert "10 h" in pagina.text  # horas estimadas de la meta

    # La lista de metas tambien muestra el avance.
    assert "40%" in client.get("/metas").text

    # 7 horas mas => 11 de 10 previstas, el avance se topa en 100%.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    client.post(
        "/registros",
        data={"meta_id": str(meta_horas), "descripcion": "Avance dos", "horas": "7"},
    )
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303
    assert "100%" in client.get("/metas/progreso").text

    # Cerrar una meta la deja en 100%.
    assert client.post(
        f"/metas/{meta_sin}/estado", data={"estado": "cerrada"}, follow_redirects=False
    ).status_code == 303
    progreso = client.get("/metas/progreso?ver=todas")
    assert progreso.status_code == 200
    assert "Meta sin estimacion" in progreso.text

    # La vista "activas" deja afuera la meta cerrada.
    assert "Meta sin estimacion" not in client.get("/metas/progreso?ver=activas").text


