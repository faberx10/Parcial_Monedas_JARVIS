"""
02_preparar_deteccion.py
========================
Arma el dataset YOLO para el DETECTOR a partir de las fotos de
01_capturar_deteccion.py.

  1. Fotos reales  -> se separan 85 % entrenamiento / 15 % validacion
                      (por moneda, siempre igual: semilla fija).
  2. Composiciones -> se recortan las monedas reales y se pegan VARIAS,
                      de distintas denominaciones, sobre fotos de la banda
                      vacia. Asi el modelo aprende a ver monedas mezcladas
                      (y algunas casi tocandose) aunque las fotos se tomaron
                      con una sola denominacion a la vez.
  3. Banda vacia   -> algunas fotos sin monedas, para que no invente monedas.

Resultado: dataset_det/  (images/, labels/, data.yaml)

Uso:
    python 02_preparar_deteccion.py
    python 02_preparar_deteccion.py --sinteticas 2500     # mas composiciones
"""

import argparse
import random
import shutil

import cv2
import numpy as np

import config
import etiquetado as et

DIR_IMG = config.DIR_DET_CRUDO / "imagenes"
DIR_ETQ = config.DIR_DET_CRUDO / "etiquetas"
DIR_FONDO = config.DIR_DET_CRUDO / "fondos"
FRACCION_VAL = 0.15


def leer(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def escribir(p, img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    buf.tofile(str(p))


def linea_yolo(idx, caja, w, h):
    x0, y0, x1, y1 = caja
    return (f"{idx} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
            f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}\n")


# ----------------------------------------------------------------------
# Recortes de monedas (con su silueta exacta) para las composiciones
# ----------------------------------------------------------------------
def etiquetas_limpias(stem, zona, w=800, h=600):
    """Etiquetas de una foto, sin las cajas falsas (reflejos en la pared)."""
    return [e for e in et.leer_etiquetas(DIR_ETQ / f"{stem}.txt")
            if et.caja_valida(e[1:], zona, w, h)]


def recortes(fotos, fondo):
    """Devuelve lista de (clase, parche BGR, alfa 0..1) de monedas completas."""
    out = []
    for p in fotos:
        img = leer(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        mascara = et.mascara_monedas(img, fondo)
        for clase, x0, y0, x1, y1 in etiquetas_limpias(p.stem, fondo["zona"], w, h):
            if x0 <= 1 or y0 <= 1 or x1 >= w - 1 or y1 >= h - 1:
                continue                      # cortada por el borde: no sirve para pegar
            m = 6                             # margen para el borde suave
            xa, ya, xb, yb = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
            alfa = mascara[ya:yb, xa:xb].astype(np.float32) / 255
            # solo la silueta de ESTA moneda (circulo inscrito en su caja)
            circ = np.zeros_like(alfa)
            cv2.ellipse(circ, ((x0 + x1) // 2 - xa, (y0 + y1) // 2 - ya),
                        ((x1 - x0) // 2 + 1, (y1 - y0) // 2 + 1), 0, 0, 360, 1.0, -1)
            alfa = cv2.GaussianBlur(np.minimum(alfa, circ), (0, 0), 1.0)
            out.append((clase, img[ya:yb, xa:xb].copy(), alfa))
    return out


def girar(parche, alfa, ang, esc):
    h, w = parche.shape[:2]
    lado = int(np.ceil(np.hypot(h, w) * esc)) + 2
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, esc)
    M[0, 2] += lado / 2 - w / 2
    M[1, 2] += lado / 2 - h / 2
    p = cv2.warpAffine(parche, M, (lado, lado), flags=cv2.INTER_LINEAR)
    a = cv2.warpAffine(alfa, M, (lado, lado), flags=cv2.INTER_LINEAR)
    return p, a


def caja_alfa(a, x, y, w, h, umbral=0.5):
    ys, xs = np.where(a > umbral)
    if len(xs) == 0:
        return None
    x0, x1 = max(0, x + xs.min()), min(w, x + xs.max() + 1)
    y0, y1 = max(0, y + ys.min()), min(h, y + ys.max() + 1)
    return x0, y0, x1, y1


def composicion(fondos, piezas, rng, zona=None):
    """Pega 2..6 monedas al azar sobre una foto de la banda vacia
    (solo sobre la banda, nunca encima de las paredes del embudo)."""
    lienzo = rng.choice(fondos).astype(np.float32).copy()
    h, w = lienzo.shape[:2]
    zona = np.ones((h, w), bool) if zona is None else zona > 0
    n = rng.randint(2, 6)
    colocadas, etiquetas = [], []
    for _ in range(n):
        clase, parche, alfa = rng.choice(piezas)
        p, a = girar(parche, alfa, rng.uniform(0, 360), rng.uniform(0.93, 1.07))
        ph, pw = p.shape[:2]
        for _intento in range(40):
            x = rng.randint(-pw // 3, w - 2 * pw // 3)
            y = rng.randint(-ph // 3, h - 2 * ph // 3)
            cx, cy, r = x + pw / 2, y + ph / 2, 0.36 * pw
            # separacion: casi siempre libres, a veces casi tocandose
            hueco = rng.choice([25, 25, 25, 8, 0])
            xa_, ya_ = int(max(0, cx - r)), int(max(0, cy - r))
            xb_, yb_ = int(min(w, cx + r)), int(min(h, cy + r))
            sobre_banda = xb_ > xa_ and yb_ > ya_ and zona[ya_:yb_, xa_:xb_].mean() > 0.9
            if sobre_banda and all(np.hypot(cx - ox, cy - oy) > r + orr + hueco
                                   for ox, oy, orr in colocadas):
                break
        else:
            continue
        xa, ya, xb, yb = max(0, x), max(0, y), min(w, x + pw), min(h, y + ph)
        if xb - xa < pw * 0.5 or yb - ya < ph * 0.5:
            continue
        sub_a = a[ya - y:yb - y, xa - x:xb - x, None]
        sub_p = p[ya - y:yb - y, xa - x:xb - x].astype(np.float32)
        brillo = rng.uniform(0.9, 1.1)
        lienzo[ya:yb, xa:xb] = lienzo[ya:yb, xa:xb] * (1 - sub_a) + sub_p * brillo * sub_a
        caja = caja_alfa(a, x, y, w, h)
        if caja is None:
            continue
        colocadas.append((cx, cy, r))
        etiquetas.append((clase, caja))
    img = np.clip(lienzo, 0, 255).astype(np.uint8)
    # misma compresion JPEG que manda la ESP32-CAM
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(70, 92)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR), etiquetas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sinteticas", type=int, default=1800, help="composiciones de entrenamiento")
    ap.add_argument("--semilla", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.semilla)
    clases = config.CLASES_MONEDA
    idx = {c: i for i, c in enumerate(clases)}

    fotos_fondo = sorted(DIR_FONDO.glob("*.jpg"))
    if len(fotos_fondo) < 5:
        raise SystemExit("[X] Faltan fotos de la banda vacia (tecla F en 01_capturar_deteccion.py)")
    fondos = [f for f in (leer(p) for p in fotos_fondo) if f is not None]
    fondo_ref = et.modelo_fondo(fondos)

    # --- fotos reales por clase -----------------------------------------
    por_clase = {c: [] for c in clases}
    for p in sorted(DIR_IMG.glob("*.jpg")):
        t = DIR_ETQ / f"{p.stem}.txt"
        if not t.exists():
            continue
        etq = et.leer_etiquetas(t)
        if etq and etq[0][0] in por_clase:
            por_clase[etq[0][0]].append(p)
    faltan = [config.CLASES[c][0] for c, l in por_clase.items() if len(l) < 10]
    if faltan:
        print(f"[!] Pocas fotos (<10) de: {', '.join(faltan)}. El modelo las reconocera mal.")

    split = {"train": [], "val": []}
    for c, lista in por_clase.items():
        lista = lista[:]
        rng.shuffle(lista)
        n_val = max(1, round(len(lista) * FRACCION_VAL)) if len(lista) >= 4 else 0
        split["val"] += lista[:n_val]
        split["train"] += lista[n_val:]

    if config.DIR_DET.exists():
        shutil.rmtree(config.DIR_DET)
    for s in ("train", "val"):
        (config.DIR_DET / "images" / s).mkdir(parents=True)
        (config.DIR_DET / "labels" / s).mkdir(parents=True)

    def guardar(img, etiquetas, s, nombre):
        h, w = img.shape[:2]
        escribir(config.DIR_DET / "images" / s / f"{nombre}.jpg", img)
        (config.DIR_DET / "labels" / s / f"{nombre}.txt").write_text(
            "".join(linea_yolo(idx[c], caja, w, h) for c, caja in etiquetas))

    # 1) reales
    descartadas = {c: 0 for c in clases}
    for s, lista in split.items():
        for p in lista:
            img = leer(p)
            h, w = img.shape[:2]
            todas = et.leer_etiquetas(DIR_ETQ / f"{p.stem}.txt")
            buenas = etiquetas_limpias(p.stem, fondo_ref["zona"], w, h)
            if todas:
                descartadas[todas[0][0]] += len(todas) - len(buenas)
            etq = [(c, (x0, y0, x1, y1)) for c, x0, y0, x1, y1 in buenas]
            guardar(img, etq, s, f"real_{p.stem}")
    if any(descartadas.values()):
        print("Cajas falsas descartadas (reflejos en la pared):",
              ", ".join(f"{config.CLASES[c][0]}: {n}" for c, n in descartadas.items() if n))
    print(f"Fotos reales: {len(split['train'])} entrenamiento / {len(split['val'])} validacion")

    # 2) composiciones (las de validacion usan SOLO monedas de validacion)
    for s, n in (("train", args.sinteticas), ("val", max(100, args.sinteticas // 8))):
        piezas = recortes(split[s], fondo_ref)
        if len({c for c, _, _ in piezas}) < 2:
            print(f"[!] Muy pocas monedas para composiciones de {s}; se omiten")
            continue
        for i in range(n):
            img, etq = composicion(fondos, piezas, rng, fondo_ref["zona"])
            guardar(img, etq, s, f"mezcla_{i:05d}")
        print(f"Composiciones de varias monedas ({s}): {n}  (a partir de {len(piezas)} monedas recortadas)")

    # 3) banda vacia (sin etiquetas)
    rng.shuffle(fotos_fondo)
    n_val_f = max(1, len(fotos_fondo) // 6)
    for i, p in enumerate(fotos_fondo):
        s = "val" if i < n_val_f else "train"
        guardar(leer(p), [], s, f"vacia_{p.stem}")
    print(f"Banda vacia: {len(fotos_fondo)}")

    yaml = config.DIR_DET / "data.yaml"
    yaml.write_text(
        f"path: {config.DIR_DET.as_posix()}\ntrain: images/train\nval: images/val\n"
        f"nc: {len(clases)}\nnames: [{', '.join(repr(c) for c in clases)}]\n", encoding="utf-8")

    print("\nMonedas reales por clase (fotos / monedas etiquetadas):")
    for c in clases:
        n_m = sum(len(etiquetas_limpias(p.stem, fondo_ref["zona"])) for p in por_clase[c])
        print(f"  {config.CLASES[c][0]:<14} {len(por_clase[c]):>4} / {n_m:>4}")
    print(f"\nListo: {yaml}\nAhora corre:  python 03_entrenar_deteccion.py")


if __name__ == "__main__":
    main()
