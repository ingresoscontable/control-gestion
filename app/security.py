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
import threading
import time

from . import config

ITERACIONES = 120_000
ALGORITMO = "sha256"

# Login: cuantos fallos seguidos aguanta y cuanto se bloquea.
LOGIN_INTENTOS = 5
LOGIN_BLOQUEO = 300.0  # 5 minutos
LOGIN_BLOQUEO_MAXIMO = 1800.0  # 30 minutos, con backoff
LOGIN_VENTANA = 900.0  # los fallos se olvidan a los 15 minutos


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


class LimitadorDeIntentos:
    """Bloquea el login tras varios fallos seguidos de la misma IP y usuario.

    Los endpoints son `def` y corren en el threadpool, asi que todo lo que
    toca el contador va bajo un Lock. Vive en memoria: al reiniciar el
    proceso se olvida, que es lo que corresponde. Cada vez que vuelve a
    bloquear, el bloqueo se dobla (backoff) hasta el tope.
    """

    def __init__(
        self,
        intentos: int = LOGIN_INTENTOS,
        bloqueo: float = LOGIN_BLOQUEO,
        bloqueo_maximo: float = LOGIN_BLOQUEO_MAXIMO,
        ventana: float = LOGIN_VENTANA,
    ):
        self.intentos = intentos
        self.bloqueo = bloqueo
        self.bloqueo_maximo = bloqueo_maximo
        self.ventana = ventana
        self._fallos: dict[str, list[float]] = {}
        self._bloqueos: dict[str, float] = {}
        self._ciclos: dict[str, int] = {}
        self._lock = threading.Lock()

    def restante(self, clave: str) -> float:
        """Segundos que faltan para volver a dejar intentar (0 = libre)."""
        with self._lock:
            faltan = self._bloqueos.get(clave, 0.0) - time.monotonic()
            return faltan if faltan > 0 else 0.0

    def registrar_fallo(self, clave: str) -> float:
        """Suma un fallo y devuelve los segundos de bloqueo (0 = sigue libre)."""
        with self._lock:
            ahora = time.monotonic()
            recientes = [
                t for t in self._fallos.get(clave, ()) if ahora - t <= self.ventana
            ]
            recientes.append(ahora)
            self._fallos[clave] = recientes
            if len(recientes) < self.intentos:
                return 0.0
            ciclo = self._ciclos.get(clave, 0) + 1
            self._ciclos[clave] = ciclo
            duracion = min(self.bloqueo * (2 ** (ciclo - 1)), self.bloqueo_maximo)
            self._bloqueos[clave] = ahora + duracion
            del self._fallos[clave]
            return duracion

    def limpiar(self, clave: str) -> None:
        """Un login bien hecho empieza de cero con esa clave."""
        with self._lock:
            self._fallos.pop(clave, None)
            self._bloqueos.pop(clave, None)
            self._ciclos.pop(clave, None)


intentos_login = LimitadorDeIntentos()

# Si el PIN todavia es el de fabrica (CG_ADMIN_PIN), quien entra tiene que
# cambiarlo antes de usar el sistema. PBKDF2 con 120.000 iteraciones cuesta
# ~100 ms, asi que el resultado se guarda en memoria por usuario.
_pins_de_fabrica: dict[int, bool] = {}
_lock_pins = threading.Lock()


def es_pin_de_fabrica(usuario_id: int, pin_hash: str) -> bool:
    with _lock_pins:
        guardado = _pins_de_fabrica.get(usuario_id)
    if guardado is not None:
        return guardado
    resultado = verificar_pin(config.ADMIN_PIN, pin_hash)
    with _lock_pins:
        _pins_de_fabrica[usuario_id] = resultado
    return resultado


def olvidar_pin_de_fabrica(usuario_id: int) -> None:
    """Se llama cuando el usuario cambia su PIN."""
    with _lock_pins:
        _pins_de_fabrica.pop(usuario_id, None)


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
