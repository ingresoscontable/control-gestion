"""Medir resultados: cantidad por reporte y objetivo en cantidad por meta.

Autocontenido: crea su propio personal y sus metas, asi que se puede correr con
``pytest tests/test_16_cantidad_objetivo.py``.
"""

from datetime import date, timedelta

from helpers import login

from app.database import SessionLocal
from app.models import Meta, Registro, Usuario
from app.progreso import progreso_metas
from app.security import hash_pin

LUNES = date(2026, 2, 2)
MARTES = date(2026, 2, 3)
PIN = "4821"


def _empleado(db, nombre_usuario: str = "cantidadprueba") -> Usuario:
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


def _meta(db, titulo: str, **extra) -> Meta:
    meta = Meta(titulo=titulo, **extra)
    db.add(meta)
    db.commit()
    return meta


def _cantidad_de(descripcion: str) -> float:
    db = SessionLocal()
    try:
        return db.query(Registro).filter_by(descripcion=descripcion).one().cantidad
    finally:
        db.close()


def test_el_objetivo_en_cantidad_manda_sobre_las_horas(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        meta = _meta(
            db,
            "Meta con objetivo",
            horas_estimadas=10,
            objetivo=100,
            unidad="trámites",
        )
        db.add(
            Registro(
                usuario_id=persona.id,
                meta_id=meta.id,
                fecha=LUNES,
                descripcion="media jornada cargando tramites",
                horas=10,  # por horas ya llegaria al 100%
                cantidad=25,  # pero el objetivo manda
            )
        )
        db.commit()
        fila = progreso_metas(db, [meta])[0]
    finally:
        db.close()

    assert fila["horas"] == 10
    assert fila["cantidad"] == 25
    assert fila["avance"] == 25


def test_el_avance_por_objetivo_se_topa_en_100(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        meta = _meta(db, "Objetivo superado", objetivo=10, unidad="registros")
        db.add(
            Registro(
                usuario_id=persona.id,
                meta_id=meta.id,
                fecha=LUNES,
                descripcion="cargo de mas",
                cantidad=14,
            )
        )
        db.commit()
        fila = progreso_metas(db, [meta])[0]
    finally:
        db.close()

    assert fila["cantidad"] == 14
    assert fila["avance"] == 100


def test_sin_objetivo_el_avance_sigue_saliendo_de_las_horas(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        meta = _meta(db, "Meta solo por horas", horas_estimadas=10)
        db.add(
            Registro(
                usuario_id=persona.id,
                meta_id=meta.id,
                fecha=LUNES,
                descripcion="avance",
                horas=4,
                cantidad=999,  # se guarda, pero no se usa para el avance
            )
        )
        db.commit()
        fila = progreso_metas(db, [meta])[0]
    finally:
        db.close()

    assert fila["avance"] == 40


def test_sin_objetivo_ni_horas_el_avance_sale_de_los_completados(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        meta = _meta(db, "Meta por reportes")
        db.add_all(
            [
                Registro(
                    usuario_id=persona.id,
                    meta_id=meta.id,
                    fecha=LUNES,
                    descripcion="paso uno",
                    estado="completado",
                ),
                Registro(
                    usuario_id=persona.id,
                    meta_id=meta.id,
                    fecha=MARTES,
                    descripcion="paso dos",
                ),
            ]
        )
        db.commit()
        fila = progreso_metas(db, [meta])[0]
    finally:
        db.close()

    assert fila["avance"] == 50


def test_una_meta_se_crea_con_unidad_y_objetivo_desde_la_pantalla(client):
    assert login(client, "jefe", "1234").status_code == 303
    assert client.post(
        "/metas",
        data={
            "titulo": "Meta con unidad visible",
            "objetivo": "250",
            "unidad": "liquidaciones",
        },
        follow_redirects=False,
    ).status_code == 303

    db = SessionLocal()
    try:
        meta = db.query(Meta).filter_by(titulo="Meta con unidad visible").one()
        objetivo, unidad = meta.objetivo, meta.unidad
    finally:
        db.close()

    assert objetivo == 250.0
    assert unidad == "liquidaciones"
    assert "liquidaciones" in client.get("/metas").text


def test_editar_una_meta_cambia_el_objetivo_y_la_unidad(client):
    assert login(client, "jefe", "1234").status_code == 303

    db = SessionLocal()
    try:
        meta = db.query(Meta).filter_by(titulo="Meta con unidad visible").one()
        meta_id = meta.id
    finally:
        db.close()

    assert client.post(
        f"/metas/{meta_id}",
        data={
            "titulo": "Meta con unidad visible",
            "objetivo": "300",
            "unidad": "trámites",
            "estado": "activa",
        },
        follow_redirects=False,
    ).status_code == 303

    db = SessionLocal()
    try:
        meta = db.get(Meta, meta_id)
        objetivo, unidad = meta.objetivo, meta.unidad
    finally:
        db.close()

    assert objetivo == 300.0
    assert unidad == "trámites"


def test_duplicar_una_meta_copia_el_objetivo_y_la_unidad(client):
    assert login(client, "jefe", "1234").status_code == 303

    db = SessionLocal()
    try:
        meta = db.query(Meta).filter_by(titulo="Meta con unidad visible").one()
        meta_id = meta.id
    finally:
        db.close()

    assert client.post(
        f"/metas/{meta_id}/duplicar", follow_redirects=False
    ).status_code == 303

    db = SessionLocal()
    try:
        copia = db.query(Meta).filter_by(titulo="Meta con unidad visible (copia)").one()
        objetivo, unidad = copia.objetivo, copia.unidad
    finally:
        db.close()

    assert objetivo == 300.0
    assert unidad == "trámites"


def test_la_cantidad_se_guarda_con_el_reporte(client):
    db = SessionLocal()
    try:
        _empleado(db, "cantidadhttp")
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "cantidadhttp", PIN).status_code == 303

    assert client.post(
        "/registros",
        data={
            "descripcion": "carga con cantidad",
            "horas": "3",
            "cantidad": "47",
            "fecha": (date.today() - timedelta(days=3)).isoformat(),
            "estado": "completado",
        },
        follow_redirects=False,
    ).status_code == 303

    assert _cantidad_de("carga con cantidad") == 47.0


def test_una_cantidad_invalida_queda_en_cero(client):
    assert login(client, "jefe", "1234").status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "cantidadhttp", PIN).status_code == 303

    assert client.post(
        "/registros",
        data={
            "descripcion": "cantidad negativa",
            "horas": "2",
            "cantidad": "-5",
            "fecha": (date.today() - timedelta(days=4)).isoformat(),
        },
        follow_redirects=False,
    ).status_code == 303
    assert _cantidad_de("cantidad negativa") == 0.0

    assert client.post(
        "/registros",
        data={
            "descripcion": "cantidad con texto",
            "horas": "2",
            "cantidad": "muchas",
            "fecha": (date.today() - timedelta(days=5)).isoformat(),
        },
        follow_redirects=False,
    ).status_code == 303
    assert _cantidad_de("cantidad con texto") == 0.0


def test_el_panel_del_equipo_muestra_la_unidad_de_la_meta(client):
    db = SessionLocal()
    try:
        persona = _empleado(db)
        _meta(
            db,
            "Meta visible en el panel",
            objetivo=40,
            unidad="informes",
            asignado_a=persona.id,
        )
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "cantidadprueba", PIN).status_code == 303

    panel = client.get("/")
    assert "Meta visible en el panel" in panel.text
    assert "informes" in panel.text
