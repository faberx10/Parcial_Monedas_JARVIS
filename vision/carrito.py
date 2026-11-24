"""
carrito.py
==========
Enlace PC -> carrito de transporte (ESP32 + L298N), para manejarlo desde la
misma interfaz del proyecto.

El carrito (firmware carrito_transporte) entiende:

    GET /cmd?d=<F|B|L|R|FL|FR|BL|BR|S|X>&s=<0-100>     /ping

  F adelante, B atras, L/R giro en el sitio, FL/FR/BL/BR curvas,
  S soltar (frena con rampa), X parar ya.  s = velocidad en %.
  Si pasan 400 ms sin ordenes el carrito se detiene solo.

La pagina web NO habla directo con el carrito: le dice al PC "mantengo
adelante al 50 %" (cada 100 ms mientras el boton esta presionado) y aqui un
hilo reenvia la orden al carrito. Asi:
  - el carrito recibe un ritmo constante de ordenes aunque el navegador se trabe;
  - si la pagina se cierra o deja de mandar (>0,35 s), este hilo frena el carrito;
  - si el PC o el WiFi se caen, el propio carrito se detiene a los 400 ms.
"""

import socket
import threading
import collections
import time

import requests

import bitacora
import config
import datos_proyecto as dp

DIRECCIONES = {"F", "B", "L", "R", "FL", "FR", "BL", "BR"}
PERIODO_S = 0.10          # cada cuanto se reenvia la orden mientras se mantiene
VIGENCIA_S = 0.35         # sin ordenes de la pagina por este tiempo -> frenar
TIMEOUT_S = 0.35


class Carrito:
    def __init__(self, host=None):
        self.host = host or config.CARRITO_HOST
        self.url = None               # http://IP (se resuelve carrito-g3.local una vez)
        self.conectada = False
        self.errores = 0
        self.d, self.v = "S", 0       # lo que se esta mandando ahora
        self._orden = ("S", 0, 0.0)   # (direccion, velocidad, hora) pedida por la pagina
        self._parar = False
        self._lock = threading.Lock()
        self._ses = requests.Session()
        # historial de movimientos (para la interfaz y JARVIS)
        self._mov = None              # movimiento en curso: {"d", "v", "inicio"}
        self.movimientos = collections.deque(maxlen=30)
        self.n_movimientos = 0
        self.tiempo_mov_s = 0.0
        threading.Thread(target=self._vigilar, daemon=True).start()
        threading.Thread(target=self._bucle, daemon=True).start()

    # ------------------------------------------------------------------
    def mover(self, d, v):
        """La pagina pide moverse en la direccion d a v % (se repite mientras siga llegando)."""
        d = (d or "S").upper()
        v = max(0, min(100, int(v)))
        with self._lock:
            if d == "X":
                self._parar = True
                self._orden = ("S", 0, 0.0)
            elif d in DIRECCIONES:
                self._orden = (d, v, time.time())
            else:
                self._orden = ("S", 0, 0.0)

    def parar(self):
        self.mover("X", 0)

    def estado(self):
        ahora = time.time()
        ult = self.movimientos[-1] if self.movimientos else None
        return {"conectada": self.conectada, "host": self.host, "d": self.d, "v": self.v,
                "direccion": dp.DIRECCION.get(self.d, self.d), "errores": self.errores,
                "movimientos": self.n_movimientos, "tiempo_mov_s": round(self.tiempo_mov_s, 1),
                "en_curso_s": round(ahora - self._mov["inicio"], 1) if self._mov else 0.0,
                "ultimo": None if not ult else {
                    "d": ult["d"], "direccion": dp.DIRECCION.get(ult["d"], ult["d"]), "v": ult["v"],
                    "duracion_s": round(ult["fin"] - ult["inicio"], 1),
                    "hace_s": round(ahora - ult["fin"], 1)}}

    def _cambio(self, d, v):
        """Registra el inicio/fin de cada movimiento."""
        ahora = time.time()
        m = self._mov
        if m and (m["d"], m["v"]) == (d, v):
            return
        if m:                                       # termina el movimiento anterior
            m["fin"] = ahora
            dur = ahora - m["inicio"]
            self.movimientos.append(m)
            self.tiempo_mov_s += dur
            bitacora.registrar("carrito", f"Carrito {dp.DIRECCION.get(m['d'], m['d'])} al {m['v']} % "
                               f"durante {dur:.1f} s", d=m["d"], v=m["v"], duracion=round(dur, 2))
        if d in DIRECCIONES:
            self._mov = {"d": d, "v": v, "inicio": ahora}
            self.n_movimientos += 1
        else:
            self._mov = None

    # ------------------------------------------------------------------
    def _resolver(self):
        nombre, _, puerto = self.host.partition(":")
        try:
            return f"http://{socket.gethostbyname(nombre)}" + (f":{puerto}" if puerto else "")
        except OSError:
            return None

    def _pedir(self, d, v):
        """Una orden al carrito. No resuelve nombres (eso lo hace _vigilar): asi un
        carrito apagado no congela el hilo esperando al DNS."""
        url = self.url
        if not url:
            return False
        try:
            return self._ses.get(url + "/cmd", params={"d": d, "s": v}, timeout=TIMEOUT_S).ok
        except requests.RequestException:
            return False

    def _bucle(self):
        moviendo = False
        while True:
            t0 = time.time()
            with self._lock:
                d, v, hora = self._orden
                parar, self._parar = self._parar, False
            activa = d in DIRECCIONES and (t0 - hora) < VIGENCIA_S
            if parar:
                self._pedir("X", 0)
                self.d, self.v, moviendo = "S", 0, False
                self._cambio("S", 0)
            elif activa:
                if not self._pedir(d, v):
                    self.errores += 1
                self.d, self.v, moviendo = d, v, True
                self._cambio(d, v)
            elif moviendo:                 # solto el boton, se cerro la pagina...
                self._pedir("S", 0)
                self.d, self.v, moviendo = "S", 0, False
                self._cambio("S", 0)
            time.sleep(max(0.0, PERIODO_S - (time.time() - t0)))

    def _vigilar(self):
        """Ping cada 3 s para el indicador de la interfaz."""
        avisado = None
        while True:
            ok = False
            url = self.url or self._resolver()
            if url:
                try:
                    ok = self._ses.get(url + "/ping", timeout=1.5).ok
                except requests.RequestException:
                    ok = False
                if ok:
                    self.url = url
            if not ok:
                self.url = None
            self.conectada = ok
            if ok != avisado:
                print(f"[Carrito] {'conectado en ' + self.url if ok else 'SIN conexion con ' + self.host}"
                      + ("" if ok else "  (mismo WiFi? pon su IP en config.CARRITO_HOST)"))
                if avisado is not None or ok:
                    bitacora.registrar("conexion", "Carrito de transporte conectado" if ok
                                       else "Se perdió la conexión con el carrito",
                                       voz="Carrito en línea" if ok else "Atención: perdí la conexión con el carrito")
                avisado = ok
            time.sleep(3)
