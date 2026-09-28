from datetime import date

from helpers import (
    _id_usuario,
    login,
)

from app.database import SessionLocal
from app.models import Usuario


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


