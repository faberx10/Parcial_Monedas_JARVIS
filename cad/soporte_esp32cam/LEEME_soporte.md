# Soporte túnel para ESP32-CAM sobre la banda transportadora
Sistema de Logística de Monedas Inteligentes · Grupo 3 · UMNG

## Archivos
| Archivo | Para qué |
|---|---|
| `ensamble_soporte_camara.step` | Abrir en SolidWorks: túnel + tapa + carro + banda de referencia |
| `tunel_camara.step`, `tapa_tunel.step`, `carro_camara.step` | Cada pieza por separado (SolidWorks / cualquier CAD) |
| `*_IMPRIMIR.stl` | Mandar a imprimir; ya vienen en la posición correcta |
| `soporte_camara.py` | Modelo paramétrico (CadQuery): cambia medidas y regenera todo |

## Medidas de diseño
- Encaja sobre una banda de **95 mm de ancho exterior** con paredes MDF de 3 mm (holgura 0,4 mm).
- Túnel: 100,4 × 120 × 130 mm (+ tapa de 2,5 mm). La falda baja 12 mm por fuera del MDF; una pestaña de 3 mm apoya sobre el borde del MDF.
- Embudo que lleva las monedas a un **canal de 34 mm** justo debajo de la cámara (la moneda más grande mide 26,7 mm). Las aletas quedan a **0,8 mm** del cuero para que ninguna moneda pase por debajo.
- Bocas de entrada y salida de 10 mm de alto. El resto está cerrado para que la luz sea siempre la misma.
- Cámara regulable: lente de **~50 a ~90 mm** sobre la banda, con marcas cada 1 cm junto a la ranura (larga = 5, 7 y 9 cm). **Empieza en ~65 mm**, que es donde la moneda llena el recorte central de la interfaz como en el entrenamiento.

## Impresión (PLA, cama 256 × 256)
| Pieza | Posición | Soportes |
|---|---|---|
| Túnel | boca arriba como viene en el STL (bordes superiores sobre la cama) | **No** (las almas del embudo están a 45°) |
| Tapa | plana, con la pestaña hacia arriba | No |
| Carro | plano, como viene | No |

Capa 0,2 mm · 3 perímetros · 15–20 % de relleno. **Mejor PLA blanco o gris claro**: por dentro refleja la luz del flash y la vuelve más pareja (menos brillos en la moneda).

## Tornillería
- 4 tornillos **M3 × 16** + 4 tuercas M3
- 2 bridas plásticas (amarran la placa MB al carro)

## Armado
1. Mete las 4 tuercas M3 en las ranuras de arriba de los bloques del carro.
2. Pon la ESP32-CAM con la **cámara hacia abajo** dentro del bolsillo, con la placa MB encima y el **USB hacia el lado abierto** del bolsillo (hacia la entrada de monedas). Amárrala con las bridas.
3. Mete el carro por arriba del túnel y atornilla por fuera en las ranuras, a la altura de la marca de 6–7 cm.
4. Pasa el cable USB por el hueco de la tapa y cierra la tapa.
5. Pon el túnel sobre la banda, en el tramo recto, con el embudo hacia donde **llegan** las monedas.

## Ajuste fino
- Abre la interfaz y pasa monedas: si se ven **pequeñas** en el recuadro, baja el carro; si **no caben**, súbelo. Aprieta los tornillos cuando la confianza salga alta y estable.
- Si el flash saca brillos, pega encima del LED un pedazo de papel mantequilla o de cinta mate como difusor.
- El fondo nuevo es el cuero negro de la banda. Si la confianza baja mucho, toma unas 20 fotos de la banda vacía con la cámara ya montada, agrégalas a `vision/referencias/fondos/` y vuelve a entrenar.
