# --------------------------------------------------------------------------
# Listados, exportes y avisos (Fase 4)
# --------------------------------------------------------------------------
from datetime import date, timedelta

from helpers import (
    _id_meta,
    _id_usuario,
    login,
)

from app.database import SessionLocal
from app.models import Meta, Registro, Usuario
from app.security import hash_pin


def test_paginacion_conserva_los_filtros(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta paginada"})
    meta_id = _id_meta("Meta paginada")

    db = SessionLocal()
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        for i in range(55):
            db.add(
                Registro(
                    usuario_id=jefe.id,
                    meta_id=meta_id,
                    fecha=date.today() - timedelta(days=i),
                    descripcion=f"fila paginada {i}",
                    horas=1.0,
                    estado="completado",
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        una = client.get("/registros", params={"meta_id": str(meta_id)})
        assert una.status_code == 200
        assert "55 registro(s)" in una.text
        # Encabezado + 50 filas: no se tiran las 55 de una.
        assert una.text.count("<tr>") == 51
        # El enlace a la pagina 2 no se olvida del filtro.
        assert f'href="/registros?meta_id={meta_id}&amp;page=2"' in una.text
        # Y el Excel baja los 55, no la pagina.
        assert (
            una.text.count(f"/registros/exportar.xlsx?meta_id={meta_id}") == 1
        )

        dos = client.get("/registros", params={"meta_id": str(meta_id), "page": "2"})
        assert dos.status_code == 200
        assert "Página 2 de 2" in dos.text
        assert "55 registro(s)" in dos.text  # los totales no cambian de pagina
        assert dos.text.count("<tr>") == 6  # encabezado + 5 filas
    finally:
        db = SessionLocal()
        try:
            db.query(Registro).filter_by(meta_id=meta_id).delete(
                synchronize_session=False
            )
            meta = db.get(Meta, meta_id)
            if meta is not None:
                db.delete(meta)
            db.commit()
        finally:
            db.close()


def test_filtro_por_texto_y_estado(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta de texto"})
    meta_id = _id_meta("Meta de texto")
    client.post(
        "/registros",
        data={
            "meta_id": str(meta_id),
            "descripcion": "arquitectura de puentes colgantes",
            "horas": "4",
            "estado": "bloqueado",
        },
        follow_redirects=False,
    )

    con_texto = client.get("/registros", params={"texto": "puentes"})
    assert con_texto.status_code == 200
    assert "arquitectura de puentes colgantes" in con_texto.text
    # El filtro sigue vivo en el enlace del Excel.
    assert "exportar.xlsx?texto=puentes" in con_texto.text

    sin_nada = client.get("/registros", params={"texto": "zzzznoexiste"})
    assert sin_nada.status_code == 200
    assert "No hay registros con esos filtros." in sin_nada.text

    por_estado = client.get("/registros", params={"estado": "bloqueado"})
    assert por_estado.status_code == 200
    assert "arquitectura de puentes colgantes" in por_estado.text

    combinado = client.get(
        "/registros", params={"texto": "puentes", "estado": "bloqueado"}
    )
    assert "arquitectura de puentes colgantes" in combinado.text
    assert "exportar.xlsx?texto=puentes&amp;estado=bloqueado" in combinado.text

    # Un estado inventado no se aplica (no filtra por cualquier cosa).
    inventado = client.get("/registros", params={"estado": "cualquiera"})
    assert inventado.status_code == 200
    assert "arquitectura de puentes colgantes" in inventado.text


def test_excel_y_pdf_desde_la_ficha_de_persona(client):
    assert login(client, "jefe", "1234").status_code == 303
    maria = _id_usuario("mperez")

    ficha = client.get(f"/personas/{maria}")
    assert ficha.status_code == 200
    assert f'href="/registros/exportar.xlsx?usuario_id={maria}"' in ficha.text
    assert f'action="/personas/{maria}/reporte.pdf"' in ficha.text

    excel = client.get("/registros/exportar.xlsx", params={"usuario_id": str(maria)})
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )

    pdf = client.get(f"/personas/{maria}/reporte.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-"
    assert 'filename="reporte_mperez_' in pdf.headers["content-disposition"]

    # Periodo invalido no tira error 500.
    raro = client.get(
        f"/personas/{maria}/reporte.pdf",
        params={"mes": "13"},
        follow_redirects=False,
    )
    assert raro.status_code == 303
    assert raro.headers["location"].startswith(f"/personas/{maria}?msg=")


def test_aviso_de_carga_excesiva(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/equipo",
        data={"nombre": "Larga Carga", "usuario": "largacarga", "pin": "4321"},
        follow_redirects=False,
    )
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "largacarga", "4321").status_code == 303

    cargado = client.post(
        "/registros",
        data={"descripcion": "dia de nueve horas", "horas": "9"},
        follow_redirects=False,
    )
    ubicacion = cargado.headers["location"]
    assert ubicacion.startswith("/?msg=Registro%20guardado")
    assert "superar%208%20h%20en%20un%20dia" in ubicacion

    # El aviso no frena nada: el registro quedo guardado igual.
    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario="largacarga").one()
        guardados = (
            db.query(Registro)
            .filter_by(usuario_id=persona.id, fecha=date.today())
            .count()
        )
    finally:
        db.close()
    assert guardados == 1

    # Una carga normal no avisa.
    normal = client.post(
        "/registros",
        data={
            "descripcion": "media jornada",
            "horas": "2",
            "fecha": (date.today() - timedelta(days=1)).isoformat(),
        },
        follow_redirects=False,
    )
    assert normal.headers["location"] == "/?msg=Registro%20guardado"


def test_aviso_de_carga_excesiva_por_semana():
    """El aviso de semana salta al pasar de 40 h, aunque ningun dia pase de 8."""
    from app.main import aviso_de_carga

    db = SessionLocal()
    persona_id = None
    try:
        persona = Usuario(
            nombre="Semana Larga",
            usuario="semanalarga",
            pin_hash=hash_pin("4321"),
            rol="empleado",
        )
        db.add(persona)
        db.flush()
        persona_id = persona.id

        # Lunes a sabado de la semana pasada: todos los dias en el pasado.
        lunes = date.today() - timedelta(days=date.today().weekday()) - timedelta(days=7)
        for i in range(6):
            db.add(
                Registro(
                    usuario_id=persona_id,
                    fecha=lunes + timedelta(days=i),
                    descripcion="siete horas",
                    horas=7.0,
                    estado="completado",
                )
            )
        db.commit()

        sabado = lunes + timedelta(days=5)

        # Una semana anterior no tiene nada cargado: no avisa.
        assert aviso_de_carga(db, persona_id, lunes - timedelta(days=3)) == ""

        # El sabado la semana llega a 42 h aunque ese dia solo cargó 7.
        aviso_semana = aviso_de_carga(db, persona_id, sabado)
        assert "42.0 h en la semana" in aviso_semana
        assert "en un dia" not in aviso_semana

        # Si ademas ese dia se pasa de 8, avisa las dos cosas.
        db.add(
            Registro(
                usuario_id=persona_id,
                fecha=lunes,
                descripcion="dos horas mas",
                horas=2.0,
                estado="completado",
            )
        )
        db.commit()
        aviso = aviso_de_carga(db, persona_id, lunes)
        assert "9.0 h el" in aviso
        assert "44.0 h en la semana" in aviso
    finally:
        if persona_id is not None:
            db.query(Registro).filter_by(usuario_id=persona_id).delete(
                synchronize_session=False
            )
            db.query(Usuario).filter_by(id=persona_id).delete(
                synchronize_session=False
            )
            db.commit()
        db.close()


def test_pagina_de_auditoria(client):
    assert login(client, "jefe", "1234").status_code == 303
    client.post("/metas", data={"titulo": "Meta para auditar"})
    meta_id = _id_meta("Meta para auditar")
    client.post(f"/metas/{meta_id}/eliminar", follow_redirects=False)

    pagina = client.get("/auditoria")
    assert pagina.status_code == 200
    assert "Archivó una meta" in pagina.text
    assert "Meta para auditar" in pagina.text

    filtrada = client.get("/auditoria", params={"accion": "archivar_meta"})
    assert filtrada.status_code == 200
    assert "Meta para auditar" in filtrada.text

    por_persona = client.get(
        "/auditoria", params={"usuario_id": str(_id_usuario("jefe"))}
    )
    assert por_persona.status_code == 200
    assert "Meta para auditar" in por_persona.text

    # Un filtro inventado no filtra nada raro.
    rara = client.get("/auditoria", params={"accion": "no_existe"})
    assert rara.status_code == 200
    assert "acción(es)" in rara.text

    # El equipo no ve esta pantalla.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get("/auditoria", follow_redirects=False).status_code == 303


