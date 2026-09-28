"""Textos legales: paginas publicas y pie con los enlaces.

Autocontenido: no toca datos de otros modulos, asi que se puede correr con
``pytest tests/test_18_legal.py``.
"""

from helpers import login

from app.main import DOCUMENTOS_LEGALES

CLAVES = [clave for clave, _nombre in DOCUMENTOS_LEGALES]


def test_las_paginas_legales_se_leen_sin_iniciar_sesion(client):
    for clave in CLAVES:
        pagina = client.get(f"/legal/{clave}", follow_redirects=False)
        assert pagina.status_code == 200
        assert "Control de Gestión" in pagina.text


def test_un_documento_que_no_existe_devuelve_404(client):
    assert client.get("/legal/inexistente", follow_redirects=False).status_code == 404


def test_el_pie_del_login_lleva_a_los_cuatro_documentos(client):
    pagina = client.get("/login")
    assert pagina.status_code == 200
    for clave in CLAVES:
        assert f'href="/legal/{clave}"' in pagina.text


def test_la_privacidad_dice_que_datos_guarda_y_cuales_no(client):
    pagina = client.get("/legal/privacidad")
    assert pagina.status_code == 200
    assert "Datos que el programa no pide ni guarda" in pagina.text
    assert "solo en memoria y por menos de 24 horas" in pagina.text


def test_la_privacidad_aclara_que_no_se_piden_datos_financieros(client):
    pagina = client.get("/legal/privacidad")
    assert pagina.status_code == 200
    assert "El detalle importante: el campo de texto libre" in pagina.text
    assert "Montos de ingresos" in pagina.text
    assert "Queda guardado tal cual" in pagina.text or "queda guardado tal cual" in pagina.text
    # Y que el marco citado es el venezolano, no el de otro pais.
    assert "Normativa aplicable (Venezuela)" in pagina.text
    assert "Bolivariana de Venezuela" in pagina.text
    assert "Ley 25.326" not in pagina.text
    # Y avisa que el modelo hay que adaptarlo a la normativa del lugar.
    assert "modelo genérico y orientativo" in pagina.text


def test_los_terminos_aclaran_que_no_es_un_control_de_asistencia(client):
    pagina = client.get("/legal/terminos")
    assert pagina.status_code == 200
    assert "control de asistencia" in pagina.text
    assert "no captura pantallas, no registra teclas" in pagina.text
    assert "tal cual" in pagina.text
    assert "nombres de empresas que pagaron" in pagina.text
    assert "Aviso sobre la normativa aplicable (Venezuela)" in pagina.text


def test_los_cookies_avisan_que_solo_hay_una_cookie(client):
    pagina = client.get("/legal/cookies")
    assert pagina.status_code == 200
    assert "session" in pagina.text
    assert "Cookies de terceros, ni botones sociales" in pagina.text
    assert "Nota sobre la normativa aplicable (Venezuela)" in pagina.text


def test_la_pagina_de_licencia_trae_el_texto_de_la_mit(client):
    pagina = client.get("/legal/licencia")
    assert pagina.status_code == 200
    assert "MIT License" in pagina.text
    assert "WITHOUT WARRANTY OF ANY KIND" in pagina.text


def test_despues_de_entrar_todas_las_paginas_muestran_el_pie_legal(client):
    assert login(client, "jefe", "1234").status_code == 303
    pagina = client.get("/")
    assert pagina.status_code == 200
    assert 'class="pie-legal"' in pagina.text
    for clave in CLAVES:
        assert f'href="/legal/{clave}"' in pagina.text


def test_los_documentos_se_enlazan_entre_si(client):
    pagina = client.get("/legal/cookies")
    assert 'class="legal-nav"' in pagina.text
    assert 'class="activo"' in pagina.text
