import OLEDInterface from "./OLEDInterface.js";

const oled = new OLEDInterface();
const btn = document.getElementById("oledBtn");
const KEYS = ["hr", "hrv", "spo2", "bp", "temp", "resp", "shock", "pulse"]; // posición = código del protocolo
const DELAY_MS = 1000;   // cada cuánto se manda el paquete completo
const STALE_MS = 5000;   // sin lecturas por este tiempo, deja de mandar
let lastReading = 0;

oled.onError = e => { console.error(e); setState(false, e); oled.disconnect().catch(() => {}); };

const astronautId = () => location.search.slice(1) || "AST-01";
let connected = false;

function setState(on, error) {
  connected = on;
  btn.textContent = on ? "OLED conectada" : "Conectar OLED";
  btn.setAttribute("aria-pressed", on);
}

btn.addEventListener("click", async () => {
  try {
    if (connected) {
      await oled.disconnect();
      setState(false);
    }
    else {
        await oled.connect();
        oled.onError = e => { console.error(e); setState(false, e); };
        oled.start(updates, DELAY_MS);
        setState(true);
    }
  } 
  catch (e) {
    console.error(e);
    setState(false, e);
  }
});

Telemetry.on(id => { if (id === astronautId()) lastReading = Date.now(); });
const updates = () => {
  if (Date.now() - lastReading > STALE_MS) return [];
  const id = astronautId();
  return KEYS.flatMap((key, code) => {
    const m = Telemetry.metric(id, key);
    return m && m.value != null ? [[code, code === 3 ? m.text : m.value]] : [];
  });
};