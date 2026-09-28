"""Configuracion comun de las pruebas.

La carpeta de datos se define aca, antes de importar la app, para no tocar la
base real de la oficina.

Ojo: los archivos ``test_NN_*.py`` comparten una misma base durante toda la
corrida y algunos se apoyan en datos que cargaron los anteriores, por eso van
numerados y conviene correrlos con ``pytest tests`` (o ``pytest``) entero. Los
ayudantes que usan varios modulos viven en ``helpers.py``.
"""

import os
import tempfile

os.environ["CG_DATA_DIR"] = tempfile.mkdtemp(prefix="cg-test-")
os.environ["CG_SECRET_KEY"] = "clave-de-prueba"
os.environ["CG_ADMIN_USUARIO"] = "jefe"
# El PIN de fabrica es distinto del que usan las pruebas: asi el jefe no queda
# obligado a cambiarlo en cada prueba y se puede probar el bloqueo aparte.
os.environ["CG_ADMIN_PIN"] = "9999"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from app.security import hash_pin, olvidar_pin_de_fabrica  # noqa: E402

_jefe_preparado = False


@pytest.fixture()
def client():
    """Arranca la app y deja al jefe con el PIN que usan todas las pruebas.

    La semilla le pone el PIN de fabrica (CG_ADMIN_PIN); aca se lo cambiamos a
    1234 una sola vez para que el resto de las pruebas no dependa del aviso de
    "cambia tu PIN".
    """
    global _jefe_preparado
    with TestClient(app) as c:
        if not _jefe_preparado:
            db = SessionLocal()
            try:
                jefe = db.query(Usuario).filter_by(usuario="jefe").one()
                jefe.pin_hash = hash_pin("1234")
                db.commit()
                id_jefe = jefe.id
            finally:
                db.close()
            olvidar_pin_de_fabrica(id_jefe)
            _jefe_preparado = True
        yield c
