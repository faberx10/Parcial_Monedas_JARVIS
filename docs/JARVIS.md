# J.A.R.V.I.S. — asistente del proyecto (Grupo 3)

La interfaz ahora abre con JARVIS al centro: `python 04_interfaz.py` → **http://localhost:8000**
(la interfaz anterior sigue en http://localhost:8000/clasico).

## 1. Conectar el cerebro (una sola vez)
1. Entra a **https://aistudio.google.com/apikey** con una cuenta de Google y pulsa *Create API key*.
2. Abre la interfaz **en el PC** (localhost) y pega la clave en el recuadro amarillo del panel de JARVIS.
3. Queda guardada en `C:\Users\<usuario>\.jarvis_g3\gemini_key.txt`, fuera del proyecto, así que no se sube a GitHub.
   (También sirve la variable de entorno `GEMINI_API_KEY`.)

Usa el plan **gratuito** de Gemini. Si un modelo se queda sin cuota, JARVIS pasa solo a otro modelo gratis.
Ojo: en el plan gratuito Google puede usar lo que se le envía (preguntas, estado y fragmentos del código) para mejorar
sus productos. Las claves de WiFi se borran antes de enviar cualquier archivo.

## 2. Hablar con JARVIS
- Botón del **micrófono** (o tecla **J**): hablas, y JARVIS responde en texto y en voz alta.
- Funciona en **Google Chrome** o **Microsoft Edge**, solo desde el PC de la interfaz (localhost) y con internet.
  La primera vez el navegador pide permiso para el micrófono.
- Voz: en **Edge** suena mejor (por ejemplo "Gonzalo, Colombia"). Se elige en el selector de voces debajo del chat.
- **Esc** calla a JARVIS. "Nueva conversación" borra lo que recuerda de la charla.

## 3. Qué sabe
- **En vivo:** monedas, valor, peso, monedas en vista, cada servo (ángulo, si está desviando, monedas enviadas),
  la banda, el carrito (dirección actual y último movimiento), las conexiones y la bitácora de eventos.
- **Del proyecto:** la ficha `vision/conocimiento/ficha_proyecto.md` (estado actual: módulos, pines, piezas,
  problemas resueltos), los README del parcial y del carrito, el presupuesto del dron, las simulaciones y todo el
  código (`vision/*.py`, `arduino/*/*.ino`, firmware del carrito).
- **Agregarle conocimiento:** copia archivos `.md` o `.txt` (informe, lista de materiales, notas) en
  `vision/conocimiento/` y reinicia la interfaz. Si algo cambia en el proyecto, actualiza `ficha_proyecto.md`.

## 4. Órdenes que acepta (por voz o texto)
Reiniciar el conteo · parar / reanudar la banda · "banda al 40 por ciento" · "prueba el servo 2" ·
servos a reposo · parar el carrito · silenciar / activar avisos.
**No mueve el carrito** (por seguridad se maneja con el panel o el teclado).

## 5. Avisos
Anuncia cada moneda contada ("500 pesos") y si se cae o vuelve la cámara, la S3 o el carrito.
Se apagan con el interruptor "Avisos hablados" o diciendo "silencia los avisos".

## 6. Sin internet o sin clave
Responde lo básico con reglas locales (conteo, peso, carrito, servos, banda, cámara) y ejecuta las órdenes.

## Archivos nuevos
| Archivo | Qué hace |
|---|---|
| `vision/jarvis.py` | Cerebro: busca en la documentación y el código, arma el estado en vivo, habla con Gemini, ejecuta órdenes |
| `vision/bitacora.py` | Registro de eventos (monedas, servos, carrito, conexiones) |
| `vision/datos_proyecto.py` | Masa de cada moneda, vaso de cada denominación, nombres de direcciones |
| `vision/static/jarvis.html` | Pantalla HUD con el núcleo neuronal, voz y paneles |
| `vision/conocimiento/` | Ficha del proyecto y documentos que estudia JARVIS |
