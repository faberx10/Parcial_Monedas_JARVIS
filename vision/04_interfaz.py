"""
04_interfaz.py
==============
Interfaz en tiempo real con el DETECTOR: reconoce y cuenta VARIAS monedas
a la vez (cada una se cuenta una sola vez aunque siga en la imagen), avisa
cada moneda contada a la ESP32-S3 (que mueve el servo de su vaso), maneja
el carrito de transporte y tiene a JARVIS, el asistente de IA del proyecto,
en una pantalla estilo HUD (static/jarvis.html).

  ESP32-CAM --(MJPEG WiFi)--> este programa --(YOLO deteccion)--> seguimiento
                                   |                                + conteo
                                   +--> http://localhost:8000  (interfaz web)
                                   +--> ESP32-S3 /moneda?v=...  (servo del vaso)
                                   +--> carrito  /cmd?d=F&s=50  (control desde la pagina)
                                   +--> JARVIS (Gemini) con el estado en vivo y la documentacion

Uso:
    python 04_interfaz.py            # ESP32-CAM + modelos/monedas_det.pt
    python 04_interfaz.py --demo     # sin camara ni modelo: monedas simuladas
    python 04_interfaz.py --sin-servos   # no avisa a la ESP32-S3
    python 04_interfaz.py --sin-carrito  # sin control del carrito

Paginas:  http://localhost:8000          interfaz con JARVIS (HUD)
          http://localhost:8000/clasico  interfaz anterior
"""

import argparse
import asyncio
import base64
import json
import random
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import bitacora
import config
import datos_proyecto as dp
from camara import CamaraESP32, aplicar_ajustes
from contador_multi import ContadorMulti
from servos_s3 import ServosS3
from carrito import Carrito
from jarvis import Jarvis

DIR_STATIC = config.RAIZ / "static"
MAX_HISTORIAL = 16


# ======================================================================
# Fuentes: real (ESP32 + detector) y demo
# ======================================================================
class FuenteReal:
    def __init__(self):
        from ultralytics import YOLO
        if not config.RUTA_MODELO_DET.exists():
            raise SystemExit(f"[X] No existe {config.RUTA_MODELO_DET}. Entrena primero "
                             "(02_preparar_deteccion.py y 03_entrenar_deteccion.py) o usa --demo.")
        self.modelo = YOLO(str(config.RUTA_MODELO_DET))
        self.nombres = self.modelo.names
        faltan = set(config.CLASES_MONEDA) - set(self.nombres.values())
        if faltan:
            print(f"[!] El modelo no conoce: {faltan}. Reentrena con fotos de esas monedas.")
        aplicar_ajustes()
        self.cam = CamaraESP32().start()
        self._ultimo = -1

    @property
    def conectada(self):
        return self.cam.conectada

    @property
    def fps(self):
        return self.cam.fps

    def siguiente(self):
        """(frame, [(caja, clase, conf), ...]) o (None, None) si no hay frame nuevo."""
        if self.cam.n_frames == self._ultimo:
            return None, None
        self._ultimo = self.cam.n_frames
        frame, _ = self.cam.leer()
        if frame is None:
            return None, None
        r = self.modelo.predict(frame, imgsz=config.IMGSZ_DET, conf=config.UMBRAL_DET,
                                iou=0.5, verbose=False)[0]
        dets = []
        for (x0, y0, x1, y1), c, p in zip(r.boxes.xyxy.cpu().numpy(),
                                           r.boxes.cls.cpu().numpy(),
                                           r.boxes.conf.cpu().numpy()):
            dets.append(((int(x0), int(y0), int(x1), int(y1)), self.nombres[int(c)], float(p)))
        return frame, dets


class FuenteDemo:
    """Monedas simuladas que cruzan la imagen como en la banda."""
    COLOR = {"1000": (190, 195, 200), "500": (70, 170, 210), "200": (75, 165, 205),
             "100": (65, 150, 200), "50": (175, 175, 180)}

    def __init__(self):
        self.conectada, self.fps = True, 12.0
        self.monedas = []          # [x, y, clase, diametro]
        self.t_sig = 0
        rng = np.random.default_rng(3)
        self.fondo = np.full((600, 800, 3), (34, 33, 32), np.uint8) + rng.integers(0, 10, (600, 800, 1), dtype=np.uint8)

    def siguiente(self):
        time.sleep(1 / self.fps)
        if time.time() > self.t_sig:
            for _ in range(random.choice([1, 1, 2, 3])):
                clase = random.choice(config.CLASES_MONEDA)
                d = {"1000": 190, "500": 175, "200": 170, "100": 155, "50": 140}[clase.split("_")[0]]
                self.monedas.append([-d / 2 - random.uniform(0, 260), random.uniform(130, 470), clase, d])
            self.t_sig = time.time() + random.uniform(2.0, 4.0)
        frame = self.fondo.copy()
        dets = []
        for m in self.monedas:
            m[0] += 14
            x, y, clase, d = m
            col = self.COLOR[clase.split("_")[0]]
            cv2.circle(frame, (int(x), int(y)), int(d / 2), col, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(x), int(y)), int(d / 2), (30, 30, 30), 2, cv2.LINE_AA)
            txt = clase.split("_")[0]
            cv2.putText(frame, txt, (int(x) - 22 * len(txt) // 2, int(y) + 10),
                        cv2.FONT_HERSHEY_DUPLEX, 0.9, (40, 40, 40), 2, cv2.LINE_AA)
            if -d / 4 < x < 800 + d / 4 and random.random() > 0.1:
                caja = (int(max(0, x - d / 2)), int(max(0, y - d / 2)),
                        int(min(800, x + d / 2)), int(min(600, y + d / 2)))
                dets.append((caja, clase, random.uniform(0.8, 0.98)))
        self.monedas = [m for m in self.monedas if m[0] < 800 + m[3]]
        return frame, dets


# ======================================================================
# Motor
# ======================================================================
class Motor:
    def __init__(self, fuente, guardar_capturas=True, servos=None, carrito=None):
        self.fuente = fuente
        self.servos = servos            # ServosS3 o None
        self.carrito = carrito          # Carrito o None
        self.guardar_capturas = guardar_capturas
        self.contador = ContadorMulti()
        self.lock = threading.Lock()
        self.jpeg = None
        self.historial = []
        self.n_evento = 0
        self.fps_inferencia = 0.0
        self.inicio = time.time()

    def start(self):
        threading.Thread(target=self._bucle, daemon=True).start()
        threading.Thread(target=self._vigilar_camara, daemon=True).start()
        bitacora.registrar("sistema", "Sistema iniciado")
        return self

    def reset(self):
        with self.lock:
            antes = self.contador.total_monedas
            self.contador.reiniciar()
            self.historial.clear()
        bitacora.registrar("sistema", f"Conteo reiniciado (se llevaban {antes} monedas)")

    def _vigilar_camara(self):
        anterior = None
        while True:
            ok = bool(self.fuente.conectada)
            if ok != anterior:
                if anterior is not None or ok:
                    bitacora.registrar("conexion", "ESP32-CAM conectada" if ok else "Se perdió la señal de la ESP32-CAM",
                                       voz="Cámara en línea" if ok else "Atención: perdí la señal de la cámara")
                anterior = ok
            time.sleep(1)

    def _bucle(self):
        n, t0 = 0, time.time()
        while True:
            frame, dets = self.fuente.siguiente()
            if frame is None:
                time.sleep(0.005)
                continue
            with self.lock:
                for m in self.contador.actualizar(dets, (frame.shape[1], frame.shape[0])):
                    self._registrar(frame, m)
                self.jpeg = self._anotar(frame)
            n += 1
            if time.time() - t0 >= 1:
                self.fps_inferencia = n / (time.time() - t0)
                n, t0 = 0, time.time()

    def _registrar(self, frame, m):
        if self.servos is not None:     # primero: que el aviso salga lo antes posible
            self.servos.enviar(m.clase)
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = m.caja
        pad = int(0.1 * max(x1 - x0, y1 - y0))
        recorte = frame[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
        if recorte.size == 0:
            recorte = frame
        ahora = datetime.now()
        if self.guardar_capturas:
            destino = config.DIR_CAPTURAS / m.clase
            destino.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(destino / (ahora.strftime("%Y%m%d_%H%M%S_%f") + ".jpg")), recorte)
        mini = cv2.resize(recorte, (112, 112), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", mini, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.n_evento += 1
        self.historial.insert(0, {
            "id": self.n_evento, "moneda": m.id, "clase": m.clase,
            "etiqueta": config.CLASES[m.clase][0], "valor": config.CLASES[m.clase][1],
            "confianza": m.conf, "hora": ahora.strftime("%H:%M:%S"),
            "miniatura": "data:image/jpeg;base64," + base64.b64encode(buf).decode(),
        })
        del self.historial[MAX_HISTORIAL:]
        valor = config.CLASES[m.clase][1]
        n_servo = dp.servo_de_clase(m.clase)
        bitacora.registrar("moneda", f"{config.CLASES[m.clase][0]} contada (#{m.id}, {m.conf * 100:.0f} %)"
                           + (f" -> servo {n_servo}" if self.servos is not None and n_servo else ""),
                           voz=f"{valor} pesos", clase=m.clase, valor=valor)

    def _anotar(self, frame):
        vista = frame.copy()
        for m in self.contador.visibles():
            x0, y0, x1, y1 = m.caja
            color = (120, 205, 95) if m.contada else (70, 190, 235)
            cv2.rectangle(vista, (x0, y0), (x1, y1), color, 2, cv2.LINE_AA)
            if not m.contada:      # barra de confirmacion
                p = self.contador.progreso(m)
                cv2.rectangle(vista, (x0, y1 + 3), (int(x0 + (x1 - x0) * p), y1 + 7), color, -1)
            texto = f"{config.CLASES[m.clase][0]} {m.conf * 100:.0f}%"
            (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            yt = max(th + 6, y0)
            cv2.rectangle(vista, (x0, yt - th - 8), (x0 + tw + 8, yt), color, -1)
            cv2.putText(vista, texto, (x0 + 4, yt - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (20, 20, 20), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", vista, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None

    def estado(self):
        with self.lock:
            vis = sorted(self.contador.visibles(), key=lambda m: m.caja[0])
            en_vista = [{
                "id": m.id, "clase": m.clase, "etiqueta": config.CLASES[m.clase][0],
                "valor": config.CLASES[m.clase][1], "confianza": m.conf,
                "contada": m.contada, "progreso": self.contador.progreso(m),
            } for m in vis]
            return {
                "conectada": self.fuente.conectada,
                "fps_camara": round(self.fuente.fps, 1),
                "fps_inferencia": round(self.fps_inferencia, 1),
                "umbral": config.UMBRAL_DET,
                "en_vista": en_vista,
                "valor_en_vista": sum(m["valor"] for m in en_vista),
                "conteo": self.contador.conteo,
                "total_monedas": self.contador.total_monedas,
                "total_pesos": self.contador.total_pesos,
                "ultimo_evento": self.n_evento,
                "s3": self.servos.estado() if self.servos is not None else None,
                "carrito": self.carrito.estado() if self.carrito is not None else None,
                "peso_total_g": round(dp.peso_total(self.contador.conteo), 2),
                "activo_s": int(time.time() - self.inicio),
            }


# ======================================================================
# Aplicacion web
# ======================================================================
def crear_app(motor, jarvis=None):
    app = FastAPI()

    @app.get("/")
    def inicio():
        return FileResponse(DIR_STATIC / "jarvis.html")

    @app.get("/clasico")
    def clasico():
        return FileResponse(DIR_STATIC / "index_det.html")

    @app.get("/masas")
    def masas():
        return dp.MASA_G

    # --- JARVIS ----------------------------------------------------------
    @app.get("/jarvis/info")
    def jarvis_info():
        return jarvis.info() if jarvis else {"clave": False, "modelo": None}

    @app.post("/jarvis/clave")
    async def jarvis_clave(req: Request):
        # solo desde el propio PC: la clave no se configura desde otro equipo de la red
        if req.client is None or req.client.host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse({"ok": False, "msg": "La clave solo se configura desde el PC de la interfaz."}, 403)
        datos = await req.json()
        ok, msg = jarvis.guardar_clave(datos.get("clave", ""))
        return {"ok": ok, "msg": msg}

    @app.post("/jarvis/preguntar")
    async def jarvis_preguntar(req: Request):
        datos = await req.json()
        texto = str(datos.get("texto", ""))

        def eventos():
            try:
                for ev in jarvis.preguntar(texto):
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
            except Exception as e:          # nunca dejar la pagina esperando
                print(f"[JARVIS] error: {e}")
                yield json.dumps({"tipo": "error", "msg": str(e)}, ensure_ascii=False) + "\n"
        return StreamingResponse(eventos(), media_type="application/x-ndjson")

    @app.post("/jarvis/olvidar")
    def jarvis_olvidar():
        jarvis.olvidar()
        return {"ok": True}

    @app.post("/accion")
    def accion(nombre: str, arg: str = ""):
        """Botones de la interfaz (banda, probar servo...): las mismas ordenes seguras de JARVIS."""
        ok, msg, _ui = jarvis.ejecutar(nombre, arg)
        return {"ok": ok, "msg": msg}

    @app.get("/clases")
    def clases():
        return {c: {"etiqueta": config.CLASES[c][0], "valor": config.CLASES[c][1]}
                for c in config.CLASES_MONEDA}

    @app.post("/reset")
    def reset():
        motor.reset()
        return {"ok": True}

    # --- carrito: la pagina repite esta orden cada 100 ms mientras se mantiene el boton ---
    @app.post("/carrito/cmd")
    def carrito_cmd(d: str = "S", s: int = 50):
        if motor.carrito is None:
            return {"ok": False, "motivo": "carrito desactivado"}
        motor.carrito.mover(d, s)
        return {"ok": True, **motor.carrito.estado()}

    @app.post("/carrito/parar")
    def carrito_parar():
        if motor.carrito is not None:
            motor.carrito.parar()
        return {"ok": True}

    @app.get("/video")
    def video():
        async def generar():
            anterior = None
            while True:
                jpg = motor.jpeg
                if jpg is not None and jpg is not anterior:
                    anterior = jpg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(0.03)
        return StreamingResponse(generar(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        enviados, inicial = 0, True      # al abrir la pagina manda el historial reciente
        ult_bit = max(0, bitacora.ultimo_id() - 40)
        try:
            while True:
                estado = motor.estado()
                estado["inicial"] = inicial
                inicial = False
                nuevos_bit = bitacora.desde(ult_bit)
                if nuevos_bit:
                    estado["bitacora"] = nuevos_bit
                    ult_bit = nuevos_bit[-1]["id"]
                if estado["ultimo_evento"] != enviados:
                    with motor.lock:
                        nuevos = [e for e in motor.historial if e["id"] > enviados]
                    estado["eventos"] = list(reversed(nuevos))
                    enviados = estado["ultimo_evento"]
                await sock.send_json(estado)
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sin ESP32 ni modelo")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--sin-servos", action="store_true", help="no avisar a la ESP32-S3")
    ap.add_argument("--servos-demo", action="store_true",
                    help="con --demo, mandar tambien las monedas simuladas a la S3")
    ap.add_argument("--sin-carrito", action="store_true", help="sin control del carrito")
    ap.add_argument("--carrito-demo", action="store_true",
                    help="con --demo, activar tambien el control del carrito")
    args = ap.parse_args()
    fuente = FuenteDemo() if args.demo else FuenteReal()
    usar_s3 = config.S3_ACTIVO and not args.sin_servos and (not args.demo or args.servos_demo)
    servos = ServosS3(config.S3_HOST) if usar_s3 else None
    if servos:
        print(f"  Avisando cada moneda a la ESP32-S3 en {config.S3_HOST}")
    usar_car = config.CARRITO_ACTIVO and not args.sin_carrito and (not args.demo or args.carrito_demo)
    carrito = Carrito(config.CARRITO_HOST) if usar_car else None
    if carrito:
        print(f"  Carrito de transporte en {config.CARRITO_HOST}")
    motor = Motor(fuente, guardar_capturas=not args.demo, servos=servos, carrito=carrito).start()
    jarvis = Jarvis(motor)
    print(f"\n  Interfaz lista en  http://localhost:{args.puerto}   (anterior: /clasico)\n")
    uvicorn.run(crear_app(motor, jarvis), host="0.0.0.0", port=args.puerto, log_level="warning")
