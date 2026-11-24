"""
config.py
=========
Configuracion central del reconocimiento de monedas - Grupo 3.
Todo lo que tengas que cambiar (IP, umbrales, clases) esta aqui.
"""

from pathlib import Path

# ----------------------------------------------------------------------
# ESP32-CAM
# ----------------------------------------------------------------------
ESP32_IP = "10.193.83.226"              # <-- cambiala si tu router asigna otra
STREAM_URL = f"http://{ESP32_IP}:81/stream"
CONTROL_URL = f"http://{ESP32_IP}/control"

# Ajustes que se envian a la camara al arrancar (se pierden cada vez que
# la ESP32 se reinicia, por eso los aplicamos desde el PC).
# La resolucion (SVGA 800x600) se fija en el sketch ESP32CAM_Monedas.ino.
AJUSTES_CAMARA = {
    "quality": 8,         # 0-63, menor = mejor calidad (8: mas detalle del relieve)
    "vflip": 0,           # tu camara salia al reves: 1 la endereza (0 si queda al reves)
    "hmirror": 0,
    "led_intensity": 0,   # flash siempre apagado (la caja tiene LEDs de ambiente)
    
}

# Fraccion del lado menor de la imagen que se recorta al centro (cuadrado).
# La moneda debe quedar dentro del circulo guia que dibujan los scripts.
FRACCION_RECORTE = 0.80
TAM_GUARDADO = 320      # px del recorte que se guarda en el dataset

# ----------------------------------------------------------------------
# Clases: nombre interno -> (etiqueta visible, valor en pesos, tecla)
# ----------------------------------------------------------------------
CLASES = {
    "1000_nueva":  ("$1.000 nueva",  1000, "1"),
    "500_nueva":   ("$500 nueva",     500, "2"),
    "500_antigua": ("$500 antigua",   500, "3"),
    "200_nueva":   ("$200 nueva",     200, "4"),
    "200_antigua": ("$200 antigua",   200, "5"),
    "100_nueva":   ("$100 nueva",     100, "6"),
    "100_antigua": ("$100 antigua",   100, "7"),
    "50_nueva":    ("$50 nueva",       50, "8"),
    "50_antigua":  ("$50 antigua",     50, "9"),
    "fondo":       ("Sin moneda",       0, "0"),
}
CLASE_FONDO = "fondo"
CLASES_MONEDA = [c for c in CLASES if c != CLASE_FONDO]

# ----------------------------------------------------------------------
# Reglas de conteo (evitan contar dos veces la misma moneda)
# ----------------------------------------------------------------------
UMBRAL_CONFIANZA = 0.85   # confianza minima para aceptar una prediccion
FRAMES_ESTABLES = 6       # frames seguidos con la misma moneda para contarla
FRAMES_VACIO = 5          # frames de fondo para "rearmar" el contador

# ----------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
DIR_DATASET_CRUDO = RAIZ / "dataset_crudo"   # lo que captura el script 01
DIR_DATASET = RAIZ / "dataset"               # train/val que arma el script 02
DIR_MODELOS = RAIZ / "modelos"
RUTA_MODELO = DIR_MODELOS / "monedas.pt"
DIR_CAPTURAS = RAIZ / "capturas"             # fotos de cada moneda contada

# ----------------------------------------------------------------------
# Detector de VARIAS monedas a la vez (YOLO deteccion)
# ----------------------------------------------------------------------
DIR_DET_CRUDO = RAIZ / "dataset_det_crudo"   # fotos de 01_capturar_deteccion.py
DIR_DET = RAIZ / "dataset_det"               # dataset YOLO que arma 02_preparar_deteccion.py
RUTA_MODELO_DET = DIR_MODELOS / "monedas_det.pt"
IMGSZ_DET = 640                # tamano de entrada del detector
UMBRAL_DET = 0.60              # confianza minima para dibujar/contar una moneda
FRAMES_CONFIRMAR = 4           # frames que una moneda debe verse para contarla

# ----------------------------------------------------------------------
# ESP32-S3 (motor de la banda + servos de los vasos)
# ----------------------------------------------------------------------
S3_HOST = "banda-s3.local"     # o la IP que muestra el Monitor Serie de la S3 (ej. "10.193.83.40")
S3_ACTIVO = True               # False = la interfaz no avisa a la S3

# ----------------------------------------------------------------------
# Carrito de transporte (ESP32 + L298N)  -  firmware carrito_transporte
# ----------------------------------------------------------------------
CARRITO_HOST = "carrito-g3.local"   # o su IP (la muestra su Monitor Serie: "Interfaz del PC: http://...")
CARRITO_ACTIVO = True               # False = sin panel de control del carrito

# ----------------------------------------------------------------------
# JARVIS (asistente de IA). La clave de Gemini NO va aqui: se guarda desde la
# interfaz en  C:\Users\<usuario>\.jarvis_g3\gemini_key.txt  (fuera del proyecto).
# ----------------------------------------------------------------------
# JARVIS_MODELOS = ["gemini-3.5-flash", "gemini-2.5-flash"]   # orden de modelos a probar
# JARVIS_CONOCIMIENTO_EXTRA = []        # carpetas o archivos extra que debe estudiar
