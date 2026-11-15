import OLEDInterface from "./OLEDInterface.js";

const oled = new OLEDInterface();
const btn = document.getElementById("oledBtn");
const KEYS = ["hr", "hrv", "spo2", "bp", "temp", "resp", "shock", "pulse"]; // posición = código del protocolo
const astronautId = () => location.search.slice(1) || "AST-01";               // mismo ?AST-01 que usa el dashboard
let connected = false, busy = false;

function setState(on, error) {
  connected = on;
  btn.textContent = on ? "OLED conectada" : "Conectar OLED";
  btn.setAttribute("aria-pressed", on);
  btn.title = error ? error.message : "";
}

btn.addEventListener("click", async () => {
  try {
    if (connected) { await oled.disconnect(); setState(false); }
    else { await oled.connect(); setState(true); }
  } catch (e) { console.error(e); setState(false, e); }
});

Telemetry.on(async id => {
  if (!connected || busy || id !== astronautId()) return;
  busy = true;
  try {
    for (let code = 0; code < KEYS.length; code++) {
      const m = Telemetry.metric(id, KEYS[code]);
      if (m && m.value != null) await oled.write(code, code === 3 ? m.text : m.value);
    }
  } catch (e) { console.error(e); setState(false, e); }
  finally { busy = false; }
});