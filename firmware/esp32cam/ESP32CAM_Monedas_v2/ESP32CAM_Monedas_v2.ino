/*
  ESP32CAM_Monedas_v2.ino  -  Grupo 3, Sistema de Logistica de Monedas Inteligentes (UMNG)
  -------------------------------------------------------------------------------------
  Camara para el reconocimiento de monedas. La ESP32-CAM solo transmite video;
  el PC (carpeta vision/, 03_interfaz.py) corre el modelo YOLO y cuenta las monedas.

    http://IP/            pagina de prueba (foto cada segundo, para enfocar y ubicar)
    http://IP/capture     una foto JPG
    http://IP/control?var=quality&val=10   ajustes (los usa camara.py al arrancar)
    http://IP/status      estado en JSON
    http://IP:81/stream   video MJPEG  -> lo lee el PC (config.STREAM_URL)

  Placa en Arduino IDE: "AI Thinker ESP32-CAM"  (paquete esp32 de Espressif)
  Si no se conecta al WiFi en 20 s crea su propia red: MONEDAS-G3 / monedas123
  (en ese caso la IP es 192.168.4.1).
*/
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "driver/ledc.h"

// ===================== CAMBIA ESTO =====================
const char *WIFI_SSID = "TU_RED_WIFI";
const char *WIFI_PASS = "";
// =======================================================
const char *AP_SSID = "MONEDAS-G3";
const char *AP_PASS = "monedas123";      // minimo 8 caracteres

// ---- Ajustes de temperatura y luz ----
const int LED_INICIAL = 0;         // flash APAGADO: la caja usa LEDs externas
const int LED_MAXIMO = 0;          // 0 = el flash nunca se enciende (ni desde el PC ni desde la pagina)
const int FPS_MAX = 12;            // el PC no necesita mas; menos fps = menos calor y WiFi
const int CPU_MHZ = 160;           // 240 por defecto; 160 calienta menos y alcanza de sobra

// ---- Pines AI-Thinker ESP32-CAM ----
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define LED_FLASH 4

httpd_handle_t web_httpd = NULL;
httpd_handle_t stream_httpd = NULL;
int led_duty = 0;   // 0..255

// El flash usa un temporizador PROPIO (grupo low-speed, timer 3, canal 7).
// La camara usa el timer 0 / canal 0 para su reloj XCLK: si se comparten,
// el LED se apaga solo o recibe el reloj de 20 MHz (se calienta).
void iniciarFlash() {
  ledc_timer_config_t t = {};
  t.speed_mode = LEDC_LOW_SPEED_MODE;
  t.duty_resolution = LEDC_TIMER_8_BIT;
  t.timer_num = LEDC_TIMER_3;
  t.freq_hz = 5000;
  t.clk_cfg = LEDC_AUTO_CLK;
  ledc_timer_config(&t);
  ledc_channel_config_t c = {};
  c.gpio_num = LED_FLASH;
  c.speed_mode = LEDC_LOW_SPEED_MODE;
  c.channel = LEDC_CHANNEL_7;
  c.timer_sel = LEDC_TIMER_3;
  c.duty = 0;
  c.hpoint = 0;
  ledc_channel_config(&c);
}

void setFlash(int duty) {
  led_duty = constrain(duty, 0, LED_MAXIMO);
  ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_7, led_duty);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_7);
}

// --------------------------------------------------------------------
// Video MJPEG (puerto 81)
// --------------------------------------------------------------------
#define BOUNDARY "123456789000000000000987654321"
static const char *STREAM_TYPE = "multipart/x-mixed-replace;boundary=" BOUNDARY;
static const char *STREAM_SEP = "\r\n--" BOUNDARY "\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t *req) {
  char part[64];
  const int64_t periodo_us = 1000000LL / FPS_MAX;
  int64_t ultimo = 0;
  esp_err_t res = httpd_resp_set_type(req, STREAM_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  while (true) {
    int64_t espera = periodo_us - (esp_timer_get_time() - ultimo);   // limita los fps
    if (espera > 0) vTaskDelay(pdMS_TO_TICKS(espera / 1000 + 1));
    ultimo = esp_timer_get_time();
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { Serial.println("Fallo al capturar"); res = ESP_FAIL; break; }
    size_t hlen = snprintf(part, sizeof(part), STREAM_PART, fb->len);
    res = httpd_resp_send_chunk(req, STREAM_SEP, strlen(STREAM_SEP));
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, part, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (res != ESP_OK) break;   // el PC cerro la conexion
  }
  return res;
}

// --------------------------------------------------------------------
// Pagina, foto, ajustes y estado (puerto 80)
// --------------------------------------------------------------------
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t control_handler(httpd_req_t *req) {
  char query[96], var[32], val[16];
  if (httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK ||
      httpd_query_key_value(query, "var", var, sizeof(var)) != ESP_OK ||
      httpd_query_key_value(query, "val", val, sizeof(val)) != ESP_OK) {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }
  int v = atoi(val);
  sensor_t *s = esp_camera_sensor_get();
  int r = 0;
  if (!strcmp(var, "framesize")) r = s->set_framesize(s, (framesize_t)v);
  else if (!strcmp(var, "quality")) r = s->set_quality(s, v);
  else if (!strcmp(var, "brightness")) r = s->set_brightness(s, v);
  else if (!strcmp(var, "contrast")) r = s->set_contrast(s, v);
  else if (!strcmp(var, "saturation")) r = s->set_saturation(s, v);
  else if (!strcmp(var, "sharpness")) r = s->set_sharpness(s, v);
  else if (!strcmp(var, "vflip")) r = s->set_vflip(s, v);
  else if (!strcmp(var, "hmirror")) r = s->set_hmirror(s, v);
  else if (!strcmp(var, "awb")) r = s->set_whitebal(s, v);
  else if (!strcmp(var, "aec")) r = s->set_exposure_ctrl(s, v);
  else if (!strcmp(var, "agc")) r = s->set_gain_ctrl(s, v);
  else if (!strcmp(var, "ae_level")) r = s->set_ae_level(s, v);
  else if (!strcmp(var, "led_intensity")) setFlash(v);
  else r = -1;
  if (r < 0) { httpd_resp_send_500(req); return ESP_FAIL; }
  Serial.printf("Ajuste %s = %d\n", var, v);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, "OK", 2);
}

static esp_err_t status_handler(httpd_req_t *req) {
  sensor_t *s = esp_camera_sensor_get();
  char json[200];
  snprintf(json, sizeof(json),
           "{\"framesize\":%d,\"quality\":%d,\"vflip\":%d,\"hmirror\":%d,"
           "\"led_intensity\":%d,\"rssi\":%d,\"psram\":%u}",
           s->status.framesize, s->status.quality, s->status.vflip, s->status.hmirror,
           led_duty, (int)WiFi.RSSI(), (unsigned)ESP.getFreePsram());
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json, strlen(json));
}

static const char PAGINA[] = R"HTML(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ESP32-CAM Monedas</title>
<style>body{background:#0b1218;color:#e6eef2;font-family:sans-serif;text-align:center;margin:0;padding:16px}
img{max-width:100%;border-radius:10px;border:2px solid #22e0c0}button{background:#22e0c0;border:0;
border-radius:8px;padding:10px 16px;margin:4px;font-weight:bold}small{color:#8fc9cc}</style></head><body>
<h2>ESP32-CAM &middot; Monedas G3</h2><img id="f" src="/capture"><br>
<button onclick="fetch('/control?var=vflip&val='+(v^=1))">Voltear</button>
<p><small>Foto cada segundo, solo para enfocar y ubicar la camara.<br>
Video para el PC: puerto 81, ruta /stream</small></p>
<script>let v=1;setInterval(()=>{document.getElementById('f').src='/capture?t='+Date.now()},1000)</script>
</body></html>)HTML";

static esp_err_t index_handler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, PAGINA, strlen(PAGINA));
}

void iniciarServidores() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.max_uri_handlers = 8;
  httpd_uri_t u_index = {"/", HTTP_GET, index_handler, NULL};
  httpd_uri_t u_cap = {"/capture", HTTP_GET, capture_handler, NULL};
  httpd_uri_t u_ctl = {"/control", HTTP_GET, control_handler, NULL};
  httpd_uri_t u_st = {"/status", HTTP_GET, status_handler, NULL};
  if (httpd_start(&web_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(web_httpd, &u_index);
    httpd_register_uri_handler(web_httpd, &u_cap);
    httpd_register_uri_handler(web_httpd, &u_ctl);
    httpd_register_uri_handler(web_httpd, &u_st);
  }
  cfg.server_port = 81;
  cfg.ctrl_port += 1;
  httpd_uri_t u_stream = {"/stream", HTTP_GET, stream_handler, NULL};
  if (httpd_start(&stream_httpd, &cfg) == ESP_OK)
    httpd_register_uri_handler(stream_httpd, &u_stream);
}

// --------------------------------------------------------------------
bool iniciarCamara() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_SVGA;          // 800x600: buen detalle para la moneda
  c.jpeg_quality = 8;                     // 0-63, menor = mejor calidad (menos artefactos en el relieve)
  c.fb_count = psramFound() ? 2 : 1;
  c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;       // siempre el frame mas nuevo (sin retraso)
  if (!psramFound()) c.frame_size = FRAMESIZE_VGA;

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Error iniciando la camara: 0x%x (revisa el cable flex y la alimentacion)\n", err);
    return false;
  }
  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("Sensor detectado PID=0x%x\n", s->id.PID);
  s->set_framesize(s, c.frame_size);
  s->set_vflip(s, 1);        // el PC lo puede cambiar (config.py -> AJUSTES_CAMARA)
  s->set_hmirror(s, 0);
  return true;
}

void iniciarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setTxPower(WIFI_POWER_15dBm);   // menos potencia = menos calor (sube a 19.5 si la senal es debil)
  Serial.printf("Conectando a %s", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi conectado.");
    Serial.printf("  Pagina de prueba : http://%s\n", WiFi.localIP().toString().c_str());
    Serial.printf("  Video para el PC : http://%s:81/stream\n", WiFi.localIP().toString().c_str());
    Serial.printf("  >>> En vision/config.py pon:  ESP32_IP = \"%s\"\n", WiFi.localIP().toString().c_str());
  } else {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);
    Serial.printf("No se pudo conectar. Red propia: %s  clave: %s\n", AP_SSID, AP_PASS);
    Serial.println("  >>> Conecta el PC a esa red y en config.py pon:  ESP32_IP = \"192.168.4.1\"");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32-CAM Monedas G3 ===");
  setCpuFrequencyMhz(CPU_MHZ);
  if (!iniciarCamara()) {
    delay(3000);
    ESP.restart();
  }
  iniciarFlash();            // SIEMPRE despues de la camara
  setFlash(LED_INICIAL);
  iniciarWiFi();
  iniciarServidores();
}

void loop() {
  // Si se cae el WiFi del router, reintenta solo
  static unsigned long ultimo = 0;
  if (WiFi.getMode() == WIFI_STA && WiFi.status() != WL_CONNECTED && millis() - ultimo > 10000) {
    ultimo = millis();
    Serial.println("WiFi perdido, reconectando...");
    WiFi.reconnect();
  }
  delay(100);
}
