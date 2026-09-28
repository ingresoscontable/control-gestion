"""Dias laborables configurables y novedades (vacaciones, licencias, feriados).

Autocontenido: cada prueba arma su propio personal, asi que se puede correr con
``pytest tests/test_15_jornada_novedades.py``.
"""

from datetime import date, timedelta
from urllib.parse import unquote

from helpers import _id_usuario, login

from app import config
from app.database import SessionLocal
from app.jornada import dias_laborables, es_laborable
from app.metricas import resumen_semanal
from app.models import Novedad, Registro, Usuario
from app.security import hash_pin

# Una semana completa de ejemplo: lunes 02/03/2026 a domingo 08/03/2026.
LUNES = date(2026, 3, 2)
MIERCOLES = date(2026, 3, 4)
SABADO = date(2026, 3, 7)
DOMINGO = date(2026, 3, 8)

PIN = "4821"


def _asegurar(db, nombre_usuario: str) -> Usuario:
    """Crea (o recupera) un empleado de estas pruebas."""
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


def test_dias_laborables_por_defecto_son_lunes_a_viernes():
    assert config.DIAS_LABORABLES == (1, 2, 3, 4, 5)
    assert dias_laborables(LUNES, DOMINGO) == 5
    assert es_laborable(LUNES)
    assert not es_laborable(SABADO)
    assert not es_laborable(DOMINGO)


def test_los_dias_laborables_se_pueden_configurar(monkeypatch):
    monkeypatch.setattr(config, "DIAS_LABORABLES", (1, 2, 3, 4, 5, 6))
    assert dias_laborables(LUNES, DOMINGO) == 6
    assert es_laborable(SABADO)
    assert not es_laborable(DOMINGO)

    monkeypatch.setattr(config, "DIAS_LABORABLES", (1, 2, 3, 4, 5, 6, 7))
    assert dias_laborables(LUNES, DOMINGO) == 7


def test_el_resumen_semanal_cuenta_solo_dias_laborables(client):
    db = SessionLocal()
    try:
        persona = _asegurar(db, "jornadauno")
        db.add_all(
            [
                Registro(
                    usuario_id=persona.id,
                    fecha=LUNES,
                    descripcion="trabajo del lunes",
                    horas=1.0,
                ),
                Registro(
                    usuario_id=persona.id,
                    fecha=SABADO,
                    descripcion="trabajo del sabado",
                    horas=1.0,
                ),
            ]
        )
        db.commit()

        resumen, inicio = resumen_semanal(db, [persona], MIERCOLES)
        fila = resumen[0]
    finally:
        db.close()

    assert inicio == LUNES
    assert fila["registros"] == 2  # los dos se cuentan como reportes
    assert fila["dias"] == 1  # pero el sabado no suma al cumplimiento
    assert fila["laborables"] == 5
    assert fila["cumplimiento"] == "baja"


def test_una_novedad_baja_los_dias_esperados(client):
    db = SessionLocal()
    try:
        persona = _asegurar(db, "jornadados")
        db.add(
            Novedad(
                usuario_id=persona.id,
                tipo="vacaciones",
                desde=LUNES,
                hasta=MIERCOLES,
                detalle="licencia de prueba",
            )
        )
        db.add(
            Registro(
                usuario_id=persona.id,
                fecha=LUNES,
                descripcion="trabajo del lunes",
                horas=1.0,
            )
        )
        db.commit()

        resumen, _inicio = resumen_semanal(db, [persona], MIERCOLES)
        fila = resumen[0]
    finally:
        db.close()

    # Lunes, martes y miercoles de vacaciones: quedan 2 dias esperados de 5.
    assert fila["laborables"] == 2
    assert fila["dias"] == 1
    assert fila["cumplimiento"] == "baja"


def test_una_novedad_de_todo_el_equipo_aplica_a_cualquiera(client):
    db = SessionLocal()
    try:
        persona = _asegurar(db, "jornadatres")
        db.add(
            Novedad(
                usuario_id=None,
                tipo="feriado",
                desde=DOMINGO,
                hasta=DOMINGO,
                detalle="feriado en domingo",
            )
        )
        db.commit()

        # El domingo no es laborable, asi que no cambia el total esperado.
        resumen, _inicio = resumen_semanal(db, [persona], MIERCOLES)
        assert resumen[0]["laborables"] == 5

        db.add(
            Novedad(
                usuario_id=None,
                tipo="feriado",
                desde=LUNES,
                hasta=LUNES,
                detalle="feriado en dia laborable",
            )
        )
        db.commit()
        resumen, _inicio = resumen_semanal(db, [persona], MIERCOLES)
        assert resumen[0]["laborables"] == 4
    finally:
        db.close()


def test_no_se_reclama_el_reporte_de_quien_esta_de_licencia(client, monkeypatch):
    # Hoy cuenta como laborable, para aislar el efecto de la novedad.
    hoy = date.today()
    monkeypatch.setattr(config, "DIAS_LABORABLES", tuple(range(1, 8)))

    db = SessionLocal()
    try:
        persona = _asegurar(db, "licenciaprueba")
        persona_id = persona.id
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    assert 'falta-registro">Licenciaprueba Prueba' in client.get("/").text

    assert client.post(
        "/novedades",
        data={
            "usuario_id": str(persona_id),
            "tipo": "licencia",
            "desde": hoy.isoformat(),
            "hasta": hoy.isoformat(),
            "detalle": "turno medico",
        },
        follow_redirects=False,
    ).status_code == 303

    assert 'falta-registro">Licenciaprueba Prueba' not in client.get("/").text
    assert "turno medico" in client.get("/novedades").text


def test_si_hoy_no_es_laborable_no_se_reclama_nada(client, monkeypatch):
    otro_dia = date.today() + timedelta(days=1)
    monkeypatch.setattr(config, "DIAS_LABORABLES", (otro_dia.isoweekday(),))

    assert login(client, "jefe", "1234").status_code == 303
    pagina = client.get("/")
    assert "Hoy no es día laborable" in pagina.text
    assert "Sin registrar hoy" not in pagina.text


def test_las_novedades_son_solo_para_el_jefe(client):
    db = SessionLocal()
    try:
        _asegurar(db, "licenciaprueba")
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    assert client.get("/novedades").status_code == 200

    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "licenciaprueba", PIN).status_code == 303
    assert client.get("/novedades", follow_redirects=False).headers["location"].startswith(
        "/?msg="
    )


def test_una_novedad_invalida_no_se_carga(client):
    assert login(client, "jefe", "1234").status_code == 303

    sin_fecha = client.post("/novedades", data={"tipo": "licencia"}, follow_redirects=False)
    assert "desde cuándo" in unquote(sin_fecha.headers["location"])

    al_reves = client.post(
        "/novedades",
        data={"tipo": "licencia", "desde": "2026-03-10", "hasta": "2026-03-01"},
        follow_redirects=False,
    )
    assert "anterior" in unquote(al_reves.headers["location"])

    tipo_malo = client.post(
        "/novedades",
        data={"tipo": "inventado", "desde": "2026-03-10"},
        follow_redirects=False,
    )
    assert "inválido" in unquote(tipo_malo.headers["location"])


def test_una_novedad_se_puede_borrar(client):
    db = SessionLocal()
    try:
        _asegurar(db, "licenciaprueba")
    finally:
        db.close()

    assert login(client, "jefe", "1234").status_code == 303
    persona_id = _id_usuario("licenciaprueba")

    assert client.post(
        "/novedades",
        data={
            "usuario_id": str(persona_id),
            "tipo": "otro",
            "desde": "2026-05-04",
            "hasta": "2026-05-05",
            "detalle": "para borrar",
        },
        follow_redirects=False,
    ).status_code == 303

    db = SessionLocal()
    try:
        novedad_id = (
            db.query(Novedad).filter_by(detalle="para borrar").one().id
        )
    finally:
        db.close()

    assert client.post(
        f"/novedades/{novedad_id}/eliminar", follow_redirects=False
    ).status_code == 303
    assert "para borrar" not in client.get("/novedades").text
