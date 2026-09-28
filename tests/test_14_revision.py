"""Revision del trabajo: el jefe aprueba, devuelve y la persona corrige.

Estas pruebas se arman solas (crean su propio empleado), asi que se pueden
correr con ``pytest tests/test_14_revision.py`` sin depender de las demas.
"""

from io import BytesIO
from urllib.parse import unquote

from helpers import login
from openpyxl import load_workbook

from app.database import SessionLocal
from app.models import Auditoria, Meta, Registro, Usuario
from app.security import hash_pin

EMPLEADO_USUARIO = "analista"
EMPLEADO_PIN = "4821"


def _empleado_id() -> int:
    """Asegura el empleado de estas pruebas y devuelve su id."""
    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario=EMPLEADO_USUARIO).one_or_none()
        if persona is None:
            persona = Usuario(
                nombre="Analista de Pruebas",
                usuario=EMPLEADO_USUARIO,
                cargo="Analista",
                pin_hash=hash_pin(EMPLEADO_PIN),
                rol="empleado",
            )
            db.add(persona)
            db.commit()
        return persona.id
    finally:
        db.close()


def _entrar(client, usuario: str, pin: str) -> None:
    client.post("/logout", follow_redirects=False)
    assert login(client, usuario, pin).status_code == 303


def _crear_meta(client, titulo: str, usuario_id: int, horas: str = "") -> int:
    datos = {"titulo": titulo, "asignado_a": str(usuario_id)}
    if horas:
        datos["horas_estimadas"] = horas
    client.post("/metas", data=datos, follow_redirects=False)
    db = SessionLocal()
    try:
        return db.query(Meta).filter_by(titulo=titulo).one().id
    finally:
        db.close()


def _id_registro(usuario: str, descripcion: str) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(Registro)
            .join(Usuario, Usuario.id == Registro.usuario_id)
            .filter(
                Usuario.usuario == usuario,
                Registro.descripcion == descripcion,
            )
            .one()
            .id
        )
    finally:
        db.close()


def _avance_de(meta_id: int) -> int:
    from app.progreso import progreso_metas

    db = SessionLocal()
    try:
        return progreso_metas(db, [db.get(Meta, meta_id)])[0]["avance"]
    finally:
        db.close()


def _acciones_de_auditoria() -> set[str]:
    db = SessionLocal()
    try:
        return {fila.accion for fila in db.query(Auditoria).all()}
    finally:
        db.close()


def test_flujo_de_revision_completo(client):
    """Pendiente -> el jefe devuelve -> la analista corrige -> el jefe aprueba."""
    empleado = _empleado_id()
    _entrar(client, "jefe", "1234")
    meta_id = _crear_meta(client, "Meta para revisar", empleado)

    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)
    client.post(
        "/registros",
        data={"meta_id": str(meta_id), "descripcion": "Trabajo a revisar", "horas": "3"},
    )
    rid = _id_registro(EMPLEADO_USUARIO, "Trabajo a revisar")

    # La analista no puede aprobarse su propio reporte.
    propio = client.post(
        f"/registros/{rid}/revisar",
        data={"estado_revision": "aprobado"},
        follow_redirects=False,
    )
    assert propio.headers["location"].startswith("/?msg=")

    # El jefe lo ve pendiente y el panel se lo recuerda.
    _entrar(client, "jefe", "1234")
    assert "badge pendiente" in client.get("/registros").text
    assert "esperando tu revisión" in client.get("/").text

    # Devolverlo sin decir qué corregir no se acepta.
    sin_motivo = client.post(
        f"/registros/{rid}/revisar",
        data={"estado_revision": "correccion_pendiente", "observacion": "   "},
        follow_redirects=False,
    )
    assert "qué hay que corregir" in unquote(sin_motivo.headers["location"])

    # Con observación vuelve a la analista.
    assert client.post(
        f"/registros/{rid}/revisar",
        data={
            "estado_revision": "correccion_pendiente",
            "observacion": "Falta el detalle del IVA",
        },
        follow_redirects=False,
    ).status_code == 303

    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)
    panel = client.get("/")
    assert "te devolvió para corregir" in panel.text
    assert "Falta el detalle del IVA" in panel.text
    assert client.get(f"/registros/{rid}/corregir").status_code == 200

    assert client.post(
        f"/registros/{rid}/corregir",
        data={
            "descripcion": "Trabajo revisado con IVA",
            "horas": "4",
            "estado": "completado",
        },
        follow_redirects=False,
    ).status_code == 303

    # Vuelve a la bandeja del jefe, que ahora lo aprueba.
    _entrar(client, "jefe", "1234")
    assert "badge pendiente" in client.get("/registros").text
    assert client.post(
        f"/registros/{rid}/revisar",
        data={"estado_revision": "aprobado", "observacion": "OK"},
        follow_redirects=False,
    ).status_code == 303
    assert "badge aprobado" in client.get("/registros").text

    # El filtro de revisión trae solo lo aprobado y el Excel agrega la columna.
    aprobados = client.get("/registros", params={"revision": "aprobado"})
    assert "Trabajo revisado con IVA" in aprobados.text
    assert "badge pendiente" not in aprobados.text

    libro = load_workbook(BytesIO(client.get("/registros/exportar.xlsx").content))
    encabezados = [celda.value for celda in libro.active[1]]
    assert "Revisión" in encabezados
    assert "Cantidad" in encabezados

    assert {"revisar_registro", "corregir_registro"} <= _acciones_de_auditoria()


def test_devolver_reversa_el_avance_de_la_meta(client):
    """Un reporte devuelto deja de sumar hasta que se corrija."""
    empleado = _empleado_id()
    _entrar(client, "jefe", "1234")
    meta_id = _crear_meta(client, "Meta reversable", empleado, horas="10")

    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)
    client.post(
        "/registros",
        data={
            "meta_id": str(meta_id),
            "descripcion": "Avance reversable",
            "horas": "4",
        },
    )
    rid = _id_registro(EMPLEADO_USUARIO, "Avance reversable")
    assert _avance_de(meta_id) == 40

    # El jefe lo devuelve: 4 de 10 ya no cuenta.
    _entrar(client, "jefe", "1234")
    assert client.post(
        f"/registros/{rid}/revisar",
        data={
            "estado_revision": "correccion_pendiente",
            "observacion": "Contar mejor las horas",
        },
        follow_redirects=False,
    ).status_code == 303
    assert _avance_de(meta_id) == 0

    # Al corregir con 6 h vuelve a contar: 60%.
    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)
    assert client.post(
        f"/registros/{rid}/corregir",
        data={
            "descripcion": "Avance reversable corregido",
            "horas": "6",
            "estado": "completado",
        },
        follow_redirects=False,
    ).status_code == 303
    assert _avance_de(meta_id) == 60


def test_no_se_puede_revisar_ni_corregir_un_reporte_ajeno(client):
    _empleado_id()
    _entrar(client, "jefe", "1234")
    client.post("/registros", data={"descripcion": "Reporte solo del jefe", "horas": "1"})
    rid = _id_registro("jefe", "Reporte solo del jefe")

    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)

    revisar = client.post(
        f"/registros/{rid}/revisar",
        data={"estado_revision": "aprobado"},
        follow_redirects=False,
    )
    assert revisar.headers["location"].startswith("/?msg=")

    corregir = client.post(
        f"/registros/{rid}/corregir",
        data={"descripcion": "cambio indebido", "horas": "1"},
        follow_redirects=False,
    )
    assert corregir.headers["location"].startswith("/?msg=")

    formulario = client.get(f"/registros/{rid}/corregir", follow_redirects=False)
    assert formulario.status_code == 303
    assert formulario.headers["location"].startswith("/?msg=")

    db = SessionLocal()
    try:
        assert db.get(Registro, rid).descripcion == "Reporte solo del jefe"
    finally:
        db.close()


def test_correccion_invalida_no_cambia_nada(client):
    empleado = _empleado_id()
    _entrar(client, "jefe", "1234")
    meta_id = _crear_meta(client, "Meta de correccion invalida", empleado)

    _entrar(client, EMPLEADO_USUARIO, EMPLEADO_PIN)
    client.post(
        "/registros",
        data={
            "meta_id": str(meta_id),
            "descripcion": "Reporte valido del analista",
            "horas": "2",
        },
    )
    rid = _id_registro(EMPLEADO_USUARIO, "Reporte valido del analista")

    vacio = client.post(
        f"/registros/{rid}/corregir",
        data={"descripcion": "   ", "horas": "1"},
        follow_redirects=False,
    )
    assert "no puede estar vacía" in unquote(vacio.headers["location"])

    estado_malo = client.post(
        f"/registros/{rid}/corregir",
        data={"descripcion": "algo", "horas": "1", "estado": "inventado"},
        follow_redirects=False,
    )
    assert "Estado inválido" in unquote(estado_malo.headers["location"])

    db = SessionLocal()
    try:
        assert db.get(Registro, rid).descripcion == "Reporte valido del analista"
    finally:
        db.close()
