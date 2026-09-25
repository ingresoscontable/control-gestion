"""Punto de entrada del sistema de Control de Gestion.

Uso:
    python main.py

Levanta el servidor en 0.0.0.0 para que las demas PC de la oficina
entren por la red local. Para detenerlo: Ctrl+C.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.security import ips_locales  # noqa: E402


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
    mostrar_banner()
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
