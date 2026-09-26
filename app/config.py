"""Configuración central de la aplicación.

Todo se puede sobreescribir con variables de entorno para no tener que
editar código al instalarlo en otra PC de la oficina.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carpeta donde vive la base SQLite (se crea sola).
DATA_DIR = Path(os.environ.get("CG_DATA_DIR", BASE_DIR / "data"))


def _clave_de_sesion() -> str:
    """Clave con la que se firma la cookie de sesión.

    Si no está definida CG_SECRET_KEY, se genera una distinta por instalación y
    se guarda en data/.secret_key (carpeta que ya está en .gitignore). Así una
    instalación no hereda la clave del repositorio y las sesiones siguen valiendo
    aunque se reinicie el servidor.
    """
    if valor := os.environ.get("CG_SECRET_KEY"):
        return valor

    archivo = DATA_DIR / ".secret_key"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if archivo.is_file():
            guardada = archivo.read_text(encoding="utf-8").strip()
            if guardada:
                return guardada
        nueva = secrets.token_urlsafe(48)
        archivo.write_text(nueva, encoding="utf-8")
        return nueva
    except OSError:
        # Sin permiso para escribir: se usa la clave de respaldo del código.
        # Las sesiones se invalidan si cambia, pero el sistema funciona.
        return "cambiar-esta-clave-en-produccion"


# Clave para firmar la cookie de sesión.
SECRET_KEY = _clave_de_sesion()

# Usuario jefe que se crea la primera vez que arranca la app.
ADMIN_USUARIO = os.environ.get("CG_ADMIN_USUARIO", "jefe")
ADMIN_PIN = os.environ.get("CG_ADMIN_PIN", "1234")
ADMIN_NOMBRE = os.environ.get("CG_ADMIN_NOMBRE", "Jefe de División")

HOST = os.environ.get("CG_HOST", "0.0.0.0")
PORT = int(os.environ.get("CG_PORT", "8000"))

# Respaldos automaticos de la base de datos.
BACKUP_DIR = Path(os.environ.get("CG_BACKUP_DIR", DATA_DIR / "respaldos"))
# Cada cuantas horas se hace un respaldo automatico.
BACKUP_HORAS = int(os.environ.get("CG_BACKUP_HORAS", "24"))
# Cuantos respaldos se conservan (los mas viejos se borran).
BACKUP_CONSERVAR = int(os.environ.get("CG_BACKUP_CONSERVAR", "30"))

APP_NAME = "Control de Gestión"
