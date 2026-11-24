"""
etiquetado.py
=============
Etiquetado AUTOMATICO de monedas para entrenar el detector.

Idea: la camara esta fija sobre la banda (fondo oscuro y parejo). Con unas
fotos de la banda VACIA se arma un "fondo de referencia". En cada foto con
monedas, todo lo que cambia respecto a ese fondo es una moneda -> su caja
sale sola; la clase la eliges tu con la tecla antes de tomar la foto.

Formato de las etiquetas que guarda la captura (un .txt por foto):
    <clase> x0 y0 x1 y1        (pixeles de la imagen original, una linea por moneda)
"""

import cv2
import numpy as np

# Una moneda a la altura de trabajo mide ~100-330 px de diametro en 800x600.
# Si subes o bajas mucho el carro de la camara ajusta estos dos valores.
DIAMETRO_MIN = 80          # px: blobs mas pequenos se ignoran (polvo, reflejos). La de $50 mide ~110 px
DIAMETRO_MAX = 420         # px: mas grande = varias monedas pegadas o sombra
REDONDEZ_MIN = 0.78        # area de la silueta / area del circulo que la encierra
                           # (1 = circulo perfecto; dos monedas pegadas dan ~0.6)
UMBRAL_DIF = 15            # diferencia minima de brillo/color contra el fondo (exposicion ya igualada)


def fondo_referencia(fotos_fondo):
    """Mediana de varias fotos de la banda vacia (quita ruido y reflejos)."""
    pila = np.stack([cv2.GaussianBlur(f, (5, 5), 0) for f in fotos_fondo])
    return np.median(pila, axis=0).astype(np.uint8)


def zona_banda(fondo):
    """Zona donde pueden estar las monedas: la BANDA (lo mas oscuro de la imagen).

    Las paredes del embudo, los LEDs y sus reflejos se ven mas claros y cambian
    de brillo con la exposicion automatica; ahi no hay monedas, asi que se
    ignoran. Devuelve mascara uint8 (255 = banda).
    """
    h, w = fondo.shape[:2]
    gris = cv2.cvtColor(fondo, cv2.COLOR_BGR2GRAY)
    datos = gris.reshape(-1, 1).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, etq, centros = cv2.kmeans(datos, 3, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    centros = centros.ravel()
    orden = np.argsort(centros)
    oscuro = orden[0]
    # si el siguiente grupo es casi igual de oscuro, tambien es banda
    grupos = [oscuro] + ([orden[1]] if centros[orden[1]] - centros[oscuro] < 18 else [])
    if centros[orden[2]] - centros[oscuro] < 30:
        return np.full((h, w), 255, np.uint8)          # imagen pareja: todo es banda
    m = np.isin(etq.reshape(h, w), grupos).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m)
    zona = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 0.03 * h * w:
            zona[cc == i] = 255
    zona = cv2.morphologyEx(zona, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    # rellena huecos (una moneda olvidada en el fondo no debe abrir un hueco)
    cont, _ = cv2.findContours(zona, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    zona = np.zeros_like(zona)
    cv2.drawContours(zona, cont, -1, 255, -1)
    # se aleja un poco de las paredes: su borde parpadea con la exposicion
    zona = cv2.erode(zona, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
    return zona if zona.any() else np.full((h, w), 255, np.uint8)


def modelo_fondo(fotos_fondo):
    """Fondo de referencia + zona de la banda, a partir de fotos de la banda vacia."""
    fondo = fondo_referencia(fotos_fondo)
    return {"fondo": fondo, "zona": zona_banda(fondo)}


def _como_modelo(fondo):
    if isinstance(fondo, dict):
        return fondo
    return {"fondo": fondo, "zona": np.full(fondo.shape[:2], 255, np.uint8)}


def igualar_exposicion(a, b, zona):
    """La camara cambia la exposicion sola. Se lleva 'a' al brillo de 'b' con
    una recta (ganancia y desplazamiento por canal) ajustada sobre los
    cuantiles de la banda; las monedas ocupan poca area y casi no la afectan."""
    q = np.linspace(3, 70, 25)        # cuantiles bajos: las monedas (brillantes) no los afectan
    out = np.empty(a.shape, np.float32)
    for ch in range(3):
        qa = np.percentile(a[..., ch][zona], q)
        qb = np.percentile(b[..., ch][zona], q)
        if qa[-1] - qa[0] < 2:                      # banda casi uniforme: solo desplazar
            g, o = 1.0, float(np.median(qb - qa))
        else:
            g, o = np.polyfit(qa, qb, 1)
            g = float(np.clip(g, 0.4, 2.5))
        out[..., ch] = a[..., ch] * g + o
    return np.clip(out, 0, 255)


def mascara_monedas(frame, fondo):
    """Pixeles que cambiaron respecto al fondo (monedas), solo sobre la banda."""
    mod = _como_modelo(fondo)
    zona = mod["zona"] > 0
    a = cv2.GaussianBlur(frame, (5, 5), 0)
    b = mod["fondo"]
    a = igualar_exposicion(a, b, zona).astype(np.int16)
    dif = np.abs(a - b.astype(np.int16)).max(axis=2).astype(np.uint8)
    dif[~zona] = 0
    # donde el fondo es mas claro (reflejos cerca de las paredes) el error de
    # exposicion es mayor: se exige mas diferencia ahi
    umbral = UMBRAL_DIF + 0.35 * b.max(axis=2).astype(np.float32)
    m = np.where(dif > umbral, 255, 0).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    # une las partes de una misma moneda (el relieve oscuro la "rompe")
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)), iterations=2)
    # rellena huecos internos (centro oscuro de algunas monedas)
    cont, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    relleno = np.zeros_like(m)
    cv2.drawContours(relleno, cont, -1, 255, -1)
    return relleno


def detectar(frame, fondo):
    """Devuelve (cajas_ok, problemas).

    cajas_ok:  lista de (x0, y0, x1, y1) de monedas bien separadas.
    problemas: lista de (x0, y0, x1, y1, motivo) que impiden guardar la foto
               (monedas pegadas, sombra, mano en la imagen...).
    """
    h, w = frame.shape[:2]
    mod = _como_modelo(fondo)
    m = mascara_monedas(frame, mod)
    # borde de la banda (paredes del embudo): una moneda ahi se ve "cortada"
    borde_zona = cv2.dilate(255 - mod["zona"], np.ones((9, 9), np.uint8)) > 0
    cont, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cajas, problemas = [], []
    for c in cont:
        casco = cv2.convexHull(c)
        area = cv2.contourArea(casco)
        (_, _), r = cv2.minEnclosingCircle(casco)
        diam = 2 * r
        if diam < DIAMETRO_MIN:
            continue
        x, y, bw, bh = cv2.boundingRect(casco)
        caja = (x, y, x + bw, y + bh)
        silueta = np.zeros((h, w), np.uint8)
        cv2.drawContours(silueta, [c], -1, 255, 3)
        toca_borde = (x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1 or
                      bool((borde_zona & (silueta > 0)).any()))
        if diam > DIAMETRO_MAX:
            problemas.append((*caja, "muy grande"))
            continue
        redondez = area / (np.pi * r * r) if r > 0 else 0
        if not toca_borde and redondez < REDONDEZ_MIN:
            problemas.append((*caja, "pegadas/forma rara"))
            continue
        if toca_borde:
            # moneda cortada por el borde: sirve, pero solo si se ve al menos la mitad
            if min(bw, bh) < 0.5 * max(bw, bh):
                continue
        if not caja_valida(caja, mod["zona"], w, h):
            continue                          # reflejo en la pared del embudo, no es moneda
        cajas.append(caja)
    cajas.sort(key=lambda b: (b[0], b[1]))
    return cajas, problemas


def caja_valida(caja, zona, w, h):
    """Descarta cajas que no pueden ser una moneda: sobre la pared del embudo
    (poca parte dentro de la banda) o muy angostas/alargadas."""
    x0, y0, x1, y1 = caja
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return False
    en_borde_imagen = x0 <= 1 or y0 <= 1 or x1 >= w - 1 or y1 >= h - 1
    aspecto = bw / bh
    if not en_borde_imagen and not (0.75 <= aspecto <= 1.33):
        return False
    if zona is not None and (zona[y0:y1, x0:x1] > 0).mean() < 0.8:
        return False
    return True


def leer_etiquetas(ruta_txt):
    """Lee el .txt de la captura -> lista de (clase, x0, y0, x1, y1)."""
    out = []
    for linea in ruta_txt.read_text(encoding="utf-8").splitlines():
        p = linea.split()
        if len(p) == 5:
            out.append((p[0], *map(int, p[1:])))
    return out


def escribir_etiquetas(ruta_txt, clase, cajas):
    ruta_txt.write_text("".join(f"{clase} {x0} {y0} {x1} {y1}\n"
                                for x0, y0, x1, y1 in cajas), encoding="utf-8")
