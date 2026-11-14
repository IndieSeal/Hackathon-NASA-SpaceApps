(function(){
"use strict";
const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const WS_URL = API ? API.replace(/^http/, "ws") + "/ws/telemetry"
                   : (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + "/ws/telemetry";
const MAX = 25;
const $ = id => document.getElementById(id);
const COLORS = {VERDE:"#1f9d63", AMARILLO:"#d99a00", ROJO:"#d93a3a"};
const LEVEL = {VERDE:"Verde", AMARILLO:"Amarillo", ROJO:"Rojo"};
const CLASSES = [
  ["NOMINAL","Nominal"], ["ATAQUE_ANSIEDAD","Ansiedad"], ["EVENTO_CARDIOVASCULAR","Cardiovascular"],
  ["INFECCION_ENFERMEDAD","Infección"], ["FATIGA_CIRCADIANA","Fatiga circadiana"]
];
const CRIT = new Set(["ARRITMIA_EXTREMA","TAQUICARDIA_SEVERA","HIPOXIA_CRITICA","INDICE_DE_CHOQUE_CRITICO","HIPOTENSION_SEVERA",
  "CRISIS_HIPERTENSIVA","FIEBRE_ALTA","HIPOTERMIA","TAQUIPNEA_SEVERA","BRADIPNEA_CRITICA","DESATURACION_RAPIDA_DE_OXIGENO"]);
const BY_CARD = {
  hr:["ARRITMIA_EXTREMA","TAQUICARDIA_SEVERA","TAQUICARDIA","BRADICARDIA","TAQUICARDIA_DE_INICIO_RAPIDO"],
  hrv:["VARIABILIDAD_CARDIACA_SUPRIMIDA"],
  spo2:["HIPOXIA_CRITICA","HIPOXIA","DESATURACION_RAPIDA_DE_OXIGENO"],
  bp:["HIPOTENSION_SEVERA","HIPOTENSION","CRISIS_HIPERTENSIVA","HIPERTENSION"],
  temp:["FIEBRE_ALTA","FIEBRE","HIPOTERMIA"],
  resp:["TAQUIPNEA_SEVERA","TAQUIPNEA","BRADIPNEA_CRITICA","BRADIPNEA"],
  shock:["INDICE_DE_CHOQUE_CRITICO","INDICE_DE_CHOQUE_ELEVADO"],
  pulse:["PRESION_DE_PULSO_ESTRECHA","PRESION_DE_PULSO_AMPLIA"]
};
const pretty = t => { const s = t.toLowerCase().replace(/_/g, " "); return s.charAt(0).toUpperCase() + s.slice(1); };
const clock = ts => new Date(ts * 1000).toLocaleTimeString("es-MX", {hour12:false});

const series = {t:[], hr:[], spo2:[], hrv:[], sbp:[]};
let last = null, lastColor = null, lastTs = null, wsOn = false, pollOk = false;

/* Charts */
Chart.defaults.font.family = '"Instrument Sans", system-ui, sans-serif';
Chart.defaults.color = "#7a8190";
const grid = {color:"#f0f1f4"}, noGrid = {display:false};
const legend = {position:"top", align:"end", labels:{usePointStyle:true, boxWidth:7, boxHeight:7, padding:14}};
const ds = (label, data, color, axis) => ({label, data, borderColor:color, backgroundColor:color, yAxisID:axis, borderWidth:2, tension:.35, pointRadius:0, pointHoverRadius:4});
const lineOpts = (a, b) => ({
  responsive:true, maintainAspectRatio:false, animation:false, interaction:{mode:"index", intersect:false},
  scales:{x:{grid:noGrid, ticks:{maxRotation:0, maxTicksLimit:5}, border:{display:false}},
          [a]:{position:"left", grid, border:{display:false}}, [b]:{position:"right", grid:noGrid, border:{display:false}}},
  plugins:{legend}
});
const c1 = new Chart($("c1"), {type:"line", data:{labels:series.t, datasets:[
  ds("Frecuencia cardíaca (lpm)", series.hr, "#14171f", "a"), ds("SpO2 (%)", series.spo2, "#3b6ef5", "b")]}, options:lineOpts("a","b")});
const c2 = new Chart($("c2"), {type:"line", data:{labels:series.t, datasets:[
  ds("RMSSD (ms)", series.hrv, "#14171f", "a"), ds("Sistólica (mmHg)", series.sbp, "#3b6ef5", "b")]}, options:lineOpts("a","b")});

const valueLabels = {id:"valueLabels", afterDatasetsDraw(chart){
  const {ctx} = chart; ctx.save(); ctx.fillStyle = "#14171f"; ctx.font = '500 12px "Instrument Sans", sans-serif'; ctx.textBaseline = "middle";
  chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(chart.data.datasets[0].data[i].toFixed(1) + "%", bar.x + 8, bar.y));
  ctx.restore();
}};
const c3 = new Chart($("c3"), {type:"bar", plugins:[valueLabels], data:{labels:CLASSES.map(c => c[1]), datasets:[
  {data:CLASSES.map(() => 0), backgroundColor:"#e5e7eb", borderRadius:5, barThickness:14}]},
  options:{indexAxis:"y", responsive:true, maintainAspectRatio:false, animation:false, layout:{padding:{right:44}},
    scales:{x:{min:0, max:100, grid, border:{display:false}, ticks:{callback:v => v + "%"}}, y:{grid:noGrid, border:{display:false}, ticks:{color:"#14171f"}}},
    plugins:{legend:{display:false}, tooltip:{callbacks:{label:c => c.parsed.x.toFixed(1) + "%"}}}}});

/* Render */
const astronautName = document.getElementById("astronaut-name");
const astronautNameSubline = document.getElementById("astronaut-name_subline");
function render(d, pushPoint){
    astronautNameSubline.style.width = astronautName.style.width;

  last = d; $("gen").disabled = false;
  const c = d.nasa_alert_color, tel = d.raw_telemetry, m = d.derived_metrics || {}, trg = d.clinical_triggers || [];

  $("hero").className = "card hero " + c;
  $("level").textContent = LEVEL[c] || c;
  $("pred").textContent = pretty(d.primary_prediction);
  $("conf").textContent = d.confidence_pct.toFixed(1) + "%";
  $("anom").textContent = "Astronauta " + d.astronaut_id + (d.unsupervised_anomaly ? " · anomalía detectada" : " · sin anomalías");
  $("chips").innerHTML = "";
  (trg.length ? trg : [null]).forEach(t => {
    const s = document.createElement("span");
    s.className = "chip " + (t === null ? "none" : CRIT.has(t) ? "crit" : "warn");
    s.textContent = t === null ? "Sin hallazgos activos" : pretty(t);
    $("chips").appendChild(s);
  });

  $("v-hr").textContent = tel.hr.toFixed(0);
  $("v-hrv").textContent = tel.hrv_rmssd.toFixed(1);
  $("v-spo2").textContent = tel.spo2.toFixed(1);
  $("v-bp").textContent = tel.sbp.toFixed(0) + "/" + tel.dbp.toFixed(0);
  $("v-temp").textContent = tel.temp_c.toFixed(1);
  $("v-resp").textContent = tel.resp_rate.toFixed(0);
  $("v-shock").textContent = (m.shock_index ?? 0).toFixed(2);
  $("v-pulse").textContent = (m.pulse_pressure ?? tel.sbp - tel.dbp).toFixed(0);
  for (const k in BY_CARD){
    const hits = trg.filter(t => BY_CARD[k].includes(t));
    $("k-" + k).className = "v" + (hits.some(t => CRIT.has(t)) ? " crit" : hits.length ? " warn" : "");
  }

  if (pushPoint){
    series.t.push(clock(tel.timestamp)); series.hr.push(tel.hr); series.spo2.push(tel.spo2);
    series.hrv.push(tel.hrv_rmssd); series.sbp.push(tel.sbp);
    for (const k in series) while (series[k].length > MAX) series[k].shift();
    c1.update("none"); c2.update("none");
  }
  c3.data.datasets[0].data = CLASSES.map(([k]) => Math.round((d.probabilities[k] || 0) * 1000) / 10);
  c3.data.datasets[0].backgroundColor = CLASSES.map(([k]) => k === d.primary_prediction ? (COLORS[c] || "#14171f") : "#e5e7eb");
  c3.update("none");
  lastTs = tel.timestamp;
  window.dispatchEvent(new CustomEvent("telemetry", {detail: d}));
}

function onTelemetry(d){
  render(d, true);
  const c = d.nasa_alert_color;
  if ((c === "AMARILLO" || c === "ROJO") && c !== lastColor && wsOn) $("pend").style.display = "flex";
  lastColor = c;
}
function showReport(r){
  $("pend").style.display = "none";
  $("rep").textContent = r.report_text;
  $("repMeta").textContent = "Alerta " + (LEVEL[r.alert_color] || r.alert_color).toLowerCase() + " · " + pretty(r.diagnosis) +
    " · inferencia en " + r.inference_time_sec.toFixed(2) + " s";
}

/* API */
const post = (path, body) => fetch(API + path, {method:"POST", headers:body ? {"Content-Type":"application/json"} : undefined, body:body ? JSON.stringify(body) : undefined});

document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", async () => {
  document.querySelectorAll(".seg button").forEach(x => x.classList.toggle("on", x === b));
  try { await post("/stream/start/" + b.dataset.s); } catch(e){ console.error(e); }
}));
$("stop").addEventListener("click", async () => {
  document.querySelectorAll(".seg button").forEach(x => x.classList.remove("on"));
  try { await post("/stream/stop"); } catch(e){ console.error(e); }
});
$("gen").addEventListener("click", async () => {
  if (!last) return;
  $("gen").disabled = true; $("pend").style.display = "flex";
  try {
    const r = await post("/report", last);
    if (!r.ok) throw new Error(r.status);
    showReport(await r.json());
  } catch(e){
    $("pend").style.display = "none";
    $("rep").textContent = "No se pudo generar el reporte. Revisa que Ollama esté activo e inténtalo de nuevo.";
  }
  $("gen").disabled = false;
});

async function health(){
  try {
    const h = await (await fetch(API + "/health")).json();
    $("dMl").className = "dot " + (h.ml_engine && h.ml_engine.ready ? "ok" : "bad");
    const o = h.ollama || {};
    $("dOl").className = "dot " + (o.reachable && o.model_available ? "ok" : o.reachable ? "warn" : "bad");
  } catch(e){ $("dMl").className = "dot"; $("dOl").className = "dot"; }
}

function conn(){
  const [cls, txt] = wsOn ? ["ok","En vivo"] : pollOk ? ["warn","Sondeo cada 2 s"] : ["bad","Sin conexión"];
  $("dConn").className = "dot " + cls; $("tConn").textContent = txt;
}

async function history(initial){
  try {
    const r = await fetch(API + "/history"); if (!r.ok) throw 0;
    const list = await r.json(); pollOk = true;
    if (initial){
      list.slice(-MAX).forEach(d => { const t = d.raw_telemetry;
        series.t.push(clock(t.timestamp)); series.hr.push(t.hr); series.spo2.push(t.spo2); series.hrv.push(t.hrv_rmssd); series.sbp.push(t.sbp); });
      if (list.length){ render(list[list.length - 1], false); lastColor = list[list.length - 1].nasa_alert_color; c1.update("none"); c2.update("none"); }
    } else if (list.length && list[list.length - 1].raw_telemetry.timestamp !== lastTs){
      onTelemetry(list[list.length - 1]);
    }
  } catch(e){ pollOk = false; }
  conn();
}

let delay = 1000;
function socket(){
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => { wsOn = true; delay = 1000; conn(); };
  ws.onmessage = ev => {
    let msg; try { msg = JSON.parse(ev.data); } catch(e){ return; }
    if (msg.type === "telemetry") onTelemetry(msg.data);
    else if (msg.type === "sbar_report") showReport(msg.data);
  };
  ws.onclose = () => { wsOn = false; conn(); setTimeout(socket, delay); delay = Math.min(delay * 1.5, 10000); };
  ws.onerror = () => ws.close();
}

history(true); health(); socket();
setInterval(() => { if (!wsOn) history(false); }, 2000);
setInterval(health, 10000);
})();