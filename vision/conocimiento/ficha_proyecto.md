# Ficha del proyecto (estado actual, 24 de noviembre de 2026)

> Fuente principal de JARVIS. Si algo de aqui contradice al README del parcial
> (README_parcial_segundo_corte.md, escrito antes), vale lo de esta ficha: el
> proyecto avanzo despues del parcial (detector de varias monedas, 4 servos, ESP32-S3,
> carrito integrado, interfaz con JARVIS).

## 1. Identidad del proyecto
- Nombre: **Sistema de Logistica de Monedas Inteligentes**.
- Universidad Militar Nueva Granada (UMNG), Ingenieria Mecatronica, campus Cajica, quinto semestre.
- Asignatura: Micros y Laboratorio (microcontroladores). **Grupo 3**.
- Integrantes: **Faber Alexander Rodriguez Hernandez**, **David Felipe Farfan Quiroz** y **Kevin Philip Castelblanco Ramirez**.
- Elemento diferencial asignado al grupo: un **agente de IA conversacional tipo JARVIS** que supervisa y comanda el sistema.
- Repositorio en GitHub: `Parcial_Monedas` (cuenta faberx10).
- Objetivo general (enunciado del curso): sistema logistico de monedas con ESP32, con estructuras mecanicas y electronicas
  propias, conexion inalambrica a un aplicativo web, contador de monedas, modulo de transporte y embalaje, recoleccion de
  los vasos con monedas que siga una trayectoria con tres obstaculos hasta una meta, dashboard con seguimiento de la ruta,
  valor, peso y cantidad de monedas, y un chatbot asistente que exponga los datos del proyecto.

## 2. Arquitectura general (como funciona hoy)
Cada modulo tiene su propio microcontrolador y todos se comunican por **WiFi en la misma red** (el hotspot del celular del grupo).
El trabajo pesado (vision artificial, conteo, interfaz y JARVIS) corre en el **PC**; las ESP32 se encargan del tiempo real.

Recorrido de una moneda:
1. Se pone la moneda en la **banda transportadora** (motor DC controlado por la ESP32-S3).
2. Pasa bajo la **ESP32-CAM** (sensor OV5640), montada en un soporte impreso en 3D sobre la banda.
3. La camara manda video **MJPEG por WiFi** al PC (`http://IP:81/stream`).
4. En el PC, el **detector YOLO11n** reconoce todas las monedas de cada cuadro (9 clases) y el **contador** sigue cada moneda
   y la cuenta una sola vez.
5. Al contar una moneda, el PC avisa a la **ESP32-S3** por HTTP: `GET http://banda-s3.local/moneda?v=500&d=12`.
6. La S3 espera el **retardo** de ese servo (lo que tarda la moneda en llegar a su paleta: 3 s servos 1 y 2, 5 s servos 3 y 4),
   gira la paleta a **DESVIO** durante 1,5 s y la regresa a **REPOSO**. La moneda cae a su **vaso**.
7. Los vasos se llevan en el **carrito de transporte** (se pegan con imanes al frente). El carrito se maneja desde la
   misma interfaz del PC.
8. La interfaz web (FastAPI) muestra todo en vivo y **JARVIS** responde preguntas, da avisos y ejecuta ordenes seguras.

Direcciones en la red (pueden cambiar si cambia la red):
- ESP32-CAM: IP fija en `config.py` (ESP32_IP, ultima usada 10.193.83.226). Video en el puerto 81.
- ESP32-S3 (banda + servos): `http://banda-s3.local` (mDNS) o su IP.
- Carrito: `http://carrito-g3.local` (mDNS) o su IP; ademas conserva su red propia `Carrito_G3` en `http://192.168.4.1`.
- Interfaz: `http://localhost:8000` en el PC (o `http://IP-del-PC:8000` desde el celular).

## 3. Modulo de reconocimiento: ESP32-CAM
- Placa **ESP32-CAM AI-Thinker** con sensor **OV5640** (lente normal, no ojo de pez) y su placa programadora **ESP32-CAM-MB**.
- Firmware `arduino/ESP32CAM_Monedas_v2/ESP32CAM_Monedas_v2.ino` (Arduino IDE 2.3.11, nucleo esp32 de Espressif).
  - Resolucion **SVGA 800x600**, JPEG calidad 8 (menos artefactos en el relieve), 2 buffers en PSRAM, siempre el cuadro mas nuevo.
  - Servidor: `/` pagina, `:81/stream` video MJPEG, `/capture` foto, `/control?var=..&val=..` ajustes, `/status` estado JSON.
  - Para que no se caliente: CPU a 160 MHz, limite de 12 fps y potencia WiFi de 15 dBm. Ademas se le puso un **disipador**.
  - **Flash siempre apagado**: dentro de la caja hay **LEDs de ambiente** que iluminan mejor y parejo.
  - Problema resuelto: el flash se apagaba solo a los 2 s porque compartia el temporizador LEDC con el reloj XCLK de la camara;
    se le dio un temporizador y canal propios (timer 3, canal 7). Luego se decidio dejarlo apagado.
  - Monitor Serie a **115200 baudios** (a 9600 salen caracteres raros).
  - Se probo subir la resolucion por codigo (`framesize`) y no mejoro: el limite real era el **enfoque del lente**.
- **Soporte de la camara**: diseno propio en CAD (CadQuery, exportado a STEP para SolidWorks y STL para imprimir), impreso en
  **PLA** (impresora con cama de 256 x 256 mm). Es un tunel que cubre la banda con tapa y un carro donde va la ESP32-CAM con su
  placa MB mirando hacia abajo; se acomoda a la estructura de MDF de la banda.

## 4. Vision en el PC (carpeta `vision/`)
- Python 3.12 en el entorno conda `monedas_g3`; ultralytics (YOLO11), PyTorch, OpenCV, NumPy, FastAPI + uvicorn, requests.
- **Detector YOLO11n** (deteccion de objetos, no clasificacion): reconoce **varias monedas a la vez** en la imagen.
- **9 clases**: $1.000 nueva, $500 nueva, $500 antigua, $200 nueva, $200 antigua, $100 nueva, $100 antigua, $50 nueva, $50 antigua.
  (La de $1.000 solo existe en la familia nueva.)
- Proceso de entrenamiento:
  1. `01_capturar_deteccion.py`: fotos tomadas con la MISMA ESP32-CAM ya montada en la banda. Las cajas de cada moneda se
     **etiquetan solas** por sustraccion de fondo: 30 fotos de la banda vacia (tecla F) forman un fondo de referencia (mediana);
     se detecta la zona de la banda con k-means, se iguala la exposicion automatica y lo que cambia contra el fondo es moneda.
     Filtros: diametro 80 a 420 px, redondez >= 0,78, y se descartan reflejos en las paredes del embudo.
     Se tomaron unas **609 fotos** (al menos 60 por moneda; de $50 se etiquetaron ~140-155 monedas por clase).
  2. `02_preparar_deteccion.py`: separa 85 % entrenamiento / 15 % validacion por moneda y genera **1.800 composiciones
     sinteticas** pegando 2 a 6 monedas recortadas (de distintas denominaciones, algunas casi tocandose) sobre fotos de la
     banda vacia, para que aprenda a ver monedas mezcladas aunque las fotos se tomaron de una denominacion a la vez.
  3. `03_entrenar_deteccion.py`: el modelo final se entreno en la **GPU** del PC: YOLO11n preentrenado, **60 epocas a 640 px**,
     lote de 16, paciencia 15, unos **32 minutos**. Dataset final: 2.341 imagenes de entrenamiento y 323 de validacion
     (fotos reales + composiciones + banda vacia). Sin GPU el script usa un modo liviano (35 epocas a 480 px).
     **Resultado en validacion (ultima epoca): precision 0,9997, recall 1,0, mAP50 0,995 y mAP50-95 0,993.**
     Ojo: la validacion mezcla fotos reales apartadas y composiciones sinteticas con la misma camara e iluminacion, por eso
     los valores son tan altos; la prueba real es el funcionamiento en vivo en la banda, que fue correcto.
     El modelo queda en `vision/modelos/monedas_det.pt`; las curvas y la matriz de confusion en `vision/runs/detector/`.
- **Contador de varias monedas** (`contador_multi.py`): cada deteccion se une a la moneda mas cercana del cuadro anterior
  (seguimiento); cada moneda acumula **votos por clase** ponderados por la confianza (un cuadro dudoso no cambia la
  denominacion); se cuenta **una sola vez** cuando se vio en 4 cuadros (FRAMES_CONFIRMAR) y al menos una vez **completa**
  (sin tocar el borde). Una moneda cortada por el borde vota con peso 0,3. Se olvida tras 10 cuadros sin verla.
  Umbral de confianza del detector: 0,60.
- **Peso**: se calcula multiplicando cada moneda contada por su masa aproximada (ver seccion 10).
- Version anterior (la del parcial): clasificador YOLO11 de 8 clases (7 monedas + "sin moneda") entrenado con fotos de
  celular; 99,3 % (417/420) en la prueba con fotos apartadas. Archivos `00_..`, `01_capturar_dataset.py`, `02_entrenar.py`,
  `03_interfaz.py`, `contador.py`. Se reemplazo por el detector porque solo veia una moneda a la vez.

## 5. Modulo de clasificacion: ESP32-S3 (banda + 4 servos)
- Firmware `arduino/BandaServos_S3/BandaServos_S3.ino` (Arduino IDE, placa "ESP32S3 Dev Module").
- **Motor DC de la banda**: GPIO 4 -> resistencia de 150 ohm -> base de un transistor **TIP31C**; colector al motor (-) y al
  anodo de un diodo **1N4007** (rueda libre); emisor a GND comun. PWM de 1 kHz y 10 bits. Arranca con un empujon de 150 ms
  al 100 % y queda al **50 %** de velocidad. La velocidad se cambia desde la pagina de la S3 o desde la interfaz/JARVIS.
- **4 servos SG90** con paleta, uno por vaso:
  | Servo | GPIO | Vaso | Reposo | Desvio | Retardo |
  |---|---|---|---|---|---|
  | 1 | 5 | $1.000 y $500 | 47 grados | 120 grados | 3 s |
  | 2 | 6 | $200 | 180 grados | 116 grados | 3 s |
  | 3 | 7 | $100 | 90 grados | 50 grados | 5 s |
  | 4 | 15 | $50 | 0 grados | 50 grados | 5 s |
  - PWM de 50 Hz con 14 bits; pulso de 500 us (0 grados) a 2400 us (180 grados). Tiempo en desvio: 1500 ms.
  - Los angulos se calibraron con una pagina web propia (sliders por servo, marcar reposo/desvio, probar, guardar en la placa).
  - Varias monedas seguidas se ponen en una **cola** (hasta 24) sin bloquear; si llega otra moneda mientras la paleta esta
    desviada, el desvio se alarga. El PC manda cuantos ms ya pasaron (`d`) y la S3 los descuenta del retardo.
  - Valores guardados en memoria no volatil (Preferences/NVS). Al encender, los servos van a reposo de a uno (pico de corriente).
- Alimentacion: los servos van con una **fuente de 5 V aparte** (>= 2 A), GND comun con la S3 y un condensador de 470-1000 uF.
- Red: entra al WiFi del router como `banda-s3.local`; si no puede, crea su red `Servos-Monedas` (clave 12345678) en 192.168.4.1.
- En el PC, `servos_s3.py` manda cada moneda contada en un hilo aparte (si la S3 no responde, el conteo sigue igual;
  descarta avisos de mas de 2 s porque llegarian tarde a la paleta).

## 6. Vasos y banda
- **4 vasos** pequenos impresos en PLA (radio ~3 cm, alto ~5 cm): vaso 1 = $1.000 y $500, vaso 2 = $200, vaso 3 = $100,
  vaso 4 = $50 (cada vaso recibe la version nueva y la antigua).
- **Banda transportadora**: estructura de **MDF de 3 mm** con banda de **cuerina**, ancho exterior ~9,5 cm; paredes laterales
  con ranuras rectangulares de 3,5 cm separadas 9 cm. Antes se habia simulado en L con brazos de 3 GDL; se cambio a banda recta
  con servos de paleta (decision tomada con la simulacion en PyBullet).

## 7. Carrito de transporte 4WD
- **ESP32 DevKit V1** (30 pines) + puente H **L298N** + chasis 4WD de acrilico de 2 pisos con 4 motorreductores **TT 1:48**.
- Pines: D13 = ENA (PWM izquierda), D27 = IN1, D26 = IN2, D25 = IN3, D33 = IN4, D32 = ENB (PWM derecha). Jumpers ENA/ENB
  retirados para controlar velocidad por PWM. Dos motores en paralelo por lado (control diferencial, tipo tanque).
- Alimentacion: bateria Ni-MH **7,2 V 500 mAh** para los motores y **power bank** aparte para la ESP32 (con la bateria sola
  la ESP32 se reiniciaba al arrancar los motores); tierra comun obligatoria.
- Firmware (PlatformIO, `carrito_firmware_main.cpp`): ordenes `GET /cmd?d=F|B|L|R|FL|FR|BL|BR|S|X&s=0-100`
  (adelante, atras, giro izquierda/derecha en el sitio, curvas, soltar, parar ya) y `/ping`.
  - **Parada de seguridad**: si pasan 400 ms sin ordenes, se detiene solo.
  - **Rampas** de aceleracion (sube suave, frena mas rapido) para no tumbar los vasos.
  - Zona muerta: el PWM nunca baja de 90/255 cuando debe moverse. Giros al 70 %, curvas con un lado al 35 %.
  - Red: su red propia `Carrito_G3` (celular, http://192.168.4.1) **y** el WiFi del router como `carrito-g3.local`
    (modo AP + estacion) para manejarlo desde la interfaz del PC.
- En la interfaz: flechas en pantalla o teclado (flechas/WASD, espacio = parar). La pagina repite la orden cada 100 ms
  mientras se mantiene el boton; el PC (`carrito.py`) la reenvia y si la pagina deja de mandar por 0,35 s frena el carrito.
- Lleva **imanes al frente** para agarrar hasta 2 vasos y en el segundo piso la **base del dron** (solo lo transporta).
- Se simulo en **Wokwi** (LEDs en lugar del L298N + analizador logico). En su entrega funciono y obtuvo **5,0**.
- JARVIS **no mueve el carrito** por voz (decision de seguridad); solo puede detenerlo. Se maneja con los botones/teclado.

## 8. Dron
- Diseno y simulacion: PyBullet con URDF propio (`dron_monedas.urdf`) y control **PID en cascada**
  (posicion -> velocidad -> angulo -> empuje; altura PID 12/3/5; mezclador en X). Mision simulada: despegue a 1,20 m,
  1 m hasta el punto B, entrega, retorno y aterrizaje en 14,5 s; error de entrega 3,3 cm.
- Diseno original: ESP32-S3 SuperMini, 4 motores coreless **8520** con helice de 75 mm, MOSFET AO3400 + diodo 1N5819,
  MPU6050, VL53L0X (altura), IR FC-51 (obstaculos), MT3608, TP4056, LiPo 1S 450 mAh, chasis PLA; T/W = 2,28 con 10 g de carga;
  costo $170.200 COP (plan mixto con 15 % de contingencia, tope de $200.000). Detalle en `presupuesto_dron.md`.
- **Lo que se construyo**: placa **ESP32-C3 SuperMini** (en lugar de la S3), motores **615** (6 mm; no se pudieron comprar los
  8520), bateria de 500 mAh y un **chasis mas ligero** impreso en 3D para que vuele con esos motores.
- Mision actual: el dron **no lleva carga**; vuela ~1,20 m de altura y ~1 m en horizontal, detecta el obstaculo y lo reporta
  a JARVIS. Las monedas viajan en los vasos del carrito. Aun **no envia datos en vivo** a la interfaz (siguiente fase).
- Limitacion conocida: sin sensor de flujo optico (PMW3901, descartado por costo) el dron deriva despacio en horizontal.

## 9. Interfaz web y JARVIS
- `vision/04_interfaz.py`: servidor FastAPI en el puerto 8000. Hilo de camara -> detector -> contador -> avisos a la S3.
  WebSocket con el estado (cada 0,1 s), video anotado MJPEG, control del carrito, bitacora de eventos y JARVIS.
- Pantalla estilo HUD (Iron Man): JARVIS al centro como una **red neuronal** animada; a la izquierda la camara y las monedas;
  a la derecha el carrito, los servos y la banda; abajo los contadores por moneda, el historial y la bitacora.
- **JARVIS** (`vision/jarvis.py`):
  - Cerebro: **Gemini API** de Google (plan gratuito, modelo gemini-3.5-flash; si se acaba la cuota pasa a otro modelo gratis).
    La clave se guarda fuera del proyecto (carpeta del usuario `.jarvis_g3`) para que no se suba a GitHub.
  - En cada pregunta recibe el **estado en vivo** (monedas, valor, peso, servos, banda, carrito, camara, bitacora) y los
    fragmentos de **documentacion y codigo** mas relevantes de la carpeta `vision/conocimiento` y del propio codigo.
  - **Voz**: boton de microfono (reconocimiento de voz de Chrome/Edge en espanol) y respuesta hablada.
  - **Ordenes seguras**: reiniciar el conteo, parar/reanudar/cambiar la velocidad de la banda, probar un servo, servos a
    reposo, parar el carrito, silenciar o activar avisos. No mueve el carrito.
  - **Avisos**: anuncia monedas detectadas y cambios de conexion de los modulos.
  - Sin internet responde lo basico (conteo, carrito, servos, banda) con reglas locales.

## 10. Monedas colombianas: valor y masa aproximada
Masas aproximadas calculadas con la guia de empaque de moneda del Banco de la Republica (peso de bolsa / cantidad):
| Moneda | Masa aprox. | Vaso |
|---|---|---|
| $1.000 nueva | 9,32 g | 1 |
| $500 nueva | 7,14 g | 1 |
| $500 antigua | 7,11 g | 1 |
| $200 nueva | 4,61 g | 2 |
| $200 antigua | 7,10 g | 2 |
| $100 nueva | 3,34 g | 3 |
| $100 antigua | 5,25 g | 3 |
| $50 nueva | 2,00 g | 4 |
| $50 antigua | 4,50 g | 4 |
Las nuevas son la familia de 2012 (biodiversidad); la de $500 y la de $1.000 nuevas son bimetalicas.

## 11. Problemas que se resolvieron (utiles para la sustentacion)
| Problema | Causa | Solucion |
|---|---|---|
| ESP32-CAM muy caliente | WiFi y CPU al maximo | Disipador, CPU a 160 MHz, 12 fps y WiFi a 15 dBm |
| El flash se apagaba a los 2 s | Compartia temporizador LEDC con la camara | Temporizador/canal propios; despues flash apagado + LEDs de ambiente |
| Caracteres raros en el Monitor Serie | Monitor a 9600 y la placa a 115200 | Poner 115200 baudios |
| El PC no conectaba con la camara | Estaban en redes distintas | Todos en el mismo WiFi; IP del Monitor Serie en config.py |
| Monedas "fantasma" al capturar con la banda vacia | Fondo viejo y exposicion automatica | Fondo nuevo con F, zona de banda e igualacion de exposicion |
| Cajas falsas en fotos de $50 | Reflejos en la pared del embudo | Filtro que exige que la caja este dentro de la banda y sea casi cuadrada |
| Servo 1 en el mismo pin del motor | Ambos en GPIO 4 | Servos a GPIO 5, 6, 7 y 15 |
| El PC no podia hablar con el carrito | El carrito solo tenia su red propia | Carrito en modo AP + estacion (entra al mismo WiFi) |
| Fotos borrosas | Enfoque del lente, no resolucion | Ajustar el lente girandolo; subir la resolucion no ayudo |
| Reinicios del carrito al arrancar | Caida de tension de la bateria | ESP32 con power bank aparte y tierra comun |

## 12. Software y herramientas
- Arduino IDE 2.3.11 (ESP32-CAM y ESP32-S3), VS Code + PlatformIO (carrito), Wokwi (simulacion del carrito).
- Miniconda, Python 3.12, PyBullet (simulacion de la planta y del dron), ultralytics/YOLO11, PyTorch, OpenCV, FastAPI, uvicorn.
- SolidWorks y CadQuery (diseno 3D), impresion 3D en PLA.
- Gemini API (JARVIS), reconocimiento y sintesis de voz del navegador.

## 13. Pendientes / siguientes pasos
- Telemetria en vivo del dron hacia la interfaz y JARVIS.
- Trayectoria con los tres obstaculos hasta la meta y seguimiento de la ruta en el dashboard.
- Dispensador automatico de monedas al inicio de la banda.
