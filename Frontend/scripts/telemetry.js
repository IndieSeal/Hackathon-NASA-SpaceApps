/*
 * telemetry.js: capa de datos compartida. Cualquier interfaz (index, multi, otras) la carga y pide lo que necesita.
 *
 *   Telemetry.astronauts()            -> ["AST-01", ...]
 *   Telemetry.profile("AST-01")       -> {id, name, photo}
 *   Telemetry.metric("AST-01","spo2") -> {label, unit, value, text, status, triggers, series}
 *   Telemetry.all("AST-01")           -> [metric, metric, ...] (en el orden de Telemetry.metrics)
 *   Telemetry.latest("AST-01")        -> DiagnosticOutput completo (probabilities, clinical_triggers, ...)
 *   Telemetry.alert("AST-01")         -> "VERDE" | "AMARILLO" | "ROJO"
 *   Telemetry.on((id, diagnostic) => ...)   // se llama en cada lectura; devuelve una funcion para cancelar
 *   Telemetry.start / stop / shot     // escenarios de la API
 *
 * status de cada metrica: "ok" | "warn" | "crit". Sale de clinical_triggers (los umbrales viven en el backend).
 */
(function () {
"use strict";
const sameOriginAsApi = location.port === "8000" || location.port === "";
const defaultApi = sameOriginAsApi ? "" : `${location.protocol}//${location.hostname}:8000`;
const API = (new URLSearchParams(location.search).get("api") || defaultApi).replace(/\/$/, "");
const WS_URL = API ? API.replace(/^http/, "ws") + "/ws/telemetry"
                   : (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + "/ws/telemetry";
const KEEP = 60;

/* La API ya entrega nombrec (nombre completo desde Postgres) dentro de raw_telemetry.
   PROFILES solo cubre lo que la API no manda (foto) o un astronauta sin telemetria todavia. */
const PROFILES = {
  "AST-01": {photo: "imgs/astronaut.png"}
};

const CRIT = /^(ARRITMIA_EXTREMA|TAQUICARDIA_SEVERA|HIPOXIA_CRITICA|INDICE_DE_CHOQUE_CRITICO|HIPOTENSION_SEVERA|CRISIS_HIPERTENSIVA|FIEBRE_ALTA|HIPOTERMIA|TAQUIPNEA_SEVERA|BRADIPNEA_CRITICA|DESATURACION_RAPIDA_DE_OXIGENO)$/;
const raw = d => d.raw_telemetry, der = d => d.derived_metrics || {};

/* Catalogo: para agregar una metrica nueva basta con sumar una linea aqui. */
const M = [
  {key: "hr",    label: "Frecuencia cardíaca",     unit: "lpm",  dec: 0, num: d => raw(d).hr,          re: /ARRITMIA|TAQUICARDIA|BRADICARDIA/},
  {key: "hrv",   label: "Variabilidad (RMSSD)",    unit: "ms",   dec: 1, num: d => raw(d).hrv_rmssd,   re: /VARIABILIDAD/},
  {key: "spo2",  label: "Saturación de oxígeno",   unit: "%",    dec: 1, num: d => raw(d).spo2,        re: /HIPOXIA|DESATURACION/},
  {key: "bp",    label: "Presión arterial",        unit: "mmHg", dec: 0, num: d => raw(d).sbp,         re: /HIPOTENSION|HIPERTENS/,
    text: d => raw(d).sbp.toFixed(0) + "/" + raw(d).dbp.toFixed(0)},
  {key: "temp",  label: "Temperatura",             unit: "°C",   dec: 1, num: d => raw(d).temp_c,      re: /FIEBRE|HIPOTERMIA/},
  {key: "resp",  label: "Frecuencia respiratoria", unit: "rpm",  dec: 0, num: d => raw(d).resp_rate,   re: /TAQUIPNEA|BRADIPNEA/},
  {key: "shock", label: "Índice de choque",        unit: "",     dec: 2, num: d => der(d).shock_index, re: /CHOQUE/},
  {key: "pulse", label: "Presión de pulso",        unit: "mmHg", dec: 0, num: d => der(d).pulse_pressure ?? raw(d).sbp - raw(d).dbp, re: /PULSO/},
  {key: "sleep", label: "Horas de sueño",          unit: "h",    dec: 1, num: d => raw(d).sleep_hours, re: /SUENO/}
];
const byKey = Object.fromEntries(M.map(m => [m.key, m]));
const fmt = (v, p) => v == null || Number.isNaN(v) ? "--" : Number(v).toFixed(p);

const store = new Map(), listeners = new Set(), repListeners = new Set(), reports = new Map();
let wsOn = false;

function ingest(d, dedupe) {
  const id = d.astronaut_id, ts = raw(d).timestamp;
  let st = store.get(id);
  if (!st) { st = {latest: null, ts: -Infinity, series: {}}; M.forEach(m => st.series[m.key] = []); store.set(id, st); }
  if (dedupe && ts <= st.ts) return;
  st.latest = d; st.ts = ts;
  M.forEach(m => { const s = st.series[m.key]; s.push(m.num(d)); if (s.length > KEEP) s.shift(); });
  listeners.forEach(fn => fn(id, d));
}

function metric(id, key) {
  const st = store.get(id), m = byKey[key];
  if (!st || !m) return null;
  const d = st.latest, hit = (d.clinical_triggers || []).filter(t => m.re.test(t)), v = m.num(d);
  return {key, label: m.label, unit: m.unit, value: v, text: m.text ? m.text(d) : fmt(v, m.dec),
    status: hit.some(t => CRIT.test(t)) ? "crit" : hit.length ? "warn" : "ok", triggers: hit, series: st.series[key].slice()};
}

/* Conexion unica: WebSocket con reconexion y /history como respaldo */
function socket() {
  const ws = new WebSocket(WS_URL);
  let delay = socket.delay || 1000;
  ws.onopen = () => { wsOn = true; socket.delay = 1000; };
  ws.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "telemetry") ingest(m.data);
    else if (m.type === "sbar_report") { reports.set(m.data.astronaut_id, m.data); repListeners.forEach(fn => fn(m.data)); }
  };
  ws.onclose = () => { wsOn = false; socket.delay = Math.min(delay * 1.5, 10000); setTimeout(socket, delay); };
  ws.onerror = () => ws.close();
}
async function pull() {
  try { const r = await fetch(API + "/history"); if (r.ok) (await r.json()).forEach(d => ingest(d, true)); } catch (e) { /* sin conexion */ }
}
const post = path => fetch(API + path, {method: "POST"}).then(r => r.json());
const q = id => "?astronaut_id=" + encodeURIComponent(id);

/* Estado de simulacion: lo guarda el backend (GET /stream/status). Aqui solo se consulta; nada se guarda en el navegador. */
const RUN = /^(started|running|active|simulating)$/i;
const PRED2SC = {NOMINAL: "nominal", ATAQUE_ANSIEDAD: "ansiedad", EVENTO_CARDIOVASCULAR: "cardiovascular", INFECCION_ENFERMEDAD: "infeccion"};
let sims = new Map(), simTimer = 0;
const simListeners = new Set();

/* UNICO punto que depende de la forma de la respuesta de /stream/status.
   Acepta: lista de {astronaut_id, scenario, running|status}, {streams: [...]}, o un objeto {"AST-01": {...}}.
   Devuelve Map(id -> {running, scenario}). */
function parseStreams(raw) {
  const out = new Map();
  const add = (id, e) => {
    if (!id || !e || typeof e !== "object") return;
    const run = e.running ?? e.active ?? e.simulating ?? RUN.test(e.status || "");
    out.set(id, {running: !!run, scenario: e.scenario ?? e.scenario_name ?? e.last_scenario ?? null});
  };
  const list = Array.isArray(raw) ? raw : raw && Array.isArray(raw.streams) ? raw.streams : null;
  if (list) list.forEach(e => add(e && e.astronaut_id, e));
  else if (raw && raw.astronaut_id) add(raw.astronaut_id, raw);
  else Object.entries((raw && raw.streams) || raw || {}).forEach(([id, e]) => add(id, e));
  return out;
}
async function refreshSimulations() {
  try {
    const r = await fetch(API + "/stream/status");
    if (r.ok) { sims = parseStreams(await r.json()); simListeners.forEach(fn => fn(sims)); }
  } catch (e) { /* sin conexion: se conserva el ultimo estado */ }
  return sims;
}

window.Telemetry = {
  metrics: M.map(({key, label, unit}) => ({key, label, unit})),
  ready: pull(),
  astronauts: () => [...store.keys()],
  profile: id => {
    const nombrec = store.get(id)?.latest?.raw_telemetry?.nombrec;
    return {id, name: id, photo: "imgs/astronaut.png", ...(PROFILES[id] || {}), ...(nombrec ? {name: nombrec} : {})};
  },
  setProfile: (id, p) => { PROFILES[id] = {...(PROFILES[id] || {}), ...p}; },
  latest: id => store.get(id)?.latest ?? null,
  alert: id => store.get(id)?.latest?.nasa_alert_color ?? null,
  prediction: id => store.get(id)?.latest?.primary_prediction ?? null,
  metric,
  all: id => M.map(m => metric(id, m.key)).filter(Boolean),
  report: id => reports.get(id) ?? null,
  connected: () => wsOn,
  on: fn => { listeners.add(fn); return () => listeners.delete(fn); },
  onReport: fn => { repListeners.add(fn); return () => repListeners.delete(fn); },
  start: (scenario, id = "AST-01") => post("/stream/start/" + scenario + q(id)).then(r => { refreshSimulations(); return r; }),
  shot: (scenario, id = "AST-01") => post("/simulate/" + scenario + q(id)),
  stop: (id = "AST-01") => post("/stream/stop" + q(id)).then(r => { refreshSimulations(); return r; }),
  listProfiles: () => fetch(API + "/astronauts").then(r => r.json()),
  streamStatus: () => fetch(API + "/stream/status").then(r => r.json()),
  /* Simulacion por astronauta (siempre consultada al backend) */
  isSimulating: async id => (await refreshSimulations()).get(id)?.running === true,   // Promise<boolean>
  simulation: id => sims.get(id) ?? {running: false, scenario: null},                  // ultimo estado consultado, sincrono
  lastScenario: id => sims.get(id)?.scenario ?? PRED2SC[store.get(id)?.latest?.primary_prediction] ?? "nominal",
  refreshSimulations,
  onSimulation: fn => { simListeners.add(fn); if (!simTimer) simTimer = setInterval(refreshSimulations, 2000); return () => simListeners.delete(fn); }
};

socket();
setInterval(() => { if (!wsOn) pull(); }, 2000);
})();
