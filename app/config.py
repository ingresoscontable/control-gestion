"""Configuración central de la aplicación.

Todo se puede sobreescribir con variables de entorno para no tener que
editar código al instalarlo en otra PC de la oficina.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carpeta donde vive la base SQLite (se crea sola).
DATA_DIR = Path(os.environ.get("CG_DATA_DIR", BASE_DIR / "data"))

# Clave para firmar la cookie de sesión. Cámbiala en cada instalación.
SECRET_KEY = os.environ.get("CG_SECRET_KEY", "cambiar-esta-clave-en-produccion")

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
