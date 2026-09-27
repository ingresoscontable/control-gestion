"""Punto de entrada del sistema de Control de Gestion.

Uso:
    python main.py

Levanta el servidor en 0.0.0.0 para que las demas PC de la oficina
entren por la red local. Para detenerlo: Ctrl+C.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.security import ips_locales  # noqa: E402

FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
FECHA = "%Y-%m-%d %H:%M:%S"


def configurar_logging() -> None:
    """Escribe el log del sistema en data/sistema.log y en la consola.

    Sin esto los respaldos automaticos fallidos quedan invisibles, sobre todo
    cuando el servidor corre oculto (iniciar-oculto.vbs) y nadie ve la salida
    de la consola.
    """
    nivel = getattr(logging, config.LOG_LEVEL, logging.INFO)
    formato = logging.Formatter(FORMATO, FECHA)

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    archivo = RotatingFileHandler(
        config.DATA_DIR / "sistema.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    archivo.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    raiz.addHandler(consola)
    raiz.addHandler(archivo)
    logging.info(
        "Log del sistema en %s (nivel %s)",
        config.DATA_DIR / "sistema.log",
        config.LOG_LEVEL,
    )


def mostrar_banner() -> None:
    linea = "=" * 64
    print(linea)
    print(f"  {config.APP_NAME} - servidor de la oficina")
    print(linea)
    print(f"  En esta PC:   http://localhost:{config.PORT}")
    for ip in ips_locales():
        print(f"  Otras PC:     http://{ip}:{config.PORT}")
    if not ips_locales():
        print("  Otras PC:     (no se detecto red local, revisa la conexion)")
    print("-" * 64)
    print("  Deja esta ventana abierta mientras se usa el sistema.")
    print("  Para detenerlo presiona Ctrl+C.")
    print(linea)


def main() -> None:
    configurar_logging()
    mostrar_banner()
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
