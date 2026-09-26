"""Pruebas de la aplicación de Control de Gestión."""

import os
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote

# Se define la carpeta de datos antes de importar la app para no tocar la
# base real de la oficina.
os.environ["CG_DATA_DIR"] = tempfile.mkdtemp(prefix="cg-test-")
os.environ["CG_SECRET_KEY"] = "clave-de-prueba"
os.environ["CG_ADMIN_USUARIO"] = "jefe"
os.environ["CG_ADMIN_PIN"] = "1234"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app import backup, config, migraciones  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Meta, Registro, Usuario  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, usuario: str, pin: str):
    return client.post(
        "/login", data={"usuario": usuario, "pin": pin}, follow_redirects=False
    )


def test_login_sin_sesion_redirige(client):
    respuesta = client.get("/", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"


def test_pin_incorrecto_no_inicia_sesion(client):
    respuesta = login(client, "jefe", "0000")
    assert respuesta.status_code == 401
    assert "incorrecto" in respuesta.text


def test_pin_se_guarda_hasheado(client):
    db = SessionLocal()
    try:
        jefe = db.query(Usuario).filter_by(usuario="jefe").one()
        assert jefe.pin_hash != "1234"
        assert jefe.pin_hash.startswith("pbkdf2$")
    finally:
        db.close()


def test_jefe_entra_y_ve_su_panel(client):
    assert login(client, "jefe", "1234").status_code == 303
    panel = client.get("/")
    assert panel.status_code == 200
    assert "Resumen de hoy" in panel.text


def test_flujo_completo_jefe_y_empleado(client):
    assert login(client, "jefe", "1234").status_code == 303

    # El jefe crea dos accesos, uno con PIN inválido (debe rebotar).
    assert (
        client.post(
            "/equipo",
            data={"nombre": "Maria Perez", "usuario": "mperez", "pin": "12", "rol": "empleado"},
            follow_redirects=False,
        ).headers["location"]
        .startswith("/equipo")
    )
    assert client.post(
        "/equipo",
        data={
            "nombre": "Maria Perez",
            "usuario": "mperez",
            "cargo": "Analista contable",
            "pin": "4821",
            "rol": "empleado",
        },
        follow_redirects=False,
    ).status_code == 303

    # El jefe crea una meta asignada a Maria.
    db = SessionLocal()
    try:
        maria = db.query(Usuario).filter_by(usuario="mperez").one()
        maria_id = maria.id
    finally:
        db.close()

    assert client.post(
        "/metas",
        data={
            "titulo": "Conciliacion bancaria septiembre",
            "descripcion": "Cerrar la conciliacion del mes",
            "asignado_a": str(maria_id),
            "fecha_limite": "2026-10-05",
        },
        follow_redirects=False,
    ).status_code == 303
    assert "Conciliacion bancaria septiembre" in client.get("/metas").text

    # Maria entra y registra su trabajo del dia.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303

    panel = client.get("/")
    assert "Conciliacion bancaria septiembre" in panel.text

    assert client.post(
        "/registros",
        data={
            "descripcion": "Revisadas 40 facturas pendientes",
            "horas": "6,5",
            "estado": "en_progreso",
            "fecha": date.today().isoformat(),
        },
        follow_redirects=False,
    ).status_code == 303

    panel = client.get("/")
    assert "Revisadas 40 facturas pendientes" in panel.text

    # Un empleado no puede administrar metas ni ver el equipo.
    assert client.get("/metas", follow_redirects=False).headers["location"].startswith("/?msg=")
    assert client.get("/equipo", follow_redirects=False).headers["location"].startswith("/?msg=")


def test_jefe_ve_registros_y_horas(client):
    assert login(client, "jefe", "1234").status_code == 303
    respuesta = client.get("/registros")
    assert respuesta.status_code == 200
    assert "Revisadas 40 facturas pendientes" in respuesta.text
    assert "6.5 horas acumuladas" in respuesta.text


def test_texto_vacio_no_crea_registro(client):
    assert login(client, "jefe", "1234").status_code == 303
    respuesta = client.post(
        "/registros", data={"descripcion": "   "}, follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert "no puede estar vacía" in unquote(respuesta.headers["location"])


def _id_usuario(login_usuario: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Usuario).filter_by(usuario=login_usuario).one().id
    finally:
        db.close()


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


def _id_registro_de(login_usuario: str) -> int:
    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario=login_usuario).one()
        registro = (
            db.query(Registro)
            .filter(Registro.usuario_id == persona.id)
            .order_by(Registro.id)
            .first()
        )
        return registro.id
    finally:
        db.close()


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


def _id_meta(titulo: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Meta).filter_by(titulo=titulo).one().id
    finally:
        db.close()


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


def test_migracion_agrega_columnas_a_una_base_vieja():
    import sqlite3

    from sqlalchemy import create_engine

    carpeta = Path(tempfile.mkdtemp(prefix="cg-migracion-"))
    archivo = carpeta / "viejo.db"

    conexion = sqlite3.connect(archivo)
    conexion.execute("CREATE TABLE registros (id INTEGER PRIMARY KEY, descripcion TEXT)")
    conexion.execute("CREATE TABLE metas (id INTEGER PRIMARY KEY, titulo TEXT)")
    conexion.commit()
    conexion.close()

    motor = create_engine(f"sqlite:///{archivo}")
    original = migraciones.engine
    migraciones.engine = motor
    try:
        migraciones.aplicar_migraciones()
    finally:
        migraciones.engine = original

    conexion = sqlite3.connect(archivo)
    try:
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(registros)")}
        columnas_metas = {
            fila[1] for fila in conexion.execute("PRAGMA table_info(metas)")
        }
    finally:
        conexion.close()
    assert {"comentario", "comentado_en"} <= columnas
    assert "horas_estimadas" in columnas_metas


def test_historial_por_persona(client):
    assert login(client, "jefe", "1234").status_code == 303
    maria_id = _id_usuario("mperez")

    pagina = client.get(f"/personas/{maria_id}")
    assert pagina.status_code == 200
    assert "Maria Perez" in pagina.text
    assert "Historial de reportes" in pagina.text
    assert "Revisadas 40 facturas pendientes" in pagina.text
    assert "Metas de Maria" in pagina.text

    # El filtro por fechas tambien funciona aca.
    vacio = client.get(
        f"/personas/{maria_id}", params={"desde": "2000-01-01", "hasta": "2000-01-31"}
    )
    assert "No hay reportes con esos filtros" in vacio.text

    # Usuario inexistente.
    assert client.get(
        "/personas/9999", follow_redirects=False
    ).headers["location"].startswith("/equipo?msg=")

    # Un empleado no entra al historial de nadie.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get(
        f"/personas/{maria_id}", follow_redirects=False
    ).headers["location"].startswith("/?msg=")


def test_grafico_de_horas_en_el_panel(client):
    assert login(client, "jefe", "1234").status_code == 303
    panel = client.get("/")
    assert "Horas por semana" in panel.text
    assert 'class="col c1"' in panel.text
    assert "La barra más alta" in panel.text

    # El empleado no ve el grafico del equipo.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert "Horas por semana" not in client.get("/").text


def test_horas_por_semana_escala_las_barras():
    from app.metricas import horas_por_semana

    db = SessionLocal()
    try:
        equipo = db.query(Usuario).order_by(Usuario.nombre).all()
        datos = horas_por_semana(db, equipo, date.today(), semanas=3)
    finally:
        db.close()

    assert len(datos["bloques"]) == 3
    assert datos["bloques"][-1]["actual"] is True
    assert datos["bloques"][0]["actual"] is False

    altos = [barra["alto"] for bloque in datos["bloques"] for barra in bloque["barras"]]
    assert max(altos) == 100  # la barra mas alta siempre llega al tope
    assert all(0 <= alto <= 100 for alto in altos)
    assert datos["bloques"][-1]["total"] > 0  # la semana en curso tiene horas
    assert datos["hay_datos"] is True


def test_ips_locales_incluye_el_hotspot(monkeypatch):
    from app import security

    class Resultado:
        stdout = (
            "lo: flags=73<UP,LOOPBACK,RUNNING>\n"
            "        inet 127.0.0.1  netmask 255.0.0.0\n"
            "wlan0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>\n"
            "        inet 192.168.1.47  netmask 255.255.255.0\n"
            "ap0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>\n"
            "        inet 10.187.127.38  netmask 255.255.255.0\n"
        )

    monkeypatch.setattr(security.subprocess, "run", lambda *a, **k: Resultado())
    ips = security.ips_locales()

    assert "192.168.1.47" in ips  # la Wi-Fi a la que esta conectado
    assert "10.187.127.38" in ips  # el hotspot que comparte
    assert "127.0.0.1" not in ips  # el loopback no sirve para la red


def test_ips_locales_acepta_el_formato_viejo_de_ifconfig(monkeypatch):
    from app import security

    class Resultado:
        stdout = (
            "eth0: flags=4163<UP,BROADCAST,RUNNING>\n"
            "        inet addr:192.168.0.10  Bcast:192.168.0.255  Mask:255.255.255.0\n"
        )

    monkeypatch.setattr(security.subprocess, "run", lambda *a, **k: Resultado())
    assert "192.168.0.10" in security.ips_locales()


def test_ips_locales_sin_ifconfig_no_falla(monkeypatch):
    from app import security

    def explota(*args, **kwargs):
        raise FileNotFoundError("ifconfig no existe")

    monkeypatch.setattr(security.subprocess, "run", explota)
    assert isinstance(security.ips_locales(), list)


def test_guia_para_el_equipo(client):
    assert login(client, "mperez", "4821").status_code == 303
    guia = client.get("/guia")
    assert guia.status_code == 200
    assert "Registrar lo que hiciste" in guia.text
    assert "en progreso" in guia.text
    assert "Cambiar mi PIN" in guia.text


def test_reporte_pdf_incluye_el_avance(client, monkeypatch):
    import fpdf

    original = fpdf.FPDF.__init__

    def sin_compresion(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.set_compression(False)  # deja el texto legible para poder verificarlo

    monkeypatch.setattr(fpdf.FPDF, "__init__", sin_compresion)

    assert login(client, "jefe", "1234").status_code == 303
    client.post(
        "/metas",
        data={"titulo": "Meta del PDF", "horas_estimadas": "8"},
        follow_redirects=False,
    )

    respuesta = client.get("/reportes/mensual.pdf")
    assert respuesta.status_code == 200

    texto = respuesta.content.decode("latin-1")
    assert "Avance promedio de metas activas" in texto
    assert "Metas con plazo vencido" in texto
    assert "Meta del PDF" in texto
    # Encabezados de la tabla de metas, incluida la columna nueva de avance.
    for encabezado in ("Asignada a", "Plazo", "Avances mes", "Estado"):
        assert encabezado in texto


def test_exportar_excel_con_filtros(client):
    assert login(client, "jefe", "1234").status_code == 303

    respuesta = client.get("/registros/exportar.xlsx")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment; filename=" in respuesta.headers["content-disposition"]
    assert respuesta.content[:2] == b"PK"  # un .xlsx es un zip

    hoja = load_workbook(BytesIO(respuesta.content)).active
    assert hoja["A1"].value == "Fecha"
    textos = [c.value for fila in hoja.iter_rows() for c in fila if c.value]
    assert "Revisadas 40 facturas pendientes" in textos
    assert "TOTAL HORAS" in textos

    # Filtrando por una persona sin registros, el archivo sale sin datos.
    filtrado = client.get("/registros/exportar.xlsx", params={"usuario_id": "999"})
    valores = [
        c.value
        for fila in load_workbook(BytesIO(filtrado.content)).active.iter_rows()
        for c in fila
        if c.value
    ]
    assert "Revisadas 40 facturas pendientes" not in valores

    # Un empleado no puede exportar.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    assert client.get(
        "/registros/exportar.xlsx", follow_redirects=False
    ).headers["location"].startswith("/?msg=")


def test_redireccion_sin_json_en_el_cuerpo(client):
    """La redireccion de seguridad responde 303 con Location y sin cuerpo."""
    respuesta = client.get("/", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"
    assert "application/json" not in respuesta.headers.get("content-type", "")
    assert respuesta.content == b""


def test_clave_de_sesion_propia_por_instalacion(tmp_path, monkeypatch):
    """Sin CG_SECRET_KEY se genera una clave por instalacion y se reutiliza."""
    monkeypatch.delenv("CG_SECRET_KEY", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    primera = config._clave_de_sesion()
    assert len(primera) >= 32
    assert config._clave_de_sesion() == primera
    assert (tmp_path / ".secret_key").read_text(encoding="utf-8") == primera

    # Si el ambiente define la clave, manda la del ambiente.
    monkeypatch.setenv("CG_SECRET_KEY", "la-que-diga-el-ambiente")
    assert config._clave_de_sesion() == "la-que-diga-el-ambiente"


def test_aviso_si_el_respaldo_queda_en_el_mismo_disco(client):
    # Por defecto los respaldos van a data/respaldos: mismo disco que la base.
    assert backup.respaldos_en_mismo_disco() is True
    assert login(client, "jefe", "1234").status_code == 303
    assert "mismo disco" in client.get("/respaldos").text


def test_restaurar_respaldo(client):
    assert login(client, "jefe", "1234").status_code == 303

    client.post(
        "/metas", data={"titulo": "Meta que va a volver"}, follow_redirects=False
    )
    client.post("/respaldos/ahora", follow_redirects=False)
    respaldo = max(
        config.BACKUP_DIR.glob("control_*_manual.db"),
        key=lambda ruta: ruta.stat().st_mtime,
    )

    meta_id = _id_meta("Meta que va a volver")
    client.post(f"/metas/{meta_id}/eliminar", follow_redirects=False)

    db = SessionLocal()
    try:
        assert db.query(Meta).filter_by(titulo="Meta que va a volver").count() == 0
    finally:
        db.close()

    respuesta = client.post(
        "/respaldos/restaurar", data={"nombre": respaldo.name}, follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert "Base restaurada" in unquote(respuesta.headers["location"])

    db = SessionLocal()
    try:
        assert db.query(Meta).filter_by(titulo="Meta que va a volver").count() == 1
    finally:
        db.close()

    # La pagina lista el respaldo y la copia de seguridad previa.
    assert "antes-de-restaurar" in client.get("/respaldos").text

    # Un empleado no puede restaurar.
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert login(client, "mperez", "4821").status_code == 303
    denegado = client.post(
        "/respaldos/restaurar", data={"nombre": respaldo.name}, follow_redirects=False
    )
    assert denegado.status_code == 303
    assert denegado.headers["location"].startswith("/?msg=")


def test_restaurar_rechaza_archivos_que_no_son_respaldos(client):
    assert login(client, "jefe", "1234").status_code == 303

    (config.BACKUP_DIR / "pepito.txt").write_text("hola", encoding="utf-8")
    (config.BACKUP_DIR / "control_basura.db").write_text(
        "esto no es sqlite", encoding="utf-8"
    )

    casos = [
        "../../control.db",  # fuera de la carpeta de respaldos
        "no_existe.db",  # no esta
        "pepito.txt",  # esta pero no tiene formato de respaldo
        "control_basura.db",  # tiene el formato pero esta corrupto
    ]
    for nombre in casos:
        respuesta = client.post(
            "/respaldos/restaurar", data={"nombre": nombre}, follow_redirects=False
        )
        assert respuesta.status_code == 303
        assert "No se pudo restaurar" in unquote(respuesta.headers["location"]), nombre

