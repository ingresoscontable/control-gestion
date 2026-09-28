"""Informes por rango de fechas libre y comparacion entre periodos.

Autocontenido: usa fechas fijas de mayo de 2026 para no pisar los datos de los
otros modulos, asi que se puede correr con
``pytest tests/test_19_informes_rango.py``.
"""

from datetime import date, datetime

from helpers import login

from app import reportes
from app.database import SessionLocal
from app.models import Registro, Usuario
from app.reportes import _comparar_cifra
from app.security import hash_pin

PIN = "4821"
DESDE = date(2026, 5, 4)  # lunes
HASTA = date(2026, 5, 15)  # viernes
ANTES_DESDE = date(2026, 4, 22)
ANTES_HASTA = date(2026, 5, 3)

_preparado = False


def _empleado(db, nombre_usuario: str) -> Usuario:
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


def _registro(usuario_id, fecha, creado_en, horas, cantidad=0.0, estado="completado"):
    return Registro(
        usuario_id=usuario_id,
        fecha=fecha,
        creado_en=datetime(creado_en.year, creado_en.month, creado_en.day, 9, 0),
        descripcion="reporte de prueba",
        horas=horas,
        cantidad=cantidad,
        estado=estado,
    )


def _preparar(db) -> None:
    """Crea el personal y sus reportes una sola vez para todos los tests."""
    global _preparado
    if _preparado:
        return
    uno = _empleado(db, "rangouno")
    dos = _empleado(db, "rangodos")
    db.add_all(
        [
            # Periodo del informe: 3 reportes, 12.5 horas, 14 de cantidad.
            _registro(uno.id, DESDE, DESDE, 4.0, cantidad=5.0),
            _registro(uno.id, DESDE.replace(day=5), DESDE.replace(day=9), 5.0, cantidad=5.0),
            _registro(
                uno.id,
                DESDE.replace(day=6),
                DESDE.replace(day=6),
                3.5,
                cantidad=4.0,
                estado="en_progreso",
            ),
            _registro(dos.id, HASTA, HASTA, 6.0),
            # Periodo anterior: uno solo, para que la comparacion tenga sentido.
            _registro(uno.id, ANTES_DESDE, ANTES_DESDE, 2.0, cantidad=1.0),
        ]
    )
    db.commit()
    _preparado = True


def _fila(resumen, login_usuario: str) -> dict:
    return next(
        fila for fila in resumen["por_persona"] if fila["usuario"].usuario == login_usuario
    )


def test_el_resumen_del_rango_trae_totales_dias_y_laborables(client):
    db = SessionLocal()
    try:
        _preparar(db)
        resumen = reportes.resumen_periodo(db, DESDE, HASTA)
        uno = _fila(resumen, "rangouno")
        dos = _fila(resumen, "rangodos")
    finally:
        db.close()

    totales = resumen["totales"]
    assert totales["reportes"] == 4
    assert totales["horas"] == 18.5
    assert totales["cantidad"] == 14.0
    assert totales["dias"] == 4
    assert totales["completados"] == 3
    assert totales["en_fecha"] == 3
    assert totales["puntualidad"] == 75
    # Dos semanas de lunes a viernes: el sabado y el domingo no cuentan.
    assert resumen["laborables"] == 10

    assert uno["reportes"] == 3
    assert uno["horas"] == 12.5
    assert uno["cantidad"] == 14.0
    assert uno["dias"] == 3
    assert uno["completados"] == 2
    assert uno["en_fecha"] == 2
    assert dos["reportes"] == 1


def test_sin_reportes_el_resumen_queda_en_cero_y_sin_puntualidad(client):
    db = SessionLocal()
    try:
        _preparar(db)
        resumen = reportes.resumen_periodo(db, date(2026, 6, 1), date(2026, 6, 30))
    finally:
        db.close()

    assert resumen["totales"]["reportes"] == 0
    assert resumen["totales"]["puntualidad"] is None
    assert resumen["totales"]["horas"] == 0.0
    assert all(fila["reportes"] == 0 for fila in resumen["por_persona"])


def test_el_periodo_anterior_es_el_mismo_largo_justo_antes(client):
    assert reportes.periodo_anterior(DESDE, HASTA) == (ANTES_DESDE, ANTES_HASTA)
    # Un solo dia tambien funciona.
    assert reportes.periodo_anterior(DESDE, DESDE) == (
        DESDE.replace(day=3),
        DESDE.replace(day=3),
    )


def test_los_tres_sentidos_de_la_comparacion(client):
    sube = _comparar_cifra(3, 1)
    assert sube["sentido"] == "sube"
    assert sube["texto"] == "+2"
    assert sube["actual"] == 3
    assert sube["anterior"] == 1

    baja = _comparar_cifra(1, 3)
    assert baja["sentido"] == "baja"
    assert baja["texto"] == "-2"

    igual = _comparar_cifra(2, 2)
    assert igual["sentido"] == "igual"
    assert igual["texto"] == "="

    con_decimales = _comparar_cifra(10.5, 8.0, decimales=1)
    assert con_decimales["texto"] == "+2.5"


def test_la_comparativa_arma_el_anterior_y_las_diferencias_por_persona(client):
    db = SessionLocal()
    try:
        _preparar(db)
        comparacion = reportes.comparativa(db, DESDE, HASTA)
        uno = next(
            fila
            for fila in comparacion["filas"]
            if fila["usuario"].usuario == "rangouno"
        )
        dos = next(
            fila
            for fila in comparacion["filas"]
            if fila["usuario"].usuario == "rangodos"
        )
    finally:
        db.close()

    assert comparacion["desde"] == ANTES_DESDE
    assert comparacion["hasta"] == ANTES_HASTA
    assert comparacion["anterior"]["totales"]["reportes"] == 1

    # Global: de 1 reporte a 4, y de 2.0 horas a 18.5.
    assert comparacion["reportes"]["sentido"] == "sube"
    assert comparacion["reportes"]["texto"] == "+3"
    assert comparacion["horas"]["texto"] == "+16.5"

    assert uno["reportes"]["actual"] == 3
    assert uno["reportes"]["anterior"] == 1
    assert uno["reportes"]["sentido"] == "sube"
    assert uno["horas"]["sentido"] == "sube"

    # Quien no tenia nada cargado antes tambien sube.
    assert dos["reportes"]["anterior"] == 0
    assert dos["reportes"]["texto"] == "+1"


def test_el_pdf_del_rango_se_genera_con_y_sin_comparacion(client):
    db = SessionLocal()
    try:
        _preparar(db)
        simple = reportes.generar_pdf_rango(db, DESDE, HASTA)
        comparado = reportes.generar_pdf_rango(db, DESDE, HASTA, comparar=True)
    finally:
        db.close()

    assert simple.startswith(b"%PDF")
    assert comparado.startswith(b"%PDF")
    # La version con comparacion trae una seccion mas, asi que es mas larga.
    assert len(comparado) > len(simple)


def test_el_pdf_mensual_sigue_saliendo_del_mismo_motor(client):
    db = SessionLocal()
    try:
        _preparar(db)
        pdf = reportes.generar_pdf_mensual(db, 2026, 5)
    finally:
        db.close()

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_la_pagina_de_informes_muestra_el_rango_y_la_comparacion(client):
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get(
        "/reportes",
        params={
            "desde": DESDE.isoformat(),
            "hasta": HASTA.isoformat(),
            "comparar": "1",
        },
    )
    assert pagina.status_code == 200
    assert "04/05/2026 al 15/05/2026" in pagina.text
    assert "día(s) laborables del período" in pagina.text
    assert "Comparación con el período anterior" in pagina.text
    assert "22/04/2026" in pagina.text
    assert "antes 1" in pagina.text


def test_sin_comparacion_la_pagina_no_muestra_esa_seccion(client):
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get(
        "/reportes", params={"desde": DESDE.isoformat(), "hasta": HASTA.isoformat()}
    )
    assert pagina.status_code == 200
    assert "04/05/2026 al 15/05/2026" in pagina.text
    assert "Comparación con el período anterior" not in pagina.text


def test_sin_fechas_se_usa_el_mes_en_curso(client):
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get("/reportes")
    assert pagina.status_code == 200
    assert date.today().replace(day=1).strftime("%d/%m/%Y") in pagina.text


def test_con_una_sola_fecha_se_arma_un_rango_util(client):
    assert login(client, "jefe", "1234").status_code == 303

    solo_desde = client.get("/reportes", params={"desde": DESDE.isoformat()})
    assert solo_desde.status_code == 200
    assert date.today().strftime("%d/%m/%Y") in solo_desde.text

    solo_hasta = client.get("/reportes", params={"hasta": HASTA.isoformat()})
    assert solo_hasta.status_code == 200
    assert date(2026, 5, 1).strftime("%d/%m/%Y") in solo_hasta.text


def test_las_fechas_al_reves_se_dan_vuelta(client):
    assert login(client, "jefe", "1234").status_code == 303

    pagina = client.get(
        "/reportes", params={"desde": HASTA.isoformat(), "hasta": DESDE.isoformat()}
    )
    assert pagina.status_code == 200
    assert "04/05/2026 al 15/05/2026" in pagina.text


def test_el_pdf_baja_por_la_ruta_con_el_nombre_del_rango(client):
    assert login(client, "jefe", "1234").status_code == 303

    respuesta = client.get(
        "/reportes/rango.pdf",
        params={"desde": DESDE.isoformat(), "hasta": HASTA.isoformat()},
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
    assert "informe_2026-05-04_2026-05-15.pdf" in respuesta.headers["content-disposition"]


def test_un_rango_demasiado_largo_se_rechaza(client):
    assert login(client, "jefe", "1234").status_code == 303

    demasiado = {"desde": "2000-01-01", "hasta": "2026-01-01"}
    pagina = client.get("/reportes", params=demasiado, follow_redirects=False)
    assert pagina.status_code == 303
    assert pagina.headers["location"].startswith("/reportes")
    assert "demasiado" in pagina.headers["location"]

    pdf = client.get("/reportes/rango.pdf", params=demasiado, follow_redirects=False)
    assert pdf.status_code == 303


def test_un_empleado_no_entra_a_los_informes(client):
    db = SessionLocal()
    try:
        _preparar(db)
    finally:
        db.close()

    assert login(client, "rangouno", PIN).status_code == 303
    pagina = client.get("/reportes", follow_redirects=False)
    assert pagina.status_code == 303
    assert "permiso" in pagina.headers["location"]

    pdf = client.get("/reportes/rango.pdf", follow_redirects=False)
    assert pdf.status_code == 303
