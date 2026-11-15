/* Interfaz multi-astronauta: foto y nombre a la izquierda; a la derecha un panel con UNA metrica
   (flechas para cambiar de metrica) y debajo el estado general Verde / Amarillo / Rojo.
   Todos los datos salen de Telemetry (scripts/telemetry.js). */
(function () {
"use strict";
const root = document.getElementById("multi");
if (!root || !window.Telemetry) return;
const T = Telemetry, $ = id => document.getElementById(id);
const cards = new Map();
const LV = {VERDE: ["ok", "Verde"], AMARILLO: ["warn", "Amarillo"], ROJO: ["crit", "Rojo"]};
const COLOR = {ok: "#3b6ef5", warn: "#d99a00", crit: "#d93a3a"};
const pretty = t => { const s = String(t || "").toLowerCase().replace(/_/g, " "); return s ? s[0].toUpperCase() + s.slice(1) : ""; };

function spark(cv, a, status) {
  const g = cv.getContext("2d"), w = cv.width, h = cv.height;
  g.clearRect(0, 0, w, h);
  a = a.filter(v => v != null);
  if (a.length < 2) return;
  const lo = Math.min(...a), hi = Math.max(...a), pad = (hi - lo) * .15 || 1;
  g.strokeStyle = COLOR[status]; g.lineWidth = 3; g.lineJoin = g.lineCap = "round"; g.beginPath();
  a.forEach((v, i) => { const x = i / (a.length - 1) * w, y = h - 8 - (v - lo + pad) / (hi - lo + 2 * pad) * (h - 16); i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.stroke();
}

function build(id) {
  const el = document.createElement("button"), p = T.profile(id);
  el.className = "mcard";
  el.innerHTML = `<div class="who"><img class="avatar" alt=""><div><b></b><span></span></div></div>
    <div class="main">
      <div class="panel">
        <div class="nav"><button class="arr" data-d="-1" aria-label="Métrica anterior">&#8249;</button><span class="label"></span><button class="arr" data-d="1" aria-label="Métrica siguiente">&#8250;</button></div>
        <div class="val"><b></b><em></em></div><canvas width="520" height="104"></canvas>
      </div>
      <div class="state">
        <i></i>
        <b></b>
        <span></span>
      </div>
    </div>`;

  const q = s => el.querySelector(s);
  q(".avatar").src = p.photo;
  q(".who b").textContent = p.name;
  q(".who span").textContent = id;
  
  const c = {
    el, i: 0, panel: q(".panel"), label: q(".label"), val: q(".val b"), unit: q(".val em"), cv: q("canvas"),
    state: q(".state"),
    sname: q(".state b"),
    sdesc: q(".state span")
  };

  el.querySelectorAll(".arr").forEach(b => b.addEventListener("click", () => {
    c.i = (c.i + Number(b.dataset.d) + T.metrics.length) % T.metrics.length; paint(id);
  }));

  // Ir a dashboard con ID de astronauta
  el.onclick = () => onAstronautClicked(id);

  cards.set(id, c);
  root.appendChild(el);
  
  const e = $("mEmpty"); if (e) e.remove();
  return c;
}

function onAstronautClicked(id){
  window.location.href = `/index.html?${id}`;
}

function paint(id) {
  const c = cards.get(id) || build(id), m = T.metric(id, T.metrics[c.i].key);
  if (!m) return;
  c.label.textContent = m.label;
  c.val.textContent = m.text;
  c.unit.textContent = m.unit;
  c.panel.dataset.status = m.status;
  
  const [cls, name] = LV[T.alert(id)] || ["", "Sin datos"];
  c.state.className = "state " + cls;
  c.sname.textContent = name;
  c.sdesc.textContent = pretty(T.prediction(id));
  
  //Set status to selected option from each of the astronauts

  spark(c.cv, m.series, m.status);
}

T.on(id => paint(id));
T.ready.then(() => T.astronauts().forEach(paint));

/* Controles: una tarjeta fija por astronauta, cada una con su propio escenario e inicio/detener */
const SCENARIOS = [["nominal", "Nominal"], ["ansiedad", "Ansiedad"], ["cardiovascular", "Cardiovascular"], ["infeccion", "Infección"]];

async function buildControls() {
  const grid = $("ctrlGrid");
  if (!grid) return;
  let profiles = [];
  try { profiles = await T.listProfiles(); } catch (e) { /* sin conexion */ }
  
  try{
    const r = await fetch(API + "/stream/status"); if (!r.ok) throw 0;
    const list = await r.json();
    
    list.slice(-25).forEach(d => {
      console.log(d.scenario);
    });

    grid.innerHTML = "";
    profiles.forEach(p => {
      const card = document.createElement("div");
      card.className = "ctrl-card";
      card.innerHTML = `<b></b><span class="ctrl-id muted"></span>
        <select aria-label="Escenario"></select>
        <div class="ctrl-actions">
          <button class="ghost start">Iniciar</button>
          <button class="ghost stop">Detener</button>
        </div>`;
      card.querySelector("b").textContent = p.nombrec;
      card.querySelector(".ctrl-id").textContent = p.astronaut_id;
      const select = card.querySelector("select");
      SCENARIOS.forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
      });

      card.querySelector(".start").addEventListener("click", () => T.start(select.value, p.astronaut_id));
      card.querySelector(".stop").addEventListener("click", () => T.stop(p.astronaut_id));
      grid.appendChild(card);
    });
  }
  catch{

  }
}

buildControls();
setInterval(() => { const on = T.connected(); $("mConn").className = "dot" + (on ? " on" : ""); $("mConnTxt").textContent = on ? "En vivo" : "Sondeo cada 2 s"; }, 1000);
})();
