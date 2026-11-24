"""
01_capturar_deteccion.py
========================
Toma las fotos para entrenar el DETECTOR (varias monedas a la vez) desde la
ESP32-CAM ya montada en la caja. Las cajas de cada moneda salen SOLAS.

PASO A: banda vacia (fondo de referencia)
    F        rafaga de 30 fotos de la banda VACIA (hazlo primero). Cada vez que
             presionas F se BORRA el fondo anterior y se toma de nuevo: hazlo
             otra vez si mueves la caja, el carro o cambias las luces.
             La linea gris muestra la zona de la banda donde se buscan monedas.

PASO B: monedas (siempre de UNA sola denominacion por foto)
    1..9     elegir la moneda que vas a poner:
             1=$1000 nueva  2=$500 nueva  3=$500 antigua  4=$200 nueva
             5=$200 antigua 6=$100 nueva  7=$100 antigua  8=$50 nueva
             9=$50 antigua
    ESPACIO  tomar UNA foto
    R        rafaga ON/OFF (una foto cada vez que las monedas se mueven)
    Z        borrar la ultima foto
    Q / ESC  salir

En pantalla:  caja VERDE = moneda detectada (se guardara)
              caja ROJA  = problema (monedas pegadas, mano...) -> no guarda
Puedes poner 1, 2 o 3 monedas IGUALES a la vez, separadas entre si.

Uso:
    python 01_capturar_deteccion.py
"""

import time
from datetime import datetime

import cv2
import numpy as np

import config
import etiquetado as et
from camara import CamaraESP32, aplicar_ajustes

META_FOTOS = 60                  # fotos por moneda (ambas caras, varias posiciones)
FOTOS_FONDO = 30
INTERVALO_RAFAGA = 0.35
DIR_IMG = config.DIR_DET_CRUDO / "imagenes"
DIR_ETQ = config.DIR_DET_CRUDO / "etiquetas"
DIR_FONDO = config.DIR_DET_CRUDO / "fondos"
VERDE, ROJO, AMARILLO, GRIS = (90, 210, 90), (60, 60, 235), (40, 200, 240), (170, 170, 170)


def leer(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def escribir(p, img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    buf.tofile(str(p))


def contar():
    cuenta = {c: 0 for c in config.CLASES_MONEDA}
    monedas = {c: 0 for c in config.CLASES_MONEDA}
    for t in DIR_ETQ.glob("*.txt"):
        etq = et.leer_etiquetas(t)
        if etq:
            cuenta[etq[0][0]] = cuenta.get(etq[0][0], 0) + 1
            monedas[etq[0][0]] = monedas.get(etq[0][0], 0) + len(etq)
    return cuenta, monedas


def cargar_fondo():
    """Modelo del fondo con las fotos MAS RECIENTES de la banda vacia."""
    rutas = sorted(DIR_FONDO.glob("*.jpg"))[-FOTOS_FONDO:]
    fotos = [f for f in (leer(p) for p in rutas) if f is not None]
    return (et.modelo_fondo(fotos), len(fotos)) if len(fotos) >= 5 else (None, len(fotos))


def panel(vista, activa, cuenta, monedas, rafaga, n_fondo, msg):
    h, w = vista.shape[:2]
    lienzo = np.full((h, w + 300, 3), 24, np.uint8)
    lienzo[:, :w] = vista
    x = w + 14
    f = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(lienzo, "CAPTURA DETECTOR", (x, 28), f, 0.62, (230, 230, 230), 2)
    color_f = VERDE if n_fondo >= FOTOS_FONDO else AMARILLO
    cv2.putText(lienzo, f"[F] fondo: {n_fondo}/{FOTOS_FONDO}", (x, 58), f, 0.5, color_f, 1)
    y = 92
    for c in config.CLASES_MONEDA:
        etiqueta, _, tecla = config.CLASES[c]
        sel = c == activa
        n = cuenta.get(c, 0)
        color = VERDE if n >= META_FOTOS else (AMARILLO if sel else GRIS)
        txt = f"{'>' if sel else ' '}[{tecla}] {etiqueta:<13} {n:>3} ({monedas.get(c, 0)})"
        cv2.putText(lienzo, txt, (x, y), f, 0.47, color, 2 if sel else 1)
        y += 26
    y += 8
    cv2.putText(lienzo, f"Meta: {META_FOTOS} fotos c/u", (x, y), f, 0.45, GRIS, 1)
    cv2.putText(lienzo, "(n) = monedas etiquetadas", (x, y + 20), f, 0.45, GRIS, 1)
    cv2.putText(lienzo, "RAFAGA ON" if rafaga else "rafaga off", (x, y + 56), f, 0.6,
                ROJO if rafaga else GRIS, 2 if rafaga else 1)
    cv2.putText(lienzo, "ESPACIO foto  R rafaga", (x, h - 46), f, 0.45, GRIS, 1)
    cv2.putText(lienzo, "Z deshacer   Q salir", (x, h - 24), f, 0.45, GRIS, 1)
    if msg:
        cv2.rectangle(lienzo, (0, h - 34), (w, h), (0, 0, 0), -1)
        cv2.putText(lienzo, msg, (10, h - 11), f, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
    return lienzo


def main():
    for d in (DIR_IMG, DIR_ETQ, DIR_FONDO):
        d.mkdir(parents=True, exist_ok=True)
    print("Aplicando ajustes a la camara...")
    aplicar_ajustes()
    cam = CamaraESP32().start()
    teclas = {ord(config.CLASES[c][2]): c for c in config.CLASES_MONEDA}
    activa = config.CLASES_MONEDA[0]
    cuenta, monedas = contar()
    fondo, n_fondo = cargar_fondo()
    rafaga, fondo_pend = False, 0
    t_ult, cajas_ult = 0.0, []
    historial = []                     # para deshacer
    msg, t_msg = "", 0.0
    print(__doc__)

    def avisar(texto):
        nonlocal msg, t_msg
        msg, t_msg = texto, time.time()
        print(texto)

    def guardar_monedas(frame, cajas):
        nombre = f"{activa}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        escribir(DIR_IMG / f"{nombre}.jpg", frame)
        et.escribir_etiquetas(DIR_ETQ / f"{nombre}.txt", activa, cajas)
        historial.append(nombre)
        cuenta[activa] += 1
        monedas[activa] += len(cajas)

    if fondo is None:
        avisar("Primero: deja la banda VACIA y presiona F (fondo de referencia)")

    while True:
        frame, _ = cam.leer()
        if frame is None:
            vacio = np.zeros((600, 800, 3), np.uint8)
            cv2.putText(vacio, "Esperando video de la ESP32-CAM...", (150, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            cv2.imshow("Captura detector", vacio)
            if cv2.waitKey(200) & 0xFF in (ord("q"), 27):
                break
            continue

        ahora = time.time()
        vista = frame.copy()

        # --- rafaga de fondo -------------------------------------------
        if fondo_pend > 0 and ahora - t_ult >= 0.25:
            escribir(DIR_FONDO / f"fondo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg", frame)
            fondo_pend -= 1
            t_ult = ahora
            if fondo_pend == 0:
                fondo, n_fondo = cargar_fondo()
                avisar(f"Fondo listo ({n_fondo} fotos). Ahora elige la moneda (1-9) y pon monedas.")

        # --- deteccion automatica --------------------------------------
        cajas, problemas = ([], []) if fondo is None or fondo_pend else et.detectar(frame, fondo)
        if fondo is not None and not fondo_pend:      # zona de la banda
            cont, _ = cv2.findContours(fondo["zona"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(vista, cont, -1, GRIS, 1)
        for x0, y0, x1, y1 in cajas:
            cv2.rectangle(vista, (x0, y0), (x1, y1), VERDE, 2)
        for x0, y0, x1, y1, motivo in problemas:
            cv2.rectangle(vista, (x0, y0), (x1, y1), ROJO, 2)
            cv2.putText(vista, motivo, (x0, max(15, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ROJO, 1)
        valido = bool(cajas) and not problemas

        if rafaga and valido and ahora - t_ult >= INTERVALO_RAFAGA:
            # solo guarda si las monedas se movieron (evita fotos repetidas)
            movida = len(cajas) != len(cajas_ult) or any(
                abs(a[0] - b[0]) + abs(a[1] - b[1]) > 12 for a, b in zip(cajas, cajas_ult))
            if movida:
                guardar_monedas(frame, cajas)
                cajas_ult, t_ult = cajas, ahora

        if ahora - t_msg > 4:
            msg = ""
        cv2.imshow("Captura detector",
                   panel(vista, activa, cuenta, monedas, rafaga, n_fondo if not fondo_pend else
                         FOTOS_FONDO - fondo_pend, msg))

        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        elif k in (ord("f"), ord("F")):
            rafaga = False
            for viejo in DIR_FONDO.glob("*.jpg"):      # fondo nuevo desde cero
                viejo.unlink()
            fondo, n_fondo = None, 0
            fondo_pend = FOTOS_FONDO
            avisar("Tomando fotos de la banda VACIA... no pongas nada ni muevas la caja")
        elif k in teclas:
            activa = teclas[k]
            avisar(f"Moneda activa: {config.CLASES[activa][0]}")
        elif k == ord(" "):
            if fondo is None:
                avisar("Falta el fondo: banda vacia y presiona F")
            elif not valido:
                avisar("No se guardo: " + ("no veo monedas" if not cajas else "hay cajas rojas"))
            else:
                guardar_monedas(frame, cajas)
                avisar(f"Foto guardada: {len(cajas)} x {config.CLASES[activa][0]} "
                       f"(total {cuenta[activa]})")
        elif k in (ord("r"), ord("R")):
            if fondo is None:
                avisar("Falta el fondo: banda vacia y presiona F")
            else:
                rafaga = not rafaga
                cajas_ult = []
                avisar(f"Rafaga {'ON' if rafaga else 'OFF'} - {config.CLASES[activa][0]}")
        elif k in (ord("z"), ord("Z")) and historial:
            nombre = historial.pop()
            clase = nombre.rsplit("_", 3)[0]
            n = len(et.leer_etiquetas(DIR_ETQ / f"{nombre}.txt"))
            (DIR_IMG / f"{nombre}.jpg").unlink(missing_ok=True)
            (DIR_ETQ / f"{nombre}.txt").unlink(missing_ok=True)
            cuenta[clase] -= 1
            monedas[clase] -= n
            avisar("Ultima foto borrada")

    cam.stop()
    cv2.destroyAllWindows()
    print("\nResumen:")
    print(f"  Fondo: {n_fondo} fotos")
    for c in config.CLASES_MONEDA:
        n = cuenta[c]
        estado = "OK" if n >= META_FOTOS else f"faltan {META_FOTOS - n}"
        print(f"  {config.CLASES[c][0]:<14} {n:>4} fotos  {monedas[c]:>4} monedas  {estado}")


if __name__ == "__main__":
    main()
