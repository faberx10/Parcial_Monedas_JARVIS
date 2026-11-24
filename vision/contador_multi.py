"""
contador_multi.py
=================
Seguimiento y conteo de VARIAS monedas a la vez (sin dependencias de
camara ni de modelo, para poder probarlo aparte).

Cada frame llega una lista de detecciones (caja, clase, confianza).
  1. Seguimiento: cada deteccion se une a la moneda que estaba mas cerca en
     el frame anterior (la banda las mueve poco entre frames). Si no hay
     ninguna cerca, es una moneda NUEVA con su propio numero (#id).
  2. Votos: cada moneda acumula votos por clase (suma de confianzas), asi un
     frame dudoso no cambia su denominacion.
  3. Conteo: una moneda se cuenta UNA sola vez, cuando ya se vio en
     FRAMES_CONFIRMAR frames y al menos una vez COMPLETA (sin tocar el borde
     de la imagen). Luego se sigue mostrando como "contada".
  4. Si una moneda deja de verse por un rato (salio de la camara) se olvida.
"""

import math

import config

FRAMES_OLVIDO = 10        # frames sin verla para darla por salida
MARGEN_BORDE = 4          # px: si la caja toca el borde, la moneda esta cortada
PESO_CORTADA = 0.3        # una moneda cortada vota menos (se ve solo una parte)


def _centro(c):
    return (c[0] + c[2]) / 2, (c[1] + c[3]) / 2


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Moneda:
    def __init__(self, ident, caja):
        self.id = ident
        self.caja = caja
        self.votos = {}
        self.frames = 0
        self.sin_ver = 0
        self.contada = False
        self.completa = False      # se vio entera al menos una vez
        self.conf = 0.0

    @property
    def clase(self):
        return max(self.votos, key=self.votos.get) if self.votos else None

    def actualizar(self, caja, clase, conf, entera=True):
        self.caja = caja
        self.completa = self.completa or entera
        self.votos[clase] = self.votos.get(clase, 0.0) + conf * (1.0 if entera else PESO_CORTADA)
        self.frames += 1
        self.sin_ver = 0
        self.conf = conf


class ContadorMulti:
    def __init__(self, frames_confirmar=None):
        self.n_confirmar = frames_confirmar or config.FRAMES_CONFIRMAR
        self.reiniciar()

    def reiniciar(self):
        self.conteo = {c: 0 for c in config.CLASES_MONEDA}
        self.monedas = {}          # id -> Moneda (visibles o recien vistas)
        self._sig_id = 1

    def actualizar(self, detecciones, tam=None):
        """detecciones: lista de (caja(x0,y0,x1,y1), clase, conf).
        tam: (ancho, alto) de la imagen, para saber si una moneda esta cortada.

        Devuelve la lista de Monedas que se CONTARON en este frame.
        """
        def entera(c):
            if tam is None:
                return True
            w, h = tam
            return (c[0] > MARGEN_BORDE and c[1] > MARGEN_BORDE and
                    c[2] < w - MARGEN_BORDE and c[3] < h - MARGEN_BORDE)

        libres = dict(self.monedas)
        pares = []
        for i, (caja, clase, conf) in enumerate(detecciones):
            cx, cy = _centro(caja)
            diam = max(caja[2] - caja[0], caja[3] - caja[1])
            for m in libres.values():
                mx, my = _centro(m.caja)
                d = math.hypot(cx - mx, cy - my)
                if d < 0.8 * diam or _iou(caja, m.caja) > 0.3:
                    pares.append((d, i, m.id))
        pares.sort()
        usadas_det, usadas_mon = set(), set()
        for d, i, mid in pares:                      # emparejamiento voraz, el mas cercano primero
            if i in usadas_det or mid in usadas_mon:
                continue
            usadas_det.add(i)
            usadas_mon.add(mid)
            caja, clase, conf = detecciones[i]
            self.monedas[mid].actualizar(caja, clase, conf, entera(caja))

        for m in list(self.monedas.values()):        # las que no aparecieron en este frame
            if m.id not in usadas_mon:
                m.sin_ver += 1
                if m.sin_ver > FRAMES_OLVIDO:
                    del self.monedas[m.id]

        for i, (caja, clase, conf) in enumerate(detecciones):
            if i not in usadas_det:                  # moneda nueva
                m = Moneda(self._sig_id, caja)
                self._sig_id += 1
                m.actualizar(caja, clase, conf, entera(caja))
                self.monedas[m.id] = m

        nuevas = []
        for m in self.monedas.values():
            if not m.contada and m.sin_ver == 0 and m.completa and m.frames >= self.n_confirmar:
                m.contada = True
                self.conteo[m.clase] += 1
                nuevas.append(m)
        return nuevas

    # ------------------------------------------------------------------
    def visibles(self):
        return [m for m in self.monedas.values() if m.sin_ver == 0]

    def progreso(self, m):
        return 1.0 if m.contada else min(1.0, m.frames / self.n_confirmar)

    @property
    def total_monedas(self):
        return sum(self.conteo.values())

    @property
    def total_pesos(self):
        return sum(n * config.CLASES[c][1] for c, n in self.conteo.items())
