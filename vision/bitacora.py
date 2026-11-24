"""
bitacora.py
===========
Registro de eventos del sistema (monedas, servos, carrito, conexiones, ordenes
de JARVIS). Lo usan todos los modulos; la interfaz lo muestra en vivo y JARVIS
lo lee para responder "que ha pasado".

    import bitacora
    bitacora.registrar("moneda", "$500 nueva detectada", voz="Quinientos pesos")
"""

import collections
import threading
import time
from datetime import datetime

_eventos = collections.deque(maxlen=400)
_lock = threading.Lock()
_n = 0


def registrar(tipo, texto, voz=None, **datos):
    """tipo: moneda | servo | carrito | conexion | banda | jarvis | sistema.
    voz: frase corta para que JARVIS la diga en voz alta (None = no se anuncia)."""
    global _n
    with _lock:
        _n += 1
        ev = {"id": _n, "t": time.time(), "hora": datetime.now().strftime("%H:%M:%S"),
              "tipo": tipo, "texto": texto, "voz": voz, **datos}
        _eventos.append(ev)
    return ev


def desde(ultimo_id):
    """Eventos con id mayor que ultimo_id (para mandarlos por WebSocket)."""
    with _lock:
        return [e for e in _eventos if e["id"] > ultimo_id]


def ultimos(n=30, tipo=None):
    with _lock:
        lista = [e for e in _eventos if tipo is None or e["tipo"] == tipo]
    return lista[-n:]


def ultimo_id():
    return _n


def texto_reciente(n=25):
    """Resumen legible para JARVIS."""
    ahora = time.time()
    lineas = []
    for e in ultimos(n):
        hace = int(ahora - e["t"])
        hace_txt = f"hace {hace} s" if hace < 120 else f"hace {hace // 60} min"
        lineas.append(f"- {e['hora']} ({hace_txt}) [{e['tipo']}] {e['texto']}")
    return "\n".join(lineas) if lineas else "- (sin eventos todavia)"
