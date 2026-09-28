# --------------------------------------------------------------------------
# Seguridad de acceso y trazabilidad (Fase 3)
# --------------------------------------------------------------------------


from helpers import (
    _id_meta,
    _id_usuario,
    _ultimo_registro_de,
    _usuario_id,
    login,
)

from app import config
from app.database import SessionLocal
from app.models import Auditoria, Usuario


def test_login_bloqueado_tras_cinco_fallos(client, monkeypatch):
    from app import main as app_main
    from app.security import LimitadorDeIntentos

    # El limite por defecto es de 5 fallos.
    assert app_main.intentos_login.intentos == 5

    limpiador = LimitadorDeIntentos(intentos=3, bloqueo=60.0)
    monkeypatch.setattr(app_main, "intentos_login", limpiador)

    assert login(client, "jefe", "0000").status_code == 401
    assert login(client, "jefe", "0000").status_code == 401

    # El intento que llega al limite cierra la puerta.
    bloqueado = login(client, "jefe", "0000")
    assert bloqueado.status_code == 429
    assert "Demasiados intentos" in bloqueado.text

    # Y no se saltea con el PIN correcto.
    assert login(client, "jefe", "1234").status_code == 429

    # Otra persona o usuario sigue pudiendo intentar.
    assert login(client, "nadie", "1234").status_code == 401

    limpiador.limpiar("testclient|jefe")
    assert login(client, "jefe", "1234").status_code == 303


def test_backoff_del_limitador_de_intentos():
    from app.security import LimitadorDeIntentos

    limpiador = LimitadorDeIntentos(intentos=2, bloqueo=10.0, bloqueo_maximo=40.0)

    assert limpiador.restante("ip|jefe") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 10.0
    assert limpiador.restante("ip|jefe") > 0

    # Si vuelve a fallar cuando se libero, el proximo bloqueo se dobla.
    assert limpiador.registrar_fallo("ip|jefe") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 20.0
    assert limpiador.registrar_fallo("ip|jefe") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 40.0

    limpiador.limpiar("ip|jefe")
    assert limpiador.restante("ip|jefe") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 0.0


def test_la_fuerza_bruta_lenta_no_saltea_el_bloqueo():
    """Un intento cada 5 minutos tambien llega al limite.

    Antes los fallos se olvidaban a los 15 minutos, asi que espaciando los
    intentos nunca se llegaba a 5 y el bloqueo no se activaba nunca.
    """
    from app.security import LimitadorDeIntentos

    ahora = [1000.0]
    limpiador = LimitadorDeIntentos(
        intentos=5,
        bloqueo=300.0,
        bloqueo_maximo=1800.0,
        reloj=lambda: ahora[0],
    )

    for _ in range(4):
        assert limpiador.registrar_fallo("ip|jefe") == 0.0
        ahora[0] += 300.0  # 5 minutos entre intento e intento

    # El quinto bloquea, aunque hayan pasado mas de 20 minutos.
    assert limpiador.registrar_fallo("ip|jefe") == 300.0
    assert limpiador.restante("ip|jefe") > 0


def test_los_contadores_sin_actividad_se_descartan():
    """El diccionario en memoria no crece para siempre."""
    from app.security import LimitadorDeIntentos

    ahora = [0.0]
    limpiador = LimitadorDeIntentos(
        intentos=2,
        bloqueo=10.0,
        olvido=3600.0,
        reloj=lambda: ahora[0],
    )

    assert limpiador.registrar_fallo("ip|jefe") == 0.0

    # Pasa mas de un dia: la clave vieja se olvida cuando otra vuelve a fallar.
    ahora[0] += 7200.0
    assert limpiador.registrar_fallo("ip|otro") == 0.0
    assert limpiador.registrar_fallo("ip|jefe") == 0.0


def test_pin_de_fabrica_obliga_a_cambiarlo(client):
    assert login(client, "jefe", "1234").status_code == 303
    creado = client.post(
        "/equipo",
        data={
            "nombre": "Nuevo Ingreso",
            "usuario": "nuevoingreso",
            "pin": config.ADMIN_PIN,
            "rol": "empleado",
        },
        follow_redirects=False,
    )
    assert creado.status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303

    assert login(client, "nuevoingreso", config.ADMIN_PIN).status_code == 303

    # Entra y lo primero que ve es el aviso de cambiar el PIN.
    panel = client.get("/", follow_redirects=False)
    assert panel.status_code == 303
    assert panel.headers["location"].startswith("/ayuda")

    # Tampoco pasa a las otras paginas.
    guia = client.get("/guia", follow_redirects=False)
    assert guia.status_code == 303
    assert guia.headers["location"].startswith("/ayuda")

    # Pero el aviso y el formulario si estan disponibles.
    assert client.get("/ayuda", follow_redirects=False).status_code == 200
    cambio = client.post(
        "/mi-pin",
        data={"pin_actual": config.ADMIN_PIN, "pin_nuevo": "5678"},
        follow_redirects=False,
    )
    assert cambio.status_code == 303
    assert "PIN%20actualizado" in cambio.headers["location"]

    # Ya cambiado, el panel se abre normal.
    assert client.get("/", follow_redirects=False).status_code == 200


def test_acciones_criticas_dejan_rastro_en_la_auditoria(client):
    assert login(client, "jefe", "1234").status_code == 303

    client.post("/metas", data={"titulo": "Meta auditada"}, follow_redirects=False)
    meta_id = _id_meta("Meta auditada")

    client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "trabajo para borrar"},
        follow_redirects=False,
    )
    registro_id = _ultimo_registro_de("jefe")
    client.post(
        f"/registros/{registro_id}/comentario",
        data={"comentario": "revisado", "volver": "/"},
        follow_redirects=False,
    )
    client.post(
        f"/registros/{registro_id}/eliminar",
        data={"volver": "/"},
        follow_redirects=False,
    )

    client.post(
        f"/metas/{meta_id}",
        data={"titulo": "Meta auditada v2", "estado": "cerrada"},
        follow_redirects=False,
    )
    client.post(f"/metas/{meta_id}/duplicar", follow_redirects=False)
    client.post(f"/metas/{meta_id}/eliminar", follow_redirects=False)

    client.post(
        "/equipo",
        data={"nombre": "Persona Nueva", "usuario": "pnueva", "pin": "4321"},
        follow_redirects=False,
    )
    nuevo_id = _usuario_id("pnueva")
    client.post(f"/equipo/{nuevo_id}/activo", follow_redirects=False)
    client.post(f"/equipo/{nuevo_id}/pin", data={"pin": "8765"}, follow_redirects=False)

    client.post("/respaldos/ahora", follow_redirects=False)

    db = SessionLocal()
    try:
        acciones = {fila.accion for fila in db.query(Auditoria).all()}
        archivo = (
            db.query(Auditoria)
            .filter_by(accion="archivar_meta", objeto_id=meta_id)
            .one()
        )
        jefe_id = db.query(Usuario).filter_by(usuario="jefe").one().id
    finally:
        db.close()

    assert {
        "crear_meta",
        "editar_meta",
        "duplicar_meta",
        "archivar_meta",
        "comentar_registro",
        "eliminar_registro",
        "crear_usuario",
        "cambiar_estado_usuario",
        "cambiar_pin",
        "crear_respaldo",
    } <= acciones
    # Cada fila dice quien la hizo y sobre que.
    assert archivo.usuario_id == jefe_id
    assert archivo.objeto_tipo == "meta"
    assert archivo.resumen == "Meta auditada v2"


def test_respaldo_automatico_tambien_deja_rastro():
    from app.main import _auditar_respaldo_automatico

    _auditar_respaldo_automatico("respaldo-solo-de-prueba.db")

    db = SessionLocal()
    try:
        filas = (
            db.query(Auditoria)
            .filter_by(accion="crear_respaldo", resumen="respaldo-solo-de-prueba.db")
            .all()
        )
    finally:
        db.close()

    assert len(filas) == 1
    assert filas[0].usuario_id is None  # lo hizo el sistema, no una persona


def test_resetear_el_pin_corta_la_sesion_abierta_de_esa_persona(client):
    """Si sospechan del PIN, resetearlo echa a quien lo estuviera usando.

    Y cambiar el PIN propio, en cambio, no saca de la sesion al que lo cambio.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/equipo",
        data={
            "nombre": "Sesion Prueba",
            "usuario": "sesionprueba",
            "pin": "5150",
            "rol": "empleado",
        },
        follow_redirects=False,
    )
    persona_id = _id_usuario("sesionprueba")

    # Otra PC: la persona entra y deja la sesion abierta.
    with TestClient(app) as otra_pc:
        assert login(otra_pc, "sesionprueba", "5150").status_code == 303
        assert otra_pc.get("/").status_code == 200

        # El jefe le resetea el PIN desde su propia sesion.
        assert client.post(
            f"/equipo/{persona_id}/pin", data={"pin": "6262"}, follow_redirects=False
        ).status_code == 303

        # La sesion que estaba abierta en la otra PC deja de valer.
        vencida = otra_pc.get("/", follow_redirects=False)
        assert vencida.status_code == 303
        assert vencida.headers["location"] == "/login"

        # Entra con el PIN nuevo y sigue adentro al cambiar su propio PIN.
        assert login(otra_pc, "sesionprueba", "6262").status_code == 303
        assert otra_pc.post(
            "/mi-pin",
            data={"pin_actual": "6262", "pin_nuevo": "7373"},
            follow_redirects=False,
        ).status_code == 303
        assert otra_pc.get("/").status_code == 200


def test_la_sesion_no_vale_si_cambio_el_token(client):
    """Cualquier rotacion del token corta la cookie que andaba dando vueltas."""
    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/equipo",
        data={
            "nombre": "Token Prueba",
            "usuario": "tokenprueba",
            "pin": "1111",
            "rol": "empleado",
        },
        follow_redirects=False,
    )
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "tokenprueba", "1111").status_code == 303
    assert client.get("/").status_code == 200

    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario="tokenprueba").one()
        persona.sesion_token = "token-rotado-a-mano"
        db.commit()
    finally:
        db.close()

    vencida = client.get("/", follow_redirects=False)
    assert vencida.status_code == 303
    assert vencida.headers["location"] == "/login"


def test_error_500_muestra_una_pagina_amigable(client, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main as app_main

    def explota(*_args, **_kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(app_main, "resumen_semanal", explota)

    assert login(client, "jefe", "1234").status_code == 303
    # raise_server_exceptions=False: es como el navegador, que recibe la respuesta.
    with TestClient(app_main.app, raise_server_exceptions=False) as cliente_web:
        assert login(cliente_web, "jefe", "1234").status_code == 303
        respuesta = cliente_web.get("/")

    assert respuesta.status_code == 500
    assert "Algo salió mal" in respuesta.text
    assert "data/sistema.log" in respuesta.text


def test_headers_de_seguridad_en_las_respuestas(client):
    respuesta = client.get("/login")
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"
    assert respuesta.headers["referrer-policy"] == "strict-origin-when-cross-origin"
