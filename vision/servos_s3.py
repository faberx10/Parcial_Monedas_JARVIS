"""
servos_s3.py
============
Enlace PC -> ESP32-S3 (banda + servos de clasificacion).

Cada vez que la interfaz CUENTA una moneda, se le avisa a la S3:

    GET http://banda-s3.local/moneda?v=500&d=12

  v = valor de la moneda en pesos (la S3 elige el servo: 1000/500 -> 1,
      200 -> 2, 100 -> 3, 50 -> 4)
  d = milisegundos que ya pasaron en el PC desde que se conto (la S3 los
      descuenta de su retardo)

Ademas, cada 2 s se lee /estado de la S3 (angulos, velocidad de la banda,
retardos, monedas recibidas) para la interfaz y JARVIS, y se exponen las
ordenes que JARVIS puede dar: velocidad de la banda, probar un servo y
servos a reposo.

Los avisos salen en un hilo aparte: si la S3 no responde, el video y el
conteo siguen normales y solo se muestra un aviso en la consola.
"""

import queue
import socket
import threading
import time

import requests

import bitacora
import config
import datos_proyecto as dp

VIGENCIA_S = 2.0       # un aviso mas viejo que esto ya llegaria tarde a la paleta: se descarta
TIMEOUT_S = 1.5
N_SERVOS = 4


class ServosS3:
    def __init__(self, host=None):
        self.host = host or config.S3_HOST
        self.url = None             # http://IP (se resuelve banda-s3.local una sola vez)
        self.conectada = False
        self.enviadas = 0
        self.fallidas = 0
        self.s3 = {}                # ultimo /estado de la S3
        self.vel_anterior = 50      # para "reanudar la banda"
        self.por_servo = [{"enviadas": 0, "ultima": None, "activo_desde": 0.0, "activo_hasta": 0.0,
                           "ultima_clase": None} for _ in range(N_SERVOS)]
        self._lock = threading.Lock()
        self._cola = queue.Queue()
        self._ses = requests.Session()
        threading.Thread(target=self._vigilar, daemon=True).start()
        threading.Thread(target=self._enviar_pendientes, daemon=True).start()

    # ------------------------------------------------------------------
    def enviar(self, clase):
        """Avisa una moneda contada (no bloquea)."""
        valor = config.CLASES.get(clase, (None, 0))[1]
        if valor > 0:
            self._cola.put((valor, clase, time.time()))

    def estado(self):
        ahora = time.time()
        s3 = self.s3 or {}
        servos = []
        with self._lock:
            for i, p in enumerate(self.por_servo):
                servos.append({
                    "n": i + 1, "vaso": dp.NOMBRE_VASO[i + 1],
                    "enviadas": p["enviadas"],
                    "recibidas": _idx(s3.get("rec"), i),
                    "angulo": _idx(s3.get("ang"), i), "reposo": _idx(s3.get("rep"), i),
                    "desvio": _idx(s3.get("des"), i), "retardo_ms": _idx(s3.get("ret"), i),
                    "activo": p["activo_desde"] <= ahora < p["activo_hasta"],
                    "en_espera": ahora < p["activo_desde"],
                    "ultima_hace_s": round(ahora - p["ultima"], 1) if p["ultima"] else None,
                    "ultima_clase": p["ultima_clase"],
                })
        return {"conectada": self.conectada, "host": self.host,
                "enviadas": self.enviadas, "fallidas": self.fallidas,
                "banda_vel": s3.get("vel"), "t_desvio_ms": s3.get("ms"), "cola": s3.get("cola"),
                "servos": servos}

    # --- ordenes (las usa JARVIS y la interfaz) ------------------------
    def banda(self, vel):
        vel = max(0, min(100, int(vel)))
        actual = (self.s3 or {}).get("vel")
        if vel == 0 and actual:
            self.vel_anterior = actual
        ok = self._orden("/banda", {"v": vel})
        if ok:
            bitacora.registrar("banda", "Banda detenida" if vel == 0 else f"Banda al {vel} %")
        return ok

    def reanudar_banda(self):
        return self.banda(self.vel_anterior or 50)

    def probar(self, n):
        """Mueve un servo a desvio y lo regresa (n = 1..4). Tarda lo del desvio."""
        if not 1 <= n <= N_SERVOS:
            return False
        t_desvio = ((self.s3 or {}).get("ms") or 1500) / 1000
        ahora = time.time()
        with self._lock:
            p = self.por_servo[n - 1]
            p["activo_desde"], p["activo_hasta"] = ahora, ahora + t_desvio
        threading.Thread(target=self._orden, args=("/probar", {"s": n - 1}, t_desvio + 3), daemon=True).start()
        bitacora.registrar("servo", f"Prueba del servo {n} ({dp.NOMBRE_VASO[n]})")
        return self.conectada

    def reposo(self):
        ok = self._orden("/reposo_todos", {})
        if ok:
            bitacora.registrar("servo", "Servos llevados a reposo")
        return ok

    # ------------------------------------------------------------------
    def _orden(self, ruta, params, timeout=TIMEOUT_S):
        url = self.url
        if not url:
            return False
        try:
            r = self._ses.get(url + ruta, params=params, timeout=timeout)
            if r.ok:
                try:
                    d = r.json()
                    if "ang" in d:
                        self.s3 = d
                except ValueError:
                    pass
            return r.ok
        except requests.RequestException:
            return False

    def _resolver(self):
        """banda-s3.local -> IP (Windows resuelve los nombres .local)."""
        nombre, _, puerto = self.host.partition(":")
        try:
            return f"http://{socket.gethostbyname(nombre)}" + (f":{puerto}" if puerto else "")
        except OSError:
            return None

    def _vigilar(self):
        """Lee /estado de la S3 cada 2 s (indicador, angulos, banda, retardos)."""
        avisado = None
        while True:
            if self.url is None:
                self.url = self._resolver()
            ok = False
            if self.url:
                try:
                    r = self._ses.get(self.url + "/estado", timeout=TIMEOUT_S)
                    ok = r.ok
                    if ok:
                        try:
                            self.s3 = r.json()
                        except ValueError:
                            pass
                except requests.RequestException:
                    ok = False
            if not ok:
                self.url = None          # la IP pudo cambiar: se vuelve a buscar
            self.conectada = ok
            if ok != avisado:
                print(f"[S3] {'conectada en ' + self.url if ok else 'SIN conexion con ' + self.host}"
                      + ("" if ok else "  (revisa que este en el mismo WiFi o pon su IP en config.S3_HOST)"))
                if avisado is not None or ok:
                    bitacora.registrar("conexion", "ESP32-S3 de la banda y los servos conectada" if ok
                                       else "Se perdió la conexión con la ESP32-S3 de los servos",
                                       voz="Servos en línea" if ok else "Atención: perdí la conexión con los servos")
                avisado = ok
            time.sleep(2)

    def _enviar_pendientes(self):
        while True:
            valor, clase, t0 = self._cola.get()
            enviado = False
            for _intento in range(2):
                ya_ms = int((time.time() - t0) * 1000)
                if ya_ms > VIGENCIA_S * 1000:
                    break
                url = self.url or self._resolver()
                if not url:
                    time.sleep(0.2)
                    continue
                try:
                    r = self._ses.get(url + "/moneda", params={"v": valor, "d": ya_ms}, timeout=TIMEOUT_S)
                    if r.ok:
                        d = r.json()
                        n, en_ms = int(d.get("servo", 0)), int(d.get("en_ms", 0))
                        print(f"[S3] {config.CLASES[clase][0]} -> servo {n} en {en_ms} ms")
                        self._marcar(n, clase, en_ms)
                        bitacora.registrar("servo", f"{config.CLASES[clase][0]} -> servo {n} "
                                           f"({dp.NOMBRE_VASO.get(n, '?')}) en {en_ms / 1000:.1f} s",
                                           servo=n, clase=clase)
                        enviado = True
                        break
                except (requests.RequestException, ValueError):
                    pass
            if enviado:
                self.enviadas += 1
            else:
                self.fallidas += 1
                print(f"[S3] [!] No se pudo avisar {config.CLASES[clase][0]}: la moneda no se desviara")
                bitacora.registrar("servo", f"No se pudo avisar {config.CLASES[clase][0]} a la S3: no se desviara",
                                   voz="Atención: una moneda no se pudo desviar")

    def _marcar(self, n, clase, en_ms):
        """Guarda cuando se movera la paleta (para mostrarla activa en la interfaz)."""
        if not 1 <= n <= N_SERVOS:
            return
        t_desvio = ((self.s3 or {}).get("ms") or 1500) / 1000
        ahora = time.time()
        with self._lock:
            p = self.por_servo[n - 1]
            p["enviadas"] += 1
            p["ultima"] = ahora
            p["ultima_clase"] = clase
            inicio = ahora + en_ms / 1000
            if inicio < p["activo_hasta"]:               # ya estaba desviada: se alarga
                p["activo_hasta"] = inicio + t_desvio
            else:
                p["activo_desde"], p["activo_hasta"] = inicio, inicio + t_desvio


def _idx(lista, i):
    try:
        return lista[i]
    except (TypeError, IndexError):
        return None
