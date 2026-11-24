/*
 * BandaServos_S3.ino   (v2: clasificacion automatica)
 * ==================
 * Motor de la banda + 4 servos SG90 (paletas que desvian cada moneda a su vaso).
 *
 *   ESP32-CAM --video--> PC (04_interfaz.py, reconoce y cuenta)
 *                         |  WiFi:  http://banda-s3.local/moneda?v=500
 *                         v
 *                     ESP32-S3: espera RETARDO_MS (lo que tarda la moneda en
 *                     llegar de la camara a su paleta), desvia T_DESVIO_MS y
 *                     vuelve a reposo. Varias monedas seguidas se encolan.
 *
 *   Moneda -> servo:  $1000 y $500 -> 1   $200 -> 2   $100 -> 3   $50 -> 4
 *
 * La S3 y el PC deben estar en la MISMA red WiFi que la ESP32-CAM: pon en
 * WIFI_SSID / WIFI_PASS los mismos datos que en ESP32CAM_Monedas_v2.ino.
 * La pagina de calibracion sigue disponible (ahora tambien con el retardo de
 * cada servo y un boton "Simular moneda").
 *
 * LA BANDA arranca sola al encender, al % guardado (por defecto VELOCIDAD_INICIAL),
 * igual que en tu sketch del motor. En la pagina puedes cambiar la velocidad o
 * pararla y "Guardar en la placa" para que arranque asi la proxima vez.
 *
 * Cada servo tiene dos posiciones:
 *   REPOSO : paleta apartada, la moneda pasa de largo por la banda
 *   DESVIO : paleta cruzada, la moneda se desvia hacia su vaso
 * y un tiempo que la paleta se queda en DESVIO antes de volver a REPOSO.
 *
 * COMO SE USA
 *   1. Conecta (ver cableado abajo) y sube este sketch.
 *   2. Abre  http://banda-s3.local  (o la IP que sale en el Monitor Serie,
 *      115200 baudios) desde un equipo en tu WiFi.
 *      Si la S3 no logra entrar a tu WiFi, sigue disponible su red propia
 *      "Servos-Monedas" (clave 12345678) en  http://192.168.4.1
 *   3. Mueve el servo con el control, pon monedas en la banda y mira como caen.
 *      Cuando la paleta quede bien: "Marcar REPOSO" / "Marcar DESVIO".
 *   4. "Guardar en la placa" (se conserva al apagar) y copia el bloque de
 *      codigo que sale al final de la pagina para dejarlo fijo en el programa.
 *
 * CABLEADO
 *   Motor de la banda: GPIO 4 -> 150 ohm -> base TIP31C ; colector -> motor(-)
 *                      y anodo 1N4007 ; emisor -> GND comun
 *   Servos (cada SG90: cafe/negro = GND, rojo = 5 V, naranja/amarillo = senal):
 *   Servo 1 ($1000 y $500) -> GPIO 5
 *   Servo 2 ($200)         -> GPIO 6
 *   Servo 3 ($100)         -> GPIO 7
 *   Servo 4 ($50)          -> GPIO 15
 *   - El rojo de los 4 servos va a una fuente de 5 V APARTE (>= 2 A), NO al pin
 *     de la ESP32: cuatro SG90 en conjunto pueden pedir mas de 1 A.
 *   - El GND de la fuente se une al GND de la ESP32-S3 (masa comun).
 *   - Un condensador de 470-1000 uF entre 5 V y GND de la fuente, cerca de
 *     los servos, evita reinicios de la placa cuando arrancan.
 *   - La senal de 3,3 V de la S3 es suficiente para el SG90.
 *
 * Placa en Arduino IDE: "ESP32S3 Dev Module"
 *   (Si ves el Monitor Serie en blanco: Tools > USB CDC On Boot > Enabled)
 */

#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ESPmDNS.h>

// ---------------------------------------------------------------------
// Pagina web (se guarda en flash)
// ---------------------------------------------------------------------
const char PAGINA[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Banda y servos</title>
<style>
:root{--bg:#0c0f14;--card:#151a22;--line:#242b37;--tx:#e8ecf2;--mut:#8b95a5;--ac:#4fd1a5;--wa:#f2b84b;--bt:#1e2530}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.4 system-ui,Segoe UI,sans-serif;padding:16px;max-width:760px;margin:auto}
h1{font-size:19px;margin:4px 0 2px}p.s{color:var(--mut);margin:0 0 14px;font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.top b{font-size:16px}.big{font-size:28px;font-weight:700;color:var(--ac);font-variant-numeric:tabular-nums}
input[type=range]{width:100%;margin:12px 0 6px;accent-color:var(--ac);height:28px}
.row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
button{background:var(--bt);color:var(--tx);border:1px solid var(--line);border-radius:9px;padding:9px 12px;font:inherit;cursor:pointer;flex:1 1 auto;min-width:56px}
button:active{transform:scale(.97)}button.p{background:var(--ac);color:#06201a;border-color:var(--ac);font-weight:600}
button.w{border-color:var(--wa);color:var(--wa)}
.gu{display:flex;gap:14px;color:var(--mut);font-size:13px;margin-top:6px}.gu b{color:var(--tx)}
.glob{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.glob label{color:var(--mut);font-size:13px}
.glob input[type=number]{width:84px;background:var(--bt);color:var(--tx);border:1px solid var(--line);border-radius:9px;padding:9px;font:inherit}
pre{background:#090c10;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;font-size:13px;margin:8px 0 0;color:#cfe9df}
#msg{color:var(--ac);font-size:13px;min-height:18px;margin:4px 2px}
</style></head><body>
<h1>Banda y servos SG90</h1>
<p class="s">Ajusta la banda, mueve la paleta, mira como cae la moneda y marca REPOSO y DESVIO. Al final guarda y copia el codigo.</p>
<div class="card"><div class="glob">
  <label>Tiempo en DESVIO (ms)</label><input type="number" id="ms" min="100" max="5000" step="50">
  <button onclick="call('/reposo_todos')">Todos a reposo</button>
  <button onclick="call('/probar_todos')">Probar los 4</button>
  <button class="p" onclick="call('/guardar','Guardado en la placa')">Guardar en la placa</button>
</div><div id="msg"></div></div>
<div class="card"><div class="top"><b>Banda transportadora <small style="color:var(--mut)">GPIO 4</small></b><span class="big" id="vv">--</span></div>
  <input type="range" id="vb" min="0" max="100" value="50" oninput="banda(this.value)" onpointerdown="arrV=1" onpointerup="arrV=0" onchange="arrV=0">
  <div class="row"><button onclick="paso2(-5)">-5</button><button onclick="paso2(-1)">-1</button>
  <button onclick="paso2(1)">+1</button><button onclick="paso2(5)">+5</button>
  <button class="w" onclick="call('/banda?v=0')">Parar</button></div></div>
<div id="servos"></div>
<div class="card"><b>Codigo para dejar fijo en el programa</b>
<pre id="cod"></pre>
<div class="row"><button onclick="copiar()">Copiar</button></div></div>
<script>
const NOM=["Vaso $1000 y $500","Vaso $200","Vaso $100","Vaso $50"];
const PIN=[5,6,7,15];
let E=null,arr=-1,t0=0,pend=null,arrV=0,t1=0;
const $=id=>document.getElementById(id);
function dom(){
  $('servos').innerHTML=NOM.map((n,i)=>`
  <div class="card"><div class="top"><b>${i+1}. ${n} <small style="color:var(--mut)">GPIO ${PIN[i]}</small></b><span class="big" id="a${i}">--</span></div>
  <input type="range" id="r${i}" min="0" max="180" value="90"
    oninput="mueve(${i},this.value)" onpointerdown="arr=${i}" onpointerup="arr=-1" onchange="arr=-1">
  <div class="row">
    <button onclick="paso(${i},-5)">-5</button><button onclick="paso(${i},-1)">-1</button>
    <button onclick="paso(${i},1)">+1</button><button onclick="paso(${i},5)">+5</button></div>
  <div class="row">
    <button class="w" onclick="call('/marcar?s=${i}&t=r','Reposo del servo ${i+1} marcado')">Marcar REPOSO</button>
    <button class="w" onclick="call('/marcar?s=${i}&t=d','Desvio del servo ${i+1} marcado')">Marcar DESVIO</button></div>
  <div class="row">
    <button onclick="call('/ir?s=${i}&t=r')">Ir a reposo</button>
    <button onclick="call('/ir?s=${i}&t=d')">Ir a desvio</button>
    <button class="p" onclick="call('/probar?s=${i}')">Probar &#9654;</button></div>
  <div class="gu"><span>Reposo: <b id="rp${i}">-</b>&deg;</span><span>Desvio: <b id="ds${i}">-</b>&deg;</span><span>Recibidas: <b id="rc${i}">0</b></span></div>
  <div class="row glob"><label>Retardo (ms)</label><input type="number" id="e${i}" min="0" max="20000" step="100"
    onchange="call('/retardo?s=${i}&v='+this.value)">
    <button onclick="sim(${i})">Simular moneda</button></div></div>`).join('');
}
function pinta(){
  if(!E)return;
  for(let i=0;i<4;i++){
    $('a'+i).textContent=E.ang[i]+'°';
    if(arr!==i)$('r'+i).value=E.ang[i];
    $('rp'+i).textContent=E.rep[i];$('ds'+i).textContent=E.des[i];
    $('rc'+i).textContent=E.rec[i];if(document.activeElement!==$('e'+i))$('e'+i).value=E.ret[i];
  }
  $('vv').textContent=E.vel+' %';if(!arrV)$('vb').value=E.vel;
  if(document.activeElement!==$('ms'))$('ms').value=E.ms;
  $('cod').textContent=
`const int PIN_MOTOR    = 4;
const int VELOCIDAD     = ${E.vel};   // % de la banda
const int PIN_SERVO[4]  = {${PIN.join(', ')}};
const int REPOSO[4]     = {${E.rep.join(', ')}};   // paleta apartada
const int DESVIO[4]     = {${E.des.join(', ')}};   // paleta cruzada
const int T_DESVIO_MS   = ${E.ms};
const int RETARDO_MS[4] = {${E.ret.join(', ')}};`;
}
async function call(u,m){
  try{E=await (await fetch(u)).json();pinta();if(m){$('msg').textContent=m;setTimeout(()=>$('msg').textContent='',2500)}}
  catch(e){$('msg').textContent='Sin conexion con la placa'}
}
function mueve(i,v){
  $('a'+i).textContent=v+'°';pend=[i,v];
  const ahora=Date.now();
  if(ahora-t0>45){t0=ahora;enviaPend()}else{clearTimeout(mueve.t);mueve.t=setTimeout(enviaPend,50)}
}
function banda(v){$('vv').textContent=v+' %';const a=Date.now();
  if(a-t1>60){t1=a;call('/banda?v='+v)}else{clearTimeout(banda.t);banda.t=setTimeout(()=>call('/banda?v='+$('vb').value),70)}}
function paso2(d){call('/banda?v='+Math.max(0,Math.min(100,(E?E.vel:0)+d)))}
async function sim(i){try{await fetch('/moneda?s='+i)}catch(e){}
  call('/estado','Moneda simulada: el servo '+(i+1)+' se mueve en '+$('e'+i).value+' ms')}
function enviaPend(){if(pend){const[i,v]=pend;pend=null;call(`/set?s=${i}&a=${v}`)}}
function paso(i,d){const v=Math.max(0,Math.min(180,(E?E.ang[i]:90)+d));call(`/set?s=${i}&a=${v}`)}
$('ms').addEventListener('change',e=>call('/ms?v='+e.target.value));
function copiar(){navigator.clipboard&&navigator.clipboard.writeText($('cod').textContent).then(()=>{$('msg').textContent='Codigo copiado';setTimeout(()=>$('msg').textContent='',2000)}).catch(()=>{})}
dom();call('/estado');setInterval(()=>{if(arr<0&&!arrV)call('/estado')},1500);
</script></body></html>)HTML";

// ---- WiFi -------------------------------------------------------------
const char* WIFI_SSID = "TU_RED_WIFI";            // <-- el MISMO WiFi de la ESP32-CAM y el PC
const char* WIFI_PASS = "";
const char* NOMBRE_RED = "banda-s3";   // el PC la encuentra como http://banda-s3.local
const char* AP_SSID   = "Servos-Monedas";   // red propia de la placa (siempre disponible)
const char* AP_PASS   = "12345678";

// ---- Motor de la banda (el GPIO 4 es el de tu sketch original) ----------
const int PIN_MOTOR = 4;
const int PWM_FREQ  = 1000;            // 1 kHz
const int PWM_BITS  = 10;              // 0..1023
const int VELOCIDAD_INICIAL = 50;      // % con el que arranca (calibrado: 50)
int vel = VELOCIDAD_INICIAL;           // % actual (0 = parada)

// ---- Servos -----------------------------------------------------------
const int N = 4;
const int PIN_SERVO[N] = {5, 6, 7, 15};
const char* NOMBRE[N]  = {"Vaso $1000 y $500", "Vaso $200", "Vaso $100", "Vaso $50"};
const int US_MIN = 500;                // ancho de pulso a 0 grados  (SG90: 500-600)
const int US_MAX = 2400;               // ancho de pulso a 180 grados (SG90: 2300-2500)

int ang[N];                            // angulo actual
// Valores calibrados (pagina de calibracion, 24 nov). Se pueden reajustar en la
// pagina y "Guardar en la placa"; lo guardado tiene prioridad sobre esto.
int rep[N] = {47, 180, 90, 0};         // angulo de REPOSO (paleta apartada)
int des[N] = {120, 116, 50, 50};       // angulo de DESVIO (paleta cruzada)
int tDesvio = 1500;                    // ms que la paleta queda desviada
int retardo[N] = {2000, 2000, 4500, 4500};  // ms desde que el PC detecta la moneda
                                            // hasta mover la paleta: servos 1 y 2 a 3 s,
                                            // servos 3 y 4 a 5 s (estan mas lejos)

// ---- Cola de monedas pendientes (sin bloquear la pagina ni la banda) ----
struct Pendiente { int s; uint32_t t; };
const int MAX_COLA = 24;
Pendiente cola[MAX_COLA];
int nCola = 0;
bool desviado[N] = {false, false, false, false};
uint32_t finDesvio[N];
int recibidas[N] = {0, 0, 0, 0};       // monedas recibidas desde el PC (por servo)

WebServer web(80);
Preferences nvs;

// ---------------------------------------------------------------------
void motorInit() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_MOTOR, PWM_FREQ, PWM_BITS);
#else
  ledcSetup(0, PWM_FREQ, PWM_BITS);
  ledcAttachPin(PIN_MOTOR, 0);
#endif
}

void motorPwm(uint32_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_MOTOR, duty);
#else
  ledcWrite(0, duty);
#endif
}

// Velocidad de la banda en %. Si estaba parada da un empujon de 150 ms para que arranque.
void banda(int pct) {
  pct = constrain(pct, 0, 100);
  if (pct > 0 && vel == 0) {
    motorPwm(1023);
    delay(150);
  }
  vel = pct;
  motorPwm((1023UL * pct) / 100);
}

void pwmInit(int i) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_SERVO[i], 50, 14);
#else
  ledcSetup(i + 2, 50, 14);            // canales 2..5: no comparten temporizador con el motor
  ledcAttachPin(PIN_SERVO[i], i + 2);
#endif
}

void mover(int i, int a) {
  a = constrain(a, 0, 180);
  ang[i] = a;
  uint32_t us = US_MIN + (uint32_t)(US_MAX - US_MIN) * a / 180;
  uint32_t duty = us * 16383UL / 20000UL;          // 50 Hz = 20000 us, 14 bits
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_SERVO[i], duty);
#else
  ledcWrite(i + 2, duty);
#endif
}

void probar(int i) {
  mover(i, des[i]);
  delay(tDesvio);
  mover(i, rep[i]);
}

// Denominacion en pesos -> servo (0..3); -1 si no corresponde
int servoDeValor(int v) {
  if (v == 1000 || v == 500) return 0;
  if (v == 200) return 1;
  if (v == 100) return 2;
  if (v == 50)  return 3;
  return -1;
}

// ya_ms: tiempo que ya paso desde que el PC vio la moneda (se descuenta del retardo)
bool encolar(int s, int ya_ms = 0) {
  if (s < 0 || s >= N || nCola >= MAX_COLA) return false;
  int espera = max(0, retardo[s] - constrain(ya_ms, 0, 5000));
  cola[nCola++] = {s, millis() + (uint32_t)espera};
  recibidas[s]++;
  return true;
}

// Se llama en cada vuelta del loop: activa las paletas a su hora y las regresa.
void atenderCola() {
  uint32_t ahora = millis();
  for (int k = 0; k < nCola; ) {
    if ((int32_t)(ahora - cola[k].t) >= 0) {
      int s = cola[k].s;
      mover(s, des[s]);
      desviado[s] = true;
      finDesvio[s] = ahora + tDesvio;          // si ya estaba desviada, se alarga
      Serial.printf("[%lu ms] Servo %d -> DESVIO\n", (unsigned long)ahora, s + 1);
      cola[k] = cola[--nCola];                 // quita de la cola
    } else {
      k++;
    }
  }
  for (int s = 0; s < N; s++) {
    if (desviado[s] && (int32_t)(ahora - finDesvio[s]) >= 0) {
      mover(s, rep[s]);
      desviado[s] = false;
    }
  }
}

void cargar() {
  nvs.begin("servos2", true);          // espacio nuevo: arranca con los valores calibrados
  for (int i = 0; i < N; i++) {
    rep[i] = nvs.getInt(("r" + String(i)).c_str(), rep[i]);
    des[i] = nvs.getInt(("d" + String(i)).c_str(), des[i]);
  }
  tDesvio = nvs.getInt("t", tDesvio);
  vel = nvs.getInt("v", vel);
  for (int i = 0; i < N; i++) retardo[i] = nvs.getInt(("q" + String(i)).c_str(), retardo[i]);
  nvs.end();
}

void guardar() {
  nvs.begin("servos2", false);
  for (int i = 0; i < N; i++) {
    nvs.putInt(("r" + String(i)).c_str(), rep[i]);
    nvs.putInt(("d" + String(i)).c_str(), des[i]);
  }
  nvs.putInt("t", tDesvio);
  nvs.putInt("v", vel);
  for (int i = 0; i < N; i++) nvs.putInt(("q" + String(i)).c_str(), retardo[i]);
  nvs.end();
}

// ---------------------------------------------------------------------
String lista(const int* v) {
  String s = "[";
  for (int i = 0; i < N; i++) s += String(v[i]) + (i < N - 1 ? "," : "");
  return s + "]";
}

void enviarEstado() {
  String ip = WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "";
  String j = "{\"ang\":" + lista(ang) + ",\"rep\":" + lista(rep) + ",\"des\":" + lista(des) +
             ",\"ms\":" + String(tDesvio) + ",\"vel\":" + String(vel) + ",\"ret\":" + lista(retardo) +
             ",\"rec\":" + lista(recibidas) + ",\"cola\":" + String(nCola) +
             ",\"ip\":\"" + ip + "\"}";
  web.sendHeader("Cache-Control", "no-store");
  web.send(200, "application/json", j);
}

int servoArg() {
  int s = web.hasArg("s") ? web.arg("s").toInt() : -1;
  return (s >= 0 && s < N) ? s : -1;
}

void rutas() {
  web.on("/", []() { web.send_P(200, "text/html; charset=utf-8", PAGINA); });
  web.on("/estado", enviarEstado);
  web.on("/set", []() {
    int s = servoArg();
    if (s >= 0 && web.hasArg("a")) mover(s, web.arg("a").toInt());
    enviarEstado();
  });
  web.on("/marcar", []() {                         // t=r reposo, t=d desvio
    int s = servoArg();
    if (s >= 0) (web.arg("t") == "r" ? rep : des)[s] = ang[s];
    enviarEstado();
  });
  web.on("/ir", []() {
    int s = servoArg();
    if (s >= 0) mover(s, web.arg("t") == "r" ? rep[s] : des[s]);
    enviarEstado();
  });
  web.on("/probar", []() {
    int s = servoArg();
    if (s >= 0) probar(s);
    enviarEstado();
  });
  web.on("/probar_todos", []() {
    for (int i = 0; i < N; i++) { probar(i); delay(300); }
    enviarEstado();
  });
  web.on("/reposo_todos", []() {
    for (int i = 0; i < N; i++) mover(i, rep[i]);
    enviarEstado();
  });
  web.on("/banda", []() {
    if (web.hasArg("v")) banda(web.arg("v").toInt());
    enviarEstado();
  });
  web.on("/ms", []() {
    if (web.hasArg("v")) tDesvio = constrain(web.arg("v").toInt(), 100, 5000);
    enviarEstado();
  });
  web.on("/guardar", []() { guardar(); enviarEstado(); });
  web.on("/retardo", []() {                        // retardo de un servo (ms)
    int s = servoArg();
    if (s >= 0 && web.hasArg("v")) retardo[s] = constrain(web.arg("v").toInt(), 0, 20000);
    enviarEstado();
  });
  // Lo llama el PC cada vez que cuenta una moneda:  /moneda?v=500&d=40   (o ?s=0..3)
  // d = ms que ya pasaron en el PC desde que conto la moneda (opcional)
  web.on("/moneda", []() {
    int s = web.hasArg("v") ? servoDeValor(web.arg("v").toInt()) : servoArg();
    bool ok = encolar(s, web.hasArg("d") ? web.arg("d").toInt() : 0);
    if (ok) Serial.printf("[%lu ms] Moneda $%s -> servo %d en %d ms\n", (unsigned long)millis(),
                          web.hasArg("v") ? web.arg("v").c_str() : "?", s + 1, retardo[s]);
    web.send(ok ? 200 : 400, "application/json",
             ok ? "{\"ok\":true,\"servo\":" + String(s + 1) + ",\"en_ms\":" + String(retardo[s]) + "}"
                : String("{\"ok\":false}"));
  });
}

// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  cargar();
  motorInit();
  int v0 = vel; vel = 0;               // para que banda() de el empujon inicial
  banda(v0);
  for (int i = 0; i < N; i++) {                    // de a uno: evita el pico de corriente
    pwmInit(i);
    mover(i, rep[i]);
    delay(250);
  }

  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID, AP_PASS);
  WiFi.setHostname(NOMBRE_RED);
  WiFi.setSleep(false);                // respuesta rapida a los avisos del PC
  if (strlen(WIFI_SSID) > 0) {
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int t = 0; t < 60 && WiFi.status() != WL_CONNECTED; t++) delay(250);
  }
  rutas();
  web.begin();
  if (MDNS.begin(NOMBRE_RED)) MDNS.addService("http", "tcp", 80);

  Serial.println("\n=== Banda + clasificacion de monedas ===");
  Serial.printf("Banda al %d %%\n", vel);
  Serial.printf("Red propia : %s (clave %s)  ->  http://%s\n", AP_SSID, AP_PASS,
                WiFi.softAPIP().toString().c_str());
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("Tu WiFi    : http://%s  (o http://%s.local)  <- pon esta IP en config.py\n",
                  WiFi.localIP().toString().c_str(), NOMBRE_RED);
  else if (strlen(WIFI_SSID) > 0)
    Serial.printf("[!] No entro al WiFi \"%s\": revisa nombre y clave\n", WIFI_SSID);
  else
    Serial.println("[!] WIFI_SSID vacio: el PC no podra mandar las monedas");
}

void loop() {
  web.handleClient();
  atenderCola();
}
