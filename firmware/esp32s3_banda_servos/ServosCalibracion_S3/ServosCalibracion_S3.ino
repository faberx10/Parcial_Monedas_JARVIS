/*
 * ServosCalibracion_S3.ino
 * ========================
 * Calibracion de los 4 servos SG90 (paletas que desvian cada moneda a su vaso)
 * desde una pagina web, para ver COMO CAEN las monedas antes de dejar los
 * angulos fijos en el codigo final.
 *
 *   ESP32-S3  --WiFi-->  celular / PC  (pagina con un control por servo)
 *
 * Cada servo tiene dos posiciones:
 *   REPOSO : paleta apartada, la moneda pasa de largo por la banda
 *   DESVIO : paleta cruzada, la moneda se desvia hacia su vaso
 * y un tiempo que la paleta se queda en DESVIO antes de volver a REPOSO.
 *
 * COMO SE USA
 *   1. Conecta (ver cableado abajo) y sube este sketch.
 *   2. Conecta el celular/PC a la red WiFi  "Servos-Monedas"  (clave 12345678)
 *      y abre  http://192.168.4.1
 *      (si pones tu WiFi en WIFI_SSID/WIFI_PASS tambien entra por la IP que
 *       sale en el Monitor Serie, 115200 baudios)
 *   3. Mueve el servo con el control, pon monedas en la banda y mira como caen.
 *      Cuando la paleta quede bien: "Marcar REPOSO" / "Marcar DESVIO".
 *   4. "Guardar en la placa" (se conserva al apagar) y copia el bloque de
 *      codigo que sale al final de la pagina para dejarlo fijo en el programa.
 *
 * CABLEADO (cada SG90: cafe/negro = GND, rojo = 5 V, naranja/amarillo = senal)
 *   Servo 1 ($1000 y $500) -> GPIO 4
 *   Servo 2 ($200)         -> GPIO 5
 *   Servo 3 ($100)         -> GPIO 6
 *   Servo 4 ($50)          -> GPIO 7
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

// ---------------------------------------------------------------------
// Pagina web (se guarda en flash)
// ---------------------------------------------------------------------
const char PAGINA[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Calibracion de servos</title>
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
<h1>Calibracion de servos SG90</h1>
<p class="s">Mueve la paleta, mira como cae la moneda y marca REPOSO y DESVIO. Al final guarda y copia el codigo.</p>
<div class="card"><div class="glob">
  <label>Tiempo en DESVIO (ms)</label><input type="number" id="ms" min="100" max="5000" step="50">
  <button onclick="call('/reposo_todos')">Todos a reposo</button>
  <button onclick="call('/probar_todos')">Probar los 4</button>
  <button class="p" onclick="call('/guardar','Guardado en la placa')">Guardar en la placa</button>
</div><div id="msg"></div></div>
<div id="servos"></div>
<div class="card"><b>Codigo para dejar fijo en el programa</b>
<pre id="cod"></pre>
<div class="row"><button onclick="copiar()">Copiar</button></div></div>
<script>
const NOM=["Vaso $1000 y $500","Vaso $200","Vaso $100","Vaso $50"];
const PIN=[4,5,6,7];
let E=null,arr=-1,t0=0,pend=null;
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
  <div class="gu"><span>Reposo: <b id="rp${i}">-</b>&deg;</span><span>Desvio: <b id="ds${i}">-</b>&deg;</span></div></div>`).join('');
}
function pinta(){
  if(!E)return;
  for(let i=0;i<4;i++){
    $('a'+i).textContent=E.ang[i]+'°';
    if(arr!==i)$('r'+i).value=E.ang[i];
    $('rp'+i).textContent=E.rep[i];$('ds'+i).textContent=E.des[i];
  }
  if(document.activeElement!==$('ms'))$('ms').value=E.ms;
  $('cod').textContent=
`const int PIN_SERVO[4]  = {${PIN.join(', ')}};
const int REPOSO[4]     = {${E.rep.join(', ')}};   // paleta apartada
const int DESVIO[4]     = {${E.des.join(', ')}};   // paleta cruzada
const int T_DESVIO_MS   = ${E.ms};`;
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
function enviaPend(){if(pend){const[i,v]=pend;pend=null;call(`/set?s=${i}&a=${v}`)}}
function paso(i,d){const v=Math.max(0,Math.min(180,(E?E.ang[i]:90)+d));call(`/set?s=${i}&a=${v}`)}
$('ms').addEventListener('change',e=>call('/ms?v='+e.target.value));
function copiar(){navigator.clipboard&&navigator.clipboard.writeText($('cod').textContent).then(()=>{$('msg').textContent='Codigo copiado';setTimeout(()=>$('msg').textContent='',2000)}).catch(()=>{})}
dom();call('/estado');
</script></body></html>)HTML";

// ---- WiFi -------------------------------------------------------------
const char* WIFI_SSID = "";            // opcional: tu red (deja "" para usar solo la propia)
const char* WIFI_PASS = "";
const char* AP_SSID   = "Servos-Monedas";   // red propia de la placa (siempre disponible)
const char* AP_PASS   = "12345678";

// ---- Servos -----------------------------------------------------------
const int N = 4;
const int PIN_SERVO[N] = {4, 5, 6, 7};
const char* NOMBRE[N]  = {"Vaso $1000 y $500", "Vaso $200", "Vaso $100", "Vaso $50"};
const int US_MIN = 500;                // ancho de pulso a 0 grados  (SG90: 500-600)
const int US_MAX = 2400;               // ancho de pulso a 180 grados (SG90: 2300-2500)

int ang[N];                            // angulo actual
int rep[N] = {90, 90, 90, 90};         // angulo de REPOSO
int des[N] = {50, 50, 50, 50};         // angulo de DESVIO
int tDesvio = 600;                     // ms que la paleta queda desviada

WebServer web(80);
Preferences nvs;

// ---------------------------------------------------------------------
void pwmInit(int i) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_SERVO[i], 50, 14);
#else
  ledcSetup(i, 50, 14);
  ledcAttachPin(PIN_SERVO[i], i);
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
  ledcWrite(i, duty);
#endif
}

void probar(int i) {
  mover(i, des[i]);
  delay(tDesvio);
  mover(i, rep[i]);
}

void cargar() {
  nvs.begin("servos", true);
  for (int i = 0; i < N; i++) {
    rep[i] = nvs.getInt(("r" + String(i)).c_str(), rep[i]);
    des[i] = nvs.getInt(("d" + String(i)).c_str(), des[i]);
  }
  tDesvio = nvs.getInt("t", tDesvio);
  nvs.end();
}

void guardar() {
  nvs.begin("servos", false);
  for (int i = 0; i < N; i++) {
    nvs.putInt(("r" + String(i)).c_str(), rep[i]);
    nvs.putInt(("d" + String(i)).c_str(), des[i]);
  }
  nvs.putInt("t", tDesvio);
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
             ",\"ms\":" + String(tDesvio) + ",\"ip\":\"" + ip + "\"}";
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
  web.on("/ms", []() {
    if (web.hasArg("v")) tDesvio = constrain(web.arg("v").toInt(), 100, 5000);
    enviarEstado();
  });
  web.on("/guardar", []() { guardar(); enviarEstado(); });
}

// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  cargar();
  for (int i = 0; i < N; i++) {                    // de a uno: evita el pico de corriente
    pwmInit(i);
    mover(i, rep[i]);
    delay(250);
  }

  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID, AP_PASS);
  if (strlen(WIFI_SSID) > 0) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int t = 0; t < 40 && WiFi.status() != WL_CONNECTED; t++) delay(250);
  }
  rutas();
  web.begin();

  Serial.println("\n=== Calibracion de servos ===");
  Serial.printf("Red propia : %s (clave %s)  ->  http://%s\n", AP_SSID, AP_PASS,
                WiFi.softAPIP().toString().c_str());
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("Tu WiFi    : http://%s\n", WiFi.localIP().toString().c_str());
}

void loop() {
  web.handleClient();
}
