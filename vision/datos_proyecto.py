"""
datos_proyecto.py
=================
Datos fijos del proyecto que usan la interfaz y JARVIS: masa de cada moneda,
a que vaso/servo va y como se nombran las direcciones del carrito.
"""

# Masa aproximada (g): guia de empaque de moneda del Banco de la Republica
# (peso de la bolsa / cantidad de monedas). Nuevas = familia 2012.
MASA_G = {
    "1000_nueva": 9.32,
    "500_nueva": 7.14,
    "500_antigua": 7.11,
    "200_nueva": 4.61,
    "200_antigua": 7.10,
    "100_nueva": 3.34,
    "100_antigua": 5.25,
    "50_nueva": 2.00,
    "50_antigua": 4.50,
}

# Servo/vaso de cada denominacion (igual que servoDeValor() en BandaServos_S3.ino)
SERVO_DE_VALOR = {1000: 1, 500: 1, 200: 2, 100: 3, 50: 4}
NOMBRE_VASO = {1: "vaso de $1.000 y $500", 2: "vaso de $200", 3: "vaso de $100", 4: "vaso de $50"}

# Direcciones del carrito (firmware carrito_transporte)
DIRECCION = {
    "F": "adelante", "B": "atras", "L": "girando a la izquierda", "R": "girando a la derecha",
    "FL": "adelante hacia la izquierda", "FR": "adelante hacia la derecha",
    "BL": "atras hacia la izquierda", "BR": "atras hacia la derecha", "S": "detenido",
}


def masa(clase):
    return MASA_G.get(clase, 0.0)


def peso_total(conteo):
    """conteo: {clase: n} -> gramos."""
    return sum(masa(c) * n for c, n in conteo.items())


def servo_de_clase(clase):
    try:
        return SERVO_DE_VALOR.get(int(clase.split("_")[0]))
    except (ValueError, AttributeError):
        return None
