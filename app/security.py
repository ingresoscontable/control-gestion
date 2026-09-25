"""Hash de PIN y utilidades de red.

Se usa solo la librería estándar (hashlib) para no depender de paquetes
como passlib que quedan sin mantenimiento.
"""

import base64
import hashlib
import hmac
import os
import socket
import subprocess

ITERACIONES = 120_000
ALGORITMO = "sha256"


def hash_pin(pin: str) -> str:
    """Devuelve un hash con formato pbkdf2$iteraciones$salt$hash."""
    salt = os.urandom(16)
    derivado = hashlib.pbkdf2_hmac(ALGORITMO, pin.encode(), salt, ITERACIONES)
    return "$".join(
        [
            "pbkdf2",
            str(ITERACIONES),
            base64.b64encode(salt).decode(),
            base64.b64encode(derivado).decode(),
        ]
    )


def verificar_pin(pin: str, guardado: str) -> bool:
    """Compara un PIN en claro contra el hash guardado."""
    try:
        _, iteraciones, salt_b64, hash_b64 = guardado.split("$")
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(hash_b64)
        derivado = hashlib.pbkdf2_hmac(
            ALGORITMO, pin.encode(), salt, int(iteraciones)
        )
        return hmac.compare_digest(derivado, esperado)
    except (ValueError, TypeError):
        return False


def valida_pin(pin: str) -> str | None:
    """Devuelve un mensaje de error si el PIN no cumple el mínimo."""
    if not pin.isdigit():
        return "El PIN debe contener solo números."
    if not 4 <= len(pin) <= 10:
        return "El PIN debe tener entre 4 y 10 dígitos."
    return None


def _ips_desde_ifconfig() -> set[str]:
    """IP de todas las interfaces segun `ifconfig` (Linux y Android/Termux).

    Es el unico metodo que tambien ve interfaces secundarias, como el hotspot
    del telefono (ap0), que getaddrinfo no reporta. En Windows el comando no
    existe, asi que devuelve vacio y se usa el resto de los metodos.
    """
    try:
        salida = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()

    ips: set[str] = set()
    for linea in salida.splitlines():
        campos = linea.strip().split()
        if len(campos) >= 2 and campos[0] == "inet":
            # "inet 192.168.1.5 netmask ..." o "inet addr:192.168.1.5 ..."
            ips.add(campos[1].split(":")[-1])
    return ips


def ips_locales() -> list[str]:
    """Lista las IP de la red local para compartir el link con el equipo."""
    ips: set[str] = _ips_desde_ifconfig()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass

    # Truco clásico: abrir un socket "hacia afuera" revela la IP de la LAN.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass

    # Se descarta el loopback, que no le sirve a nadie de la red.
    return sorted(ip for ip in ips if not ip.startswith("127."))
