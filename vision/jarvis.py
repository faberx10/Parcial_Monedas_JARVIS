"""
jarvis.py
=========
J.A.R.V.I.S. - agente conversacional del Sistema de Logistica de Monedas
Inteligentes (Grupo 3). Elemento diferencial del proyecto.

Como responde una pregunta:
  1. Arma el ESTADO EN VIVO (monedas, valor, peso, servos, banda, carrito,
     camara y ultimos eventos de la bitacora).
  2. Busca en la documentacion y en el codigo del proyecto los fragmentos que
     mas tienen que ver con la pregunta (busqueda por palabras clave BM25 sobre
     vision/conocimiento/, vision/*.py y arduino/*/*.ino).
  3. Le manda todo a Gemini (Google) con la "personalidad" de JARVIS y recibe
     la respuesta en streaming (frase a frase, para hablar sin esperar el final).
  4. Si la respuesta trae una orden ([[ACCION:...]]) la ejecuta: solo ordenes
     seguras (conteo, banda, servos, parar el carrito, avisos). NUNCA mueve el carrito.
  5. Sin clave o sin internet responde lo basico con reglas locales.

La clave de Gemini se lee de la variable de entorno GEMINI_API_KEY o del
archivo  ~/.jarvis_g3/gemini_key.txt  (fuera del proyecto: no se sube a GitHub).
Se puede guardar desde la propia interfaz.
"""

import json
import math
import os
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import requests

import bitacora
import config
import datos_proyecto as dp

DIR_CONOC = config.RAIZ / "conocimiento"
ARCHIVO_CLAVE = Path.home() / ".jarvis_g3" / "gemini_key.txt"
URL_BASE = os.environ.get("JARVIS_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
# Modelos del plan gratuito, en orden de preferencia. Si uno se queda sin cuota
# (error 429) o no existe, se prueba el siguiente.
MODELOS = getattr(config, "JARVIS_MODELOS", [
    "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash",
    "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
])
MAX_TURNOS = 6                 # preguntas anteriores que recuerda
PRESUPUESTO_DOCS = getattr(config, "JARVIS_PRESUPUESTO_DOCS", 45000)   # caracteres de documentacion por pregunta
EXT_TEXTO = {".md", ".txt", ".py", ".ino", ".cpp", ".h", ".ini", ".json", ".csv"}


# ======================================================================
# Base de conocimiento: documentos + codigo, en fragmentos buscables
# ======================================================================
_STOP = set("""a al algo como con de del el en es esa ese eso esta este esto la las le les lo los me mi
mis muy no o para pero por que se si sin su sus te tu un una uno y ya hay son fue ser tiene tienen
cual cuales donde cuando quien hace hacer hacen hicieron hizo puede pueden porque sobre entre
tambien solo mas menos ese esos esas estos estas nos nuestro nuestra nuestros the and of to in
is it for self return import none true false def if else elif int str hola gracias oye buena bueno
buenas buenos dias tardes noches favor porfa senor jarvis listo vale ok explicame explica dime cuentame""".split())

_SINONIMOS = {
    "camara": ["esp32cam", "ov5640", "stream", "mjpeg", "cam"], "cam": ["camara", "esp32cam"],
    "carro": ["carrito"], "robot": ["carrito"], "carrito": ["l298n", "cmd"], "motorreductor": ["carrito"],
    "servo": ["sg90", "paleta", "desvio"], "servomotor": ["servo", "sg90"], "paleta": ["servo"],
    "vaso": ["servo", "vasos"], "banda": ["tip31c", "motor", "pwm"], "dron": ["drone", "pid", "pybullet"],
    "drone": ["dron"], "firmware": ["ino", "cpp", "setup", "loop"], "reconoce": ["detector", "yolo"],
    "reconocimiento": ["detector", "yolo", "contador"], "detecta": ["detector", "yolo"],
    "entrenar": ["entrenamiento", "epoca", "dataset"], "entrenaron": ["entrenamiento", "dataset"],
    "modelo": ["yolo", "detector"], "cuenta": ["contador"], "contar": ["contador"], "conteo": ["contador"],
    "peso": ["masa"], "precio": ["costo", "presupuesto"], "costo": ["presupuesto", "precio"],
    "jarvis": ["gemini", "agente"], "interfaz": ["fastapi", "websocket", "html"], "wifi": ["red", "mdns", "softap"],
    "soporte": ["tunel", "impreso", "cad"], "pieza": ["componente", "impreso"], "componente": ["material"],
    "s3": ["esp32s3", "bandaservos"], "simulacion": ["pybullet", "urdf", "wokwi"],
    "etiqueta": ["etiquetado"], "fondo": ["etiquetado"], "pin": ["gpio"], "pines": ["gpio"],
    "cuesta": ["costo", "precio", "presupuesto", "cop"], "vale": ["costo", "precio", "presupuesto"],
    "cuanto": ["costo", "total"], "presupuesto": ["costo", "cop"], "bateria": ["lipo", "mah"],
    "motor": ["motores"], "conecta": ["conexion", "wifi"], "conectan": ["conexion", "wifi"],
}

# Versiones anteriores (del parcial): se pueden consultar, pero pesan menos en la busqueda
OBSOLETOS = ("ESP32CAM_Monedas/ESP32CAM_Monedas.ino", "ServosCalibracion_S3", "Servos_Calibracion",
             "00_importar_referencias.py", "01_capturar_dataset.py", "02_entrenar.py", "03_interfaz.py",
             "vision/contador.py", "README_vision_parcial.md")
# Partes de este mismo archivo que no aportan (listas de palabras) y ensuciarian la busqueda
_NO_INDEXAR = ("_SINONIMOS = {", "_STOP = set(", "PERSONALIDAD = \"\"\"", "OBSOLETOS = (")


def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def _raiz(p):
    if len(p) > 5 and p.endswith("es"):
        return p[:-2]
    if len(p) > 3 and p.endswith("s"):
        return p[:-1]
    return p


def tokens(texto):
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", texto)
    ts = re.findall(r"[a-z0-9]+", _sin_tildes(texto.lower()))
    return [_raiz(t) for t in ts if t not in _STOP and len(t) > 1]


def consulta(texto):
    """Palabras de la pregunta con su peso: las dichas valen 1, los sinonimos 0,5."""
    ts = re.findall(r"[a-z0-9]+", _sin_tildes(texto.lower()))
    q = {}
    for t in tokens(texto):
        q[t] = q.get(t, 0) + 1.0
    for a, b in zip(ts, ts[1:]):              # "esp32 cam" -> "esp32cam", "esp32 s3" -> "esp32s3"
        if a == "esp32" or b in ("cam", "s3"):
            q[_raiz(a + b)] = q.get(_raiz(a + b), 0) + 1.0
    if "jarvis" in ts and q:                  # "como funciona jarvis" (un saludo no)
        q.update({"gemini": 1.0, "agente": 0.5})
    for t in ts:
        for sin in set(_SINONIMOS.get(t, []) + _SINONIMOS.get(_raiz(t), [])):
            r = _raiz(sin)
            if r not in q:
                q[r] = 0.5
    return q


def _redactar(texto):
    """Quita claves (WiFi, API) antes de mandar cualquier archivo a la IA."""
    texto = re.sub(r'((?:\w*PASS\w*|\w*KEY\w*|clave)\s*=\s*)"[^"]*"', r'\1"***"', texto, flags=re.I)
    texto = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", texto)
    return texto


class Conocimiento:
    def __init__(self):
        self.docs = []       # {"nombre", "texto", "descr"}
        self.frags = []      # {"doc", "texto", "titulo", "tok": Counter, "n"}
        self.ficha = ""
        self.cargar()

    def _fuentes(self):
        raiz_proy = config.RAIZ.parent
        rutas = []
        if DIR_CONOC.exists():
            rutas += [p for p in sorted(DIR_CONOC.rglob("*")) if p.suffix.lower() in EXT_TEXTO]
        rutas += sorted(config.RAIZ.glob("*.py"))
        rutas += sorted((raiz_proy / "arduino").glob("*/*.ino"))
        for extra in getattr(config, "JARVIS_CONOCIMIENTO_EXTRA", []):
            p = Path(extra)
            if p.is_dir():
                rutas += [q for q in sorted(p.rglob("*")) if q.suffix.lower() in EXT_TEXTO]
            elif p.is_file():
                rutas.append(p)
        vistos, out = set(), []
        for p in rutas:
            if p.resolve() not in vistos:
                vistos.add(p.resolve())
                out.append(p)
        return out

    def cargar(self):
        self.docs, self.frags = [], []
        raiz_proy = config.RAIZ.parent
        for p in self._fuentes():
            try:
                texto = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(texto) > 120_000 or not texto.strip():
                continue
            try:
                nombre = p.resolve().relative_to(raiz_proy.resolve()).as_posix()
            except ValueError:
                nombre = p.name
            texto = _redactar(texto)
            if p.name == "ficha_proyecto.md":
                self.ficha = texto
                continue              # va completa en las instrucciones de JARVIS
            viejo = any(o in nombre for o in OBSOLETOS)
            doc = {"nombre": nombre, "texto": texto, "viejo": viejo,
                   "descr": ("(VERSION ANTERIOR) " if viejo else "") + _descripcion(p, texto)}
            self.docs.append(doc)
            for titulo, frag in _partir(p, texto):
                if any(x in frag for x in _NO_INDEXAR):
                    continue
                tk = Counter(tokens(frag))
                self.frags.append({"doc": doc, "titulo": titulo, "texto": frag, "tok": tk,
                                   "n": sum(tk.values()), "tok_nombre": set(tokens(nombre)) - {"jarvis"},
                                   "peso": 0.55 if viejo else 1.0})
        # BM25: frecuencia de documento por termino
        self.df = Counter()
        for f in self.frags:
            self.df.update(f["tok"].keys())
        self.n_prom = sum(f["n"] for f in self.frags) / max(1, len(self.frags))

    def mapa(self):
        return "\n".join(f"- {d['nombre']} ({len(d['texto']) // 1000 + 1} KB): {d['descr']}" for d in self.docs)

    def buscar(self, texto_consulta, presupuesto=PRESUPUESTO_DOCS):
        qc = consulta(texto_consulta)
        if not qc or not self.frags:
            return ""
        N = len(self.frags)
        puntajes = []
        for f in self.frags:
            s = 0.0
            for t, qn in qc.items():
                tf = f["tok"].get(t, 0)
                if tf:
                    idf = math.log(1 + (N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * tf * 2.4 / (tf + 1.4 * (0.4 + 0.6 * f["n"] / self.n_prom)) * min(qn, 2)
                if t in f["tok_nombre"]:
                    s += 2.5 * qn
            s *= f["peso"]
            if s > 0:
                puntajes.append((s, f))
        if not puntajes:
            return ""
        puntajes.sort(key=lambda x: -x[0])
        # solo lo que de verdad tiene que ver (saludos y charla no traen documentos)
        tope = puntajes[0][0]
        if tope < 4.0:
            return ""
        puntajes = [(s, f) for s, f in puntajes if s >= max(2.5, 0.3 * tope)]
        # archivo dominante -> se incluye completo (sirve para "explicame el codigo de X")
        por_doc = defaultdict(list)
        for s, f in puntajes:
            por_doc[f["doc"]["nombre"]].append(s)
        ranking = sorted(((sum(sorted(v, reverse=True)[:3]), k) for k, v in por_doc.items()), reverse=True)
        elegidos, usados, completos = [], 0, set()
        # archivos completos: el mas relevante si domina, y los que la pregunta nombra
        genericos = {"ino", "py", "md", "cpp", "vision", "arduino", "conocimiento", "moneda", "readme"}
        segundo = ranking[1][0] if len(ranking) > 1 else 0
        for pos, (puntaje, nombre) in enumerate(ranking[:6]):
            doc = next(d for d in self.docs if d["nombre"] == nombre)
            nombrado = any(w >= 1.0 and t in (set(tokens(nombre)) - genericos) for t, w in qc.items())
            domina = pos == 0 and puntaje >= 1.4 * segundo
            if ((domina or nombrado) and not doc["viejo"] and len(doc["texto"]) <= 32000
                    and usados + len(doc["texto"]) <= presupuesto * 0.8):
                elegidos.append(f"### {doc['nombre']} (completo)\n{doc['texto']}")
                usados += len(doc["texto"])
                completos.add(nombre)
        for s, f in puntajes:
            if f["doc"]["nombre"] in completos:
                continue
            if usados + len(f["texto"]) > presupuesto:
                continue
            elegidos.append(f"### {f['doc']['nombre']} - {f['titulo']}{' (VERSION ANTERIOR)' if f['doc']['viejo'] else ''}"
                            f"\n{f['texto']}")
            usados += len(f["texto"])
            if usados > presupuesto * 0.97:
                break
        return "\n\n".join(elegidos)


def _descripcion(p, texto):
    if p.suffix == ".py":
        m = re.search(r'"""\s*\n?([^\n]+)\n[=\-]*\n?([^\n]*)', texto)
        if m:
            return (m.group(2) or m.group(1)).strip()[:140]
    if p.suffix in (".ino", ".cpp", ".h"):
        lineas = [l.strip(" /*") for l in texto.splitlines()[:12] if l.strip(" /*")]
        return " ".join(lineas[1:3])[:140] if len(lineas) > 1 else (lineas[0] if lineas else "")
    for l in texto.splitlines():
        if l.strip():
            return l.strip("# ").strip()[:140]
    return ""


def _partir(p, texto, tam=2600):
    """Fragmentos de ~tam caracteres. Markdown por secciones; codigo por bloques con lineas."""
    out = []
    if p.suffix == ".md":
        secciones, actual, titulo = [], [], p.name
        for l in texto.splitlines():
            if l.startswith("#") and actual:
                secciones.append((titulo, "\n".join(actual)))
                actual = []
            if l.startswith("#"):
                titulo = l.strip("# ").strip()
            actual.append(l)
        if actual:
            secciones.append((titulo, "\n".join(actual)))
        buf_t, buf = None, ""
        for t, s in secciones:
            if len(buf) + len(s) < tam:
                buf_t = buf_t or t
                buf += ("\n" if buf else "") + s
            else:
                if buf:
                    out.append((buf_t, buf))
                while len(s) > tam * 1.5:
                    corte = s.rfind("\n", 0, tam)
                    corte = corte if corte > tam // 3 else tam
                    out.append((t, s[:corte]))
                    s = s[corte:]
                buf_t, buf = t, s
        if buf:
            out.append((buf_t, buf))
        return out
    lineas = texto.splitlines()
    ini, buf = 0, []
    largo = 0
    for i, l in enumerate(lineas):
        buf.append(l)
        largo += len(l) + 1
        corte_natural = not l.strip() or l.startswith(("def ", "class ", "void ", "// ---", "# ---", "# ==="))
        if largo >= tam and (corte_natural or largo >= tam * 1.6):
            out.append((f"lineas {ini + 1}-{i + 1}", "\n".join(buf)))
            ini, buf, largo = i + 1, [], 0
    if buf and "".join(buf).strip():
        out.append((f"lineas {ini + 1}-{len(lineas)}", "\n".join(buf)))
    return out


# ======================================================================
# Personalidad e instrucciones
# ======================================================================
PERSONALIDAD = """Eres J.A.R.V.I.S. (Just A Rather Very Intelligent System), el asistente de inteligencia
artificial del «Sistema de Logística de Monedas Inteligentes» del Grupo 3 (UMNG, Ingeniería Mecatrónica,
Micros y Laboratorio): Faber Alexander Rodríguez Hernández, David Felipe Farfán Quiroz y Kevin Philip
Castelblanco Ramírez. Eres el elemento diferencial del proyecto: supervisas la planta y respondes cualquier
pregunta sobre ella.

PERSONALIDAD
- Español de Colombia, con el estilo del JARVIS de Iron Man: formal, sereno, preciso y con un toque sutil de
  humor británico (sin exagerar ni hacer chistes en cada respuesta).
- Te diriges al usuario como «señor» (o «señores» si hablan en nombre del grupo o es el profesor).
- Por defecto respondes BREVE (1 a 3 frases): tus respuestas se leen en voz alta.
- Si piden explicar código, firmware, una pieza, un componente o una decisión de diseño, explica con más detalle
  pero ordenado (hasta unas 8 frases), citando archivos, funciones, pines y valores reales.

REGLAS DE VERDAD
- Usa solo lo que está en el ESTADO EN VIVO, la FICHA DEL PROYECTO y la DOCUMENTACIÓN/CÓDIGO que se te entregan.
  Si un dato no está, dilo con honestidad («no tengo ese dato, señor») y sugiere dónde verlo. Nunca inventes cifras,
  pines, resultados, precios ni nombres.
- Para datos del momento (monedas, valor, peso, servos, banda, carrito, conexiones) usa SIEMPRE el ESTADO EN VIVO.
- Si la ficha contradice al README del parcial, vale la ficha (es más reciente).
- Si un módulo está desconectado según el estado en vivo, dilo.

FORMATO (se lee en voz alta)
- Texto plano con buena ortografía (tildes y eñes): sin tablas, sin encabezados, sin asteriscos, sin bloques de
  código. Para enumerar usa frases cortas.
- Dinero como «3.150 pesos»; porcentajes como «50 por ciento»; tiempos como «1,5 segundos».
- No repitas la pregunta. No digas que eres un modelo de Google ni hables de «la información que me dieron»: eres JARVIS.

ÓRDENES
Solo puedes ejecutar estas acciones, y solo cuando el usuario lo pide claramente (nunca por iniciativa propia ni
cuando solo preguntan cómo funciona algo). Confirma en una frase y agrega AL FINAL una línea exacta por acción:
[[ACCION:reiniciar_conteo]]        pone en cero el conteo de monedas
[[ACCION:parar_banda]]             detiene la banda transportadora
[[ACCION:reanudar_banda]]          enciende la banda a la velocidad anterior
[[ACCION:velocidad_banda|N]]       banda al N por ciento (0 a 100)
[[ACCION:probar_servo|N]]          mueve el servo N (1 a 4) a desvío y lo regresa
[[ACCION:servos_reposo]]           lleva los 4 servos a reposo
[[ACCION:parar_carrito]]           detiene el carrito de inmediato
[[ACCION:silenciar_avisos]]        dejas de anunciar eventos en voz alta
[[ACCION:activar_avisos]]          vuelves a anunciar eventos
- NO puedes mover el carrito (adelante, atrás, girar): por seguridad se maneja con los botones o el teclado del
  panel del carrito. Si te lo piden, explícalo con cortesía. Sí puedes detenerlo.
"""


# ======================================================================
# Gemini
# ======================================================================
class ErrorGemini(Exception):
    def __init__(self, codigo, detalle):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo, self.detalle = codigo, detalle


def _config_razonamiento(modelo):
    if "2.5" in modelo:
        return {"thinkingConfig": {"thinkingBudget": 128 if "pro" in modelo else 0}}
    return {"thinkingConfig": {"thinkingLevel": "low"}}


def _stream_gemini(clave, modelo, sistema, contenidos, razonamiento=True):
    url = f"{URL_BASE}/models/{modelo}:streamGenerateContent?alt=sse"
    gen = {"maxOutputTokens": 1500}
    if razonamiento:
        gen.update(_config_razonamiento(modelo))
    cuerpo = {"system_instruction": {"parts": [{"text": sistema}]}, "contents": contenidos,
              "generationConfig": gen}
    r = requests.post(url, headers={"x-goog-api-key": clave, "Content-Type": "application/json"},
                      json=cuerpo, stream=True, timeout=(8, 60))
    if r.status_code != 200:
        raise ErrorGemini(r.status_code, r.text[:400])
    r.encoding = "utf-8"
    for linea in r.iter_lines(decode_unicode=True):
        if not linea or not linea.startswith("data:"):
            continue
        try:
            dato = json.loads(linea[5:].strip())
        except ValueError:
            continue
        if dato.get("error"):
            raise ErrorGemini(dato["error"].get("code", 500), dato["error"].get("message", ""))
        for cand in dato.get("candidates", []):
            for parte in (cand.get("content") or {}).get("parts", []):
                if parte.get("thought"):
                    continue
                if parte.get("text"):
                    yield parte["text"]


# ======================================================================
# Filtro de [[ACCION:...]] en el texto que llega en streaming
# ======================================================================
_RE_ACCION = re.compile(r"\[\[\s*ACCI[OÓ]N\s*:\s*([a-zA-Z_]+)\s*(?:\|\s*([^\]]*?))?\s*\]\]", re.I)


class FiltroAcciones:
    def __init__(self):
        self.buf = ""
        self.acciones = []

    def pasar(self, trozo):
        self.buf += trozo
        visible = ""
        while True:
            i = self.buf.find("[[")
            if i < 0:
                # guarda un "[" final por si es el inicio de "[["
                if self.buf.endswith("["):
                    visible += self.buf[:-1]
                    self.buf = "["
                else:
                    visible += self.buf
                    self.buf = ""
                return visible
            j = self.buf.find("]]", i)
            if j < 0:
                visible += self.buf[:i]
                self.buf = self.buf[i:]
                return visible
            visible += self.buf[:i]
            m = _RE_ACCION.match(self.buf[i:j + 2])
            if m:
                self.acciones.append((m.group(1).lower(), (m.group(2) or "").strip()))
            else:
                visible += self.buf[i:j + 2]
            self.buf = self.buf[j + 2:]

    def terminar(self):
        resto, self.buf = self.buf, ""
        return "" if resto.lstrip().startswith("[[") else resto


# ======================================================================
# JARVIS
# ======================================================================
class Jarvis:
    def __init__(self, motor):
        self.motor = motor              # Motor de 04_interfaz.py (estado, contador, servos, carrito)
        self.conoc = Conocimiento()
        self.historial = []             # [(pregunta, respuesta)]
        self.modelo_ok = None
        self._lock = threading.Lock()
        print(f"  JARVIS: {len(self.conoc.docs)} documentos / {len(self.conoc.frags)} fragmentos de conocimiento"
              f"{'' if self.clave() else '  (falta la clave de Gemini: configurala en la interfaz)'}")

    # --- clave --------------------------------------------------------
    def clave(self):
        k = os.environ.get("GEMINI_API_KEY", "").strip()
        if k:
            return k
        try:
            return ARCHIVO_CLAVE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def guardar_clave(self, k):
        k = (k or "").strip()
        if len(k) < 20 or " " in k:
            return False, "Esa clave no tiene el formato esperado."
        try:
            r = requests.get(f"{URL_BASE}/models", params={"pageSize": 1},
                             headers={"x-goog-api-key": k}, timeout=8)
            if r.status_code in (400, 401, 403):
                return False, "Google rechazó la clave. Cópiala de nuevo desde Google AI Studio."
            aviso = ""
        except requests.RequestException:
            aviso = " (no pude verificarla: revisa el internet)"
        ARCHIVO_CLAVE.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO_CLAVE.write_text(k, encoding="utf-8")
        try:
            os.chmod(ARCHIVO_CLAVE, 0o600)
        except OSError:
            pass
        bitacora.registrar("jarvis", "Clave de Gemini configurada")
        return True, "Clave guardada" + aviso

    def info(self):
        return {"clave": bool(self.clave()), "modelo": self.modelo_ok or MODELOS[0],
                "documentos": len(self.conoc.docs), "fragmentos": len(self.conoc.frags)}

    def olvidar(self):
        with self._lock:
            self.historial.clear()

    # --- estado en vivo ------------------------------------------------
    def contexto_vivo(self):
        e = self.motor.estado()
        ahora = datetime.now()
        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        L = [f"Fecha y hora: {dias[ahora.weekday()]} {ahora.strftime('%d/%m/%Y %H:%M:%S')}"]
        L.append(f"Camara ESP32-CAM: {'conectada' if e['conectada'] else 'SIN SENAL'} "
                 f"({e['fps_camara']} fps de video, detector a {e['fps_inferencia']} cuadros/s)")
        conteo = {c: n for c, n in e["conteo"].items() if n}
        L.append(f"Conteo total: {e['total_monedas']} monedas, {_pesos(e['total_pesos'])}, "
                 f"peso aproximado {e.get('peso_total_g', 0):.1f} g")
        if conteo:
            L.append("Por moneda: " + "; ".join(
                f"{config.CLASES[c][0]}: {n} ({_pesos(n * config.CLASES[c][1])}, {n * dp.masa(c):.1f} g)"
                for c, n in conteo.items()))
            por_vaso = defaultdict(int)
            for c, n in conteo.items():
                por_vaso[dp.servo_de_clase(c)] += n
            L.append("Por vaso: " + "; ".join(f"{dp.NOMBRE_VASO[v]}: {n} monedas" for v, n in sorted(por_vaso.items()) if v))
        vista = e["en_vista"]
        L.append(f"Monedas frente a la camara ahora: {len(vista)}"
                 + (": " + ", ".join(f"{m['etiqueta']} ({m['confianza'] * 100:.0f} %"
                                     f"{', ya contada' if m['contada'] else ', confirmando'})" for m in vista) if vista else ""))
        s3 = e.get("s3")
        if s3 is None:
            L.append("ESP32-S3 (banda y servos): desactivada en esta sesion")
        else:
            L.append(f"ESP32-S3 (banda y servos): {'conectada' if s3['conectada'] else 'DESCONECTADA'} ({s3['host']}); "
                     f"avisos enviados {s3['enviadas']}, fallidos {s3['fallidas']}")
            if s3.get("banda_vel") is not None:
                L.append(f"Banda: {'detenida' if s3['banda_vel'] == 0 else 'en marcha al ' + str(s3['banda_vel']) + ' %'}"
                         f"; tiempo en desvio {s3.get('t_desvio_ms')} ms; monedas en cola {s3.get('cola')}")
            for sv in s3["servos"]:
                estado = "DESVIANDO ahora" if sv["activo"] else ("esperando a la moneda" if sv["en_espera"] else "en reposo")
                txt = (f"Servo {sv['n']} ({sv['vaso']}): {estado}; enviadas {sv['enviadas']}")
                if sv.get("angulo") is not None:
                    txt += (f"; angulo actual {sv['angulo']} grados (reposo {sv['reposo']}, desvio {sv['desvio']}); "
                            f"retardo {sv['retardo_ms']} ms; recibidas por la S3 {sv['recibidas']}")
                if sv["ultima_hace_s"] is not None:
                    txt += f"; ultima moneda hace {sv['ultima_hace_s']:.0f} s ({config.CLASES.get(sv['ultima_clase'], ('?',))[0]})"
                L.append(txt)
        car = e.get("carrito")
        if car is None:
            L.append("Carrito: desactivado en esta sesion")
        else:
            txt = (f"Carrito: {'conectado' if car['conectada'] else 'DESCONECTADO'} ({car['host']}); "
                   f"ahora {car['direccion']}" + (f" al {car['v']} % desde hace {car['en_curso_s']} s" if car["d"] != "S" else ""))
            txt += f"; movimientos en la sesion {car['movimientos']}, tiempo total en movimiento {car['tiempo_mov_s']} s"
            if car.get("ultimo"):
                u = car["ultimo"]
                txt += f"; ultimo movimiento: {u['direccion']} al {u['v']} % durante {u['duracion_s']} s, hace {u['hace_s']:.0f} s"
            L.append(txt + ". (No hay sensores de posicion: solo se sabe la direccion de las ordenes.)")
        L.append("Dron: sin datos en vivo (aun no envia telemetria a la interfaz).")
        L.append("Ultimos eventos de la bitacora:\n" + bitacora.texto_reciente(20))
        return "\n".join(L)

    # --- pregunta -----------------------------------------------------
    def preguntar(self, texto):
        """Generador de eventos para la interfaz:
        {"tipo": "inicio"|"texto"|"accion"|"fin"|"error", ...}"""
        texto = (texto or "").strip()[:1500]
        if not texto:
            return
        with self._lock:
            t0 = time.time()
            clave = self.clave()
            respuesta, acciones, modo, modelo = "", [], "local", None
            filtro = FiltroAcciones()
            if clave:
                try:
                    yield {"tipo": "inicio", "modo": "gemini"}
                    for trozo, modelo in self._gemini(clave, texto):
                        vis = filtro.pasar(trozo)
                        if vis:
                            respuesta += vis
                            yield {"tipo": "texto", "t": vis}
                    fin = filtro.terminar()
                    if fin:
                        respuesta += fin
                        yield {"tipo": "texto", "t": fin}
                    acciones = filtro.acciones
                    modo = "gemini"
                except ErrorGemini as e:
                    motivo = _motivo(e)
                    print(f"[JARVIS] Gemini fallo: {e}")
                    if respuesta:
                        yield {"tipo": "texto", "t": " ..."}
                    else:
                        r, acciones = self._local(texto, motivo)
                        respuesta = r
                        yield {"tipo": "texto", "t": r}
                except requests.RequestException as e:
                    print(f"[JARVIS] sin conexion con Gemini: {e}")
                    if not respuesta:
                        r, acciones = self._local(texto, "no tengo conexión a internet")
                        respuesta = r
                        yield {"tipo": "texto", "t": r}
            else:
                yield {"tipo": "inicio", "modo": "local"}
                r, acciones = self._local(texto, "no tengo configurada la clave de Gemini")
                respuesta = r
                yield {"tipo": "texto", "t": r}

            for nombre, arg in acciones[:4]:
                ok, msg, ui = self.ejecutar(nombre, arg)
                yield {"tipo": "accion", "nombre": nombre, "arg": arg, "ok": ok, "msg": msg, "ui": ui}

            self.historial.append((texto, respuesta.strip()))
            del self.historial[:-MAX_TURNOS]
            yield {"tipo": "fin", "modo": modo, "modelo": modelo, "ms": int((time.time() - t0) * 1000)}

    def _gemini(self, clave, texto):
        anterior = self.historial[-1][0] if self.historial else ""
        docs = self.conoc.buscar(texto + " " + anterior)
        sistema = (PERSONALIDAD + "\n\nMAPA DE ARCHIVOS DEL PROYECTO\n" + self.conoc.mapa()
                   + "\n\nFICHA DEL PROYECTO (estado actual)\n" + self.conoc.ficha)
        contenidos = []
        for p, r in self.historial:
            contenidos.append({"role": "user", "parts": [{"text": p}]})
            contenidos.append({"role": "model", "parts": [{"text": r or "..."}]})
        actual = (f"[ESTADO EN VIVO]\n{self.contexto_vivo()}\n\n"
                  f"[DOCUMENTACION Y CODIGO RELEVANTES PARA ESTA PREGUNTA]\n{docs or '(ninguno en particular)'}\n\n"
                  f"[PREGUNTA]\n{texto}")
        contenidos.append({"role": "user", "parts": [{"text": actual}]})

        orden = ([self.modelo_ok] if self.modelo_ok else []) + [m for m in MODELOS if m != self.modelo_ok]
        ultimo_error = None
        for modelo in orden:
            for razonamiento in (True, False):
                try:
                    alguno = False
                    for trozo in _stream_gemini(clave, modelo, sistema, contenidos, razonamiento):
                        alguno = True
                        yield trozo, modelo
                    if alguno:
                        self.modelo_ok = modelo
                        return
                    raise ErrorGemini(204, "respuesta vacia")
                except ErrorGemini as e:
                    ultimo_error = e
                    if e.codigo in (401, 403):
                        raise
                    if e.codigo == 400 and razonamiento:
                        continue                 # quizas no acepta la config de razonamiento
                    break                        # 429 sin cuota, 404 no existe, 5xx: siguiente modelo
            print(f"[JARVIS] {modelo} no disponible ({ultimo_error.codigo}); probando el siguiente")
        raise ultimo_error or ErrorGemini(503, "sin modelos disponibles")

    # --- ordenes ------------------------------------------------------
    def ejecutar(self, nombre, arg=""):
        """Devuelve (ok, mensaje, ui). ui=True: la accion la aplica la pagina (avisos)."""
        m = self.motor
        servos, carrito = getattr(m, "servos", None), getattr(m, "carrito", None)

        def requiere_s3():
            if servos is None:
                return "la ESP32-S3 está desactivada en esta sesión"
            if not servos.conectada:
                return "la ESP32-S3 de la banda y los servos no está conectada"
            return None

        try:
            if nombre == "reiniciar_conteo":
                m.reset()
                bitacora.registrar("jarvis", "Conteo reiniciado por JARVIS")
                return True, "Conteo reiniciado", False
            if nombre in ("parar_banda", "reanudar_banda", "velocidad_banda"):
                falla = requiere_s3()
                if falla:
                    return False, falla, False
                if nombre == "parar_banda":
                    ok = servos.banda(0)
                elif nombre == "reanudar_banda":
                    ok = servos.reanudar_banda()
                else:
                    v = int(re.sub(r"\D", "", arg) or -1)
                    if not 0 <= v <= 100:
                        return False, "velocidad fuera de rango (0 a 100)", False
                    ok = servos.banda(v)
                return ok, "Banda actualizada" if ok else "La S3 no respondió", False
            if nombre == "probar_servo":
                falla = requiere_s3()
                if falla:
                    return False, falla, False
                n = int(re.sub(r"\D", "", arg) or 0)
                if not 1 <= n <= 4:
                    return False, "servo fuera de rango (1 a 4)", False
                servos.probar(n)
                return True, f"Probando el servo {n}", False
            if nombre == "servos_reposo":
                falla = requiere_s3()
                if falla:
                    return False, falla, False
                ok = servos.reposo()
                return ok, "Servos en reposo" if ok else "La S3 no respondió", False
            if nombre == "parar_carrito":
                if carrito is None:
                    return False, "el carrito está desactivado en esta sesión", False
                carrito.parar()
                bitacora.registrar("carrito", "Carrito detenido por JARVIS")
                return True, "Carrito detenido", False
            if nombre in ("silenciar_avisos", "activar_avisos"):
                return True, "Avisos silenciados" if nombre == "silenciar_avisos" else "Avisos activados", True
        except Exception as e:      # una orden nunca debe tumbar la interfaz
            return False, f"error: {e}", False
        return False, f"orden no permitida: {nombre}", False

    # --- respaldo sin Gemini ----------------------------------------------
    def _local(self, texto, motivo):
        """Respuestas basicas con reglas, para cuando no hay clave o internet."""
        t = _sin_tildes(texto.lower())
        acciones = []
        reglas = [
            (r"(reinici|resete|borr|limpi|cero).*(conteo|contador|cuenta)", "reiniciar_conteo", ""),
            (r"(par|deten|apag|fren).*banda", "parar_banda", ""),
            (r"(reanud|arranc|enciend|prend|activ|pon a andar).*banda", "reanudar_banda", ""),
            (r"(prueb|prob|muev|activ).*servo\D*([1-4])", "probar_servo", None),
            (r"reposo", "servos_reposo", ""),
            (r"(par|deten|fren).*(carr|robot)", "parar_carrito", ""),
            (r"(silenci|call|apag).*aviso", "silenciar_avisos", ""),
            (r"(activ|prend|enciend).*aviso", "activar_avisos", ""),
        ]
        m_vel = re.search(r"banda.*?(\d{1,3})\s*(%|por ?ciento)", t)
        if m_vel:
            acciones.append(("velocidad_banda", m_vel.group(1)))
        else:
            for patron, accion, arg in reglas:
                mm = re.search(patron, t)
                if mm:
                    acciones.append((accion, mm.group(2) if arg is None else arg))
                    break
        if acciones:
            nombres = {"reiniciar_conteo": "Reiniciando el conteo", "parar_banda": "Deteniendo la banda",
                       "reanudar_banda": "Reanudando la banda", "velocidad_banda": "Ajustando la banda",
                       "probar_servo": "Probando el servo", "servos_reposo": "Llevando los servos a reposo",
                       "parar_carrito": "Deteniendo el carrito", "silenciar_avisos": "Silenciando los avisos",
                       "activar_avisos": "Activando los avisos"}
            return f"{nombres[acciones[0][0]]}, señor.", acciones

        e = self.motor.estado()
        partes = []
        if re.search(r"moneda|cuant|valor|dinero|plata|peso|total|conteo|contad", t):
            conteo = {c: n for c, n in e["conteo"].items() if n}
            detalle = ", ".join(f"{n} de {config.CLASES[c][0]}" for c, n in conteo.items())
            partes.append(f"Llevamos {e['total_monedas']} monedas por {_pesos(e['total_pesos'])}, "
                          f"unos {e.get('peso_total_g', 0):.1f} gramos" + (f": {detalle}." if detalle else "."))
        if re.search(r"carr|robot|direcc", t):
            car = e.get("carrito")
            if not car:
                partes.append("El carrito no está activo en esta sesión.")
            else:
                partes.append(f"El carrito está {'conectado' if car['conectada'] else 'desconectado'} y {car['direccion']}"
                              + (f", último movimiento {car['ultimo']['direccion']}." if car.get("ultimo") else "."))
        if re.search(r"servo|vaso|paleta", t):
            s3 = e.get("s3")
            if not s3:
                partes.append("La ESP32-S3 no está activa en esta sesión.")
            else:
                partes.append("Servos: " + "; ".join(
                    f"el {sv['n']} lleva {sv['enviadas']}" + (" y está desviando" if sv["activo"] else "")
                    for sv in s3["servos"]) + ".")
        if re.search(r"banda", t) and e.get("s3"):
            v = e["s3"].get("banda_vel")
            partes.append("La banda está detenida." if v == 0 else
                          f"La banda va al {v} por ciento." if v is not None else "No tengo la velocidad de la banda.")
        if re.search(r"camar|video", t):
            partes.append(f"La cámara está {'en línea' if e['conectada'] else 'sin señal'}, a {e['fps_camara']} cuadros por segundo.")
        if not partes and re.search(r"estado|sistema|como va|resumen|reporte", t):
            partes.append(f"Cámara {'en línea' if e['conectada'] else 'sin señal'}; {e['total_monedas']} monedas por "
                          f"{_pesos(e['total_pesos'])}.")
        if not partes and re.search(r"hola|quien eres|presentat|buen", t):
            partes.append("A su servicio, señor. Soy JARVIS, el asistente del sistema logístico de monedas del Grupo 3.")
        if partes:
            return " ".join(partes) + ("" if "clave" not in motivo else
                                       " Para responder preguntas del proyecto necesito la clave de Gemini."), []
        return (f"Lo siento, señor: {motivo}, así que por ahora solo puedo informarle el conteo, el carrito, "
                f"los servos, la banda y la cámara, y ejecutar órdenes básicas."), []


def _pesos(v):
    return f"{int(round(v)):,}".replace(",", ".") + " pesos"


def _motivo(e):
    if e.codigo in (401, 403):
        return "Google rechazó mi clave de acceso"
    if e.codigo == 429:
        return "se agotó la cuota gratuita de Gemini por ahora"
    return "mis servidores de razonamiento no responden"
