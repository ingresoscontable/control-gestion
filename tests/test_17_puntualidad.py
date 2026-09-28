"""Puntualidad: cuanto se cargo el mismo dia en que se hizo el trabajo.

Autocontenido: crea su propio personal, asi que se puede correr con
``pytest tests/test_17_puntualidad.py``.
"""

from datetime import date, datetime, timedelta

from helpers import _id_usuario, login

from app.database import SessionLocal
from app.main import filtrar_registros, totales_registros
from app.metricas import puntualidad, resumen_semanal
from app.models import Registro, Usuario
from app.security import hash_pin

PIN = "4821"
HOY = date.today()
INICIO_SEMANA = HOY - timedelta(days=HOY.weekday())
HACE_TRES = HOY - timedelta(days=3)


def _empleado(db, nombre_usuario: str = "puntualidadprueba") -> Usuario:
    persona = db.query(Usuario).filter_by(usuario=nombre_usuario).one_or_none()
    if persona is None:
        persona = Usuario(
            nombre=f"{nombre_usuario.title()} Prueba",
            usuario=nombre_usuario,
            cargo="Analista",
            pin_hash=hash_pin(PIN),
            rol="empleado",
        )
        db.add(persona)
        db.commit()
    return persona


def _registro(usuario_id: int, fecha: date, creado_en: date, descripcion: str) -> Registro:
    return Registro(
        usuario_id=usuario_id,
        fecha=fecha,
        creado_en=datetime(creado_en.year, creado_en.month, creado_en.day, 9, 0),
        descripcion=descripcion,
        horas=1.0,
    )


def test_la_puntualidad_separa_lo_cargado_en_fecha_de_lo_atrasado(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        db.add_all(
            [
                _registro(persona.id, HACE_TRES, HACE_TRES, "cargado el mismo dia"),
                _registro(persona.id, HACE_TRES - timedelta(days=1), HOY, "cargado tarde"),
            ]
        )
        db.commit()
        datos = puntualidad(db, persona.id, HOY - timedelta(days=30), HOY)
    finally:
        db.close()

    assert datos["total"] == 2
    assert datos["en_fecha"] == 1
    assert datos["tarde"] == 1
    assert datos["porcentaje"] == 50


def test_sin_reportes_la_puntualidad_es_vacia(client):
    db = SessionLocal()
    try:
        persona = _empleado(db, "puntualidadvacia")
        datos = puntualidad(db, persona.id, HOY - timedelta(days=30), HOY)
    finally:
        db.close()

    assert datos["total"] == 0
    assert datos["porcentaje"] is None


def test_los_totales_de_registros_traen_los_cargados_en_fecha(client):
    db = SessionLocal()
    try:
        persona = _empleado(db, "puntualidadtotales")
        db.add_all(
            [
                _registro(persona.id, HACE_TRES, HACE_TRES, "en fecha"),
                _registro(persona.id, HACE_TRES - timedelta(days=1), HOY, "tarde"),
            ]
        )
        db.commit()

        consulta, _filtros = filtrar_registros(str(persona.id), "", "")
        totales = totales_registros(db, consulta)
    finally:
        db.close()

    assert totales["cantidad"] == 2
    assert totales["en_fecha"] == 1


def test_el_resumen_semanal_trae_la_puntualidad(client):
    db = SessionLocal()
    try:
        persona = _empleado(db, "puntualidadsemana")
        db.add_all(
            [
                _registro(persona.id, INICIO_SEMANA, INICIO_SEMANA, "lunes en fecha"),
                _registro(
                    persona.id,
                    INICIO_SEMANA + timedelta(days=1),
                    INICIO_SEMANA,
                    "martes cargado el lunes",
                ),
            ]
        )
        db.commit()

        resumen, _inicio = resumen_semanal(db, [persona], HOY)
        fila = resumen[0]
    finally:
        db.close()

    assert fila["registros"] == 2
    assert fila["en_fecha"] == 1
    assert fila["puntualidad"] == 50


def test_la_pagina_de_registros_muestra_el_kpi(client):
    db = SessionLocal()
    try:
        persona = _empleado(db, "puntualidadkpi")
        persona_id = persona.id
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "puntualidadkpi", PIN).status_code == 303

    assert client.post(
        "/registros",
        data={"descripcion": "kpi de hoy", "horas": "2", "fecha": HOY.isoformat()},
        follow_redirects=False,
    ).status_code == 303
    assert client.post(
        "/registros",
        data={"descripcion": "kpi atrasado", "horas": "2", "fecha": HACE_TRES.isoformat()},
        follow_redirects=False,
    ).status_code == 303

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get("/registros", params={"usuario_id": str(persona_id)})
    assert pagina.status_code == 200
    assert "Cargados el mismo día en que se hizo el trabajo" in pagina.text
    assert "<strong>1</strong> de 2" in pagina.text


def test_la_ficha_de_la_persona_muestra_la_puntualidad(client):
    db = SessionLocal()
    try:
        _empleado(db, "puntualidadkpi")
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    persona_id = _id_usuario("puntualidadkpi")

    ficha = client.get(f"/personas/{persona_id}")
    assert ficha.status_code == 200
    assert "cargado el mismo día" in ficha.text
    assert "con fecha atrasada" in ficha.text


def test_el_pdf_de_la_persona_se_sigue_generando(client):
    assert login(client, "jefe", "1234").status_code == 303
    persona_id = _id_usuario("puntualidadkpi")

    respuesta = client.get(f"/personas/{persona_id}/reporte.pdf")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
