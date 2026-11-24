> **Nota:** guía de la versión del parcial (clasificador de una moneda, `03_interfaz.py`). Para la versión final usa el
> paso a paso del [README principal](../README.md#5-paso-a-paso-para-replicarlo).

# Reconocimiento de monedas con ESP32-CAM: paso a paso (Grupo 3)

```
ESP32-CAM (arduino/ESP32CAM_Monedas) --WiFi, video--> PC (vision/03_interfaz.py, modelo YOLO) --> http://localhost:8000
```
La ESP32-CAM solo manda el video; el reconocimiento lo hace el PC con `vision/modelos/monedas.pt`.

---

## A. Arduino IDE 2.3.11: instalar las ESP32 (una sola vez)

1. **Archivo → Preferencias**. En **"URLs adicionales del gestor de placas"** pega:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
   y dale **OK**.
2. Abre el **Gestor de placas** (segundo icono de la barra izquierda, o *Herramientas → Placa → Gestor de placas*).
   Busca **esp32** e instala **"esp32 by Espressif Systems"** (la versión más nueva).
   No instales "Arduino ESP32 Boards", que es otro paquete. Tarda varios minutos.
3. Conecta la ESP32-CAM montada en la placa **ESP32-CAM-MB** con un cable USB **de datos**.
   Si no aparece ningún puerto COM, instala el driver **CH340** (CH341SER para Windows) y vuelve a conectar.

## B. Subir el código a la ESP32-CAM

1. Abre `arduino/ESP32CAM_Monedas/ESP32CAM_Monedas.ino`.
2. Cambia estas dos líneas por tu red (tiene que ser **2,4 GHz**; si usas el celular como punto de acceso, activa "Maximizar compatibilidad" o la banda de 2,4 GHz):
   ```cpp
   const char *WIFI_SSID = "TU_RED_WIFI";
   const char *WIFI_PASS = "TU_CLAVE";
   ```
3. **Herramientas → Placa → esp32 → "AI Thinker ESP32-CAM"**.
   **Herramientas → Puerto → COMx** (el que aparece al conectar la placa).
4. Dale **Subir** (flecha →). Cuando en la consola aparezca `Connecting......`:
   **mantén presionado IO0**, toca **RST**, y suelta IO0.
   (Algunas placas MB lo hacen solas; si sube sin hacer esto, perfecto.)
5. Cuando diga `Hard resetting via RTS pin...`, presiona **RST** una vez.
6. Abre el **Monitor serie** (lupa arriba a la derecha) a **115200 baudios** y presiona RST. Debe salir:
   ```
   Sensor detectado PID=0x5640
   WiFi conectado.
     Pagina de prueba : http://192.168.x.x
     >>> En vision/config.py pon:  ESP32_IP = "192.168.x.x"
   ```
   **Anota esa IP.**
   Si no logra conectarse, crea su propia red **MONEDAS-G3** (clave `monedas123`): conecta el PC a esa red y usa la IP `192.168.4.1`.
7. **Prueba**: abre `http://LA_IP` en el navegador. Verás una foto que se actualiza cada segundo, con botones de flash y de voltear la imagen.
   Úsala para ubicar la cámara en el soporte y revisar la luz. Luego **cierra la pestaña** para que el video al PC vaya más fluido.

## C. PC: preparar Python (una sola vez)

En el **Anaconda Prompt** (o Miniconda):
```
conda create -n monedas_g3 python=3.11 -y
conda activate monedas_g3
cd RUTA\Monedas_ESP32CAM\vision
pip install torch torchvision
pip install -r requirements_vision.txt
```
Con `torch` normal (CPU) va bien: el modelo es pequeño. Si quieres usar la GPU NVIDIA, cambia la tercera línea por el comando CUDA de https://pytorch.org/get-started/locally/.

## D. Reconocer monedas

1. En `vision/config.py` cambia la IP por la que salió en el Monitor serie:
   ```python
   ESP32_IP = "192.168.x.x"
   ```
2. Prueba sin cámara (opcional): `python 03_interfaz.py --demo` → abre http://localhost:8000 → Ctrl+C para cerrar.
3. Con la cámara:
   ```
   conda activate monedas_g3
   cd RUTA\Monedas_ESP32CAM\vision
   python 03_interfaz.py
   ```
   Abre **http://localhost:8000**. Pasa una moneda bajo la cámara:
   - El círculo se pone **dorado** mientras confirma y **verde** cuando la cuenta.
   - Suma la moneda al total y la muestra en "Últimas monedas registradas".
   - El contador se rearma cuando no hay moneda, así no cuenta dos veces la misma.

## E. Ajustes (vision/config.py)

| Qué pasa | Qué cambiar |
|---|---|
| Imagen muy oscura (dentro de la caja no entra luz) | Sube `led_intensity` (50–80) |
| Moneda quemada / con brillos blancos | Baja `led_intensity` (15–20) y pega papel mantequilla sobre el LED |
| Imagen al revés | `vflip`: 1 ↔ 0 |
| Cuenta monedas equivocadas | Sube `UMBRAL_CONFIANZA` (0.90) |
| Le cuesta aceptar monedas correctas | Baja `UMBRAL_CONFIANZA` (0.75) o ajusta la altura del carro |

## F. Problemas comunes

| Mensaje / síntoma | Solución |
|---|---|
| No aparece el puerto COM | Cable de datos (no solo de carga) y driver CH340 |
| `Failed to connect ... Wrong boot mode` | Repite el paso B.4 (IO0 + RST cuando salga `Connecting...`) |
| `Error iniciando la camara: 0x105` o `0x106` | Revisa que el cable flex de la cámara esté bien metido y cerrado; aliméntala con un cargador de 5 V / 2 A |
| `Brownout detector was triggered` | Alimentación débil: cargador de pared, no un puerto USB del PC sin fuerza |
| "sin conexion... reintentando" en el PC | IP equivocada en `config.py`, o el PC y la ESP32 en redes distintas |
| El video va lento o se congela | Cierra la página de la ESP32 en el navegador y acércala al router |
