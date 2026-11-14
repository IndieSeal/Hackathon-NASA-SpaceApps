(function () {
"use strict";
const $ = id => document.getElementById(id);
const svg = $("body"), tip = $("tip"), lensA = $("lensA"), lensM = $("lensM");
const N = 30;
const H = {hr: [], hrv: [], spo2: [], resp: [], sbp: [], temp: []};
const CRIT = /^(ARRITMIA_EXTREMA|TAQUICARDIA_SEVERA|HIPOXIA_CRITICA|INDICE_DE_CHOQUE_CRITICO|HIPOTENSION_SEVERA|CRISIS_HIPERTENSIVA|FIEBRE_ALTA|HIPOTERMIA|TAQUIPNEA_SEVERA|BRADIPNEA_CRITICA|DESATURACION_RAPIDA_DE_OXIGENO)$/;
const LBL = {ok: "Normal", warn: "Atención", crit: "Crítico"};
const f = (v, p = 0) => v == null ? "--" : Number(v).toFixed(p);
const pc = (d, k) => f((d.probabilities[k] || 0) * 100) + "%";
const pretty = t => { const s = t.toLowerCase().replace(/_/g, " "); return s[0].toUpperCase() + s.slice(1); };

/* Sistemas del cuerpo: zonas sensibles [x, y, radio] en coordenadas del SVG */
const SYS = {
  brain: {name: "Cerebro", sub: "Sueño y estrés", hits: [[490, 135, 72]], re: /SUENO/, pred: "ATAQUE_ANSIEDAD",
    spark: "hrv", cap: "Variabilidad cardíaca, reflejo del estrés",
    big: t => [f(t.sleep_hours, 1), "h de sueño"],
    rows: (t, m, d) => [["Ansiedad", pc(d, "ATAQUE_ANSIEDAD")], ["Fatiga circadiana", pc(d, "FATIGA_CIRCADIANA")]]},
  lungs: {name: "Pulmones", sub: "Respiración y oxígeno", hits: [[430, 355, 52], [552, 345, 50]], re: /HIPOXIA|DESATURACION|TAQUIPNEA|BRADIPNEA/,
    spark: "spo2", cap: "Saturación de oxígeno, últimos registros",
    big: t => [f(t.spo2, 1), "% SpO2"],
    rows: t => [["Frecuencia respiratoria", f(t.resp_rate) + " rpm"]]},
  heart: {name: "Corazón", sub: "Ritmo cardíaco", hits: [[512, 405, 42]], re: /ARRITMIA|TAQUICARDIA|BRADICARDIA|VARIABILIDAD|CHOQUE/, pred: "EVENTO_CARDIOVASCULAR",
    ecg: true, cap: "Latido simulado con la frecuencia actual",
    big: t => [f(t.hr), "lpm"],
    rows: (t, m) => [["Variabilidad (RMSSD)", f(t.hrv_rmssd, 1) + " ms"], ["Índice de choque", f(m.shock_index, 2)]]},
  vessels: {name: "Circulación", sub: "Presión arterial", hits: [[652, 400, 50], [328, 400, 50], [490, 720, 70]], re: /HIPOTENSION|HIPERTENSION|PULSO/,
    spark: "sbp", cap: "Presión sistólica, últimos registros",
    big: t => [f(t.sbp) + "/" + f(t.dbp), "mmHg"],
    rows: (t, m) => [["Presión de pulso", f(m.pulse_pressure ?? t.sbp - t.dbp) + " mmHg"]]},
  core: {name: "Temperatura", sub: "Termorregulación e inmunidad", hits: [[498, 558, 60]], re: /FIEBRE|HIPOTERMIA/, pred: "INFECCION_ENFERMEDAD",
    spark: "temp", cap: "Temperatura corporal, últimos registros",
    big: t => [f(t.temp_c, 1), "°C"],
    rows: (t, m, d) => [["Riesgo de infección", pc(d, "INFECCION_ENFERMEDAD")]]}
};

let D = null, active = null, hr = 70, raf = 0, last = 0, acc = 0, phase = 0;
const buf = new Array(180).fill(0);

function status(k) {
  if (!D) return ["ok", []];
  const s = SYS[k], hit = (D.clinical_triggers || []).filter(t => s.re.test(t));
  if (hit.some(t => CRIT.test(t))) return ["crit", hit];
  return [hit.length || D.primary_prediction === s.pred ? "warn" : "ok", hit];
}
function paint(k) {
  $("o-" + k).setAttribute("class", "organ " + k + " " + status(k)[0] + (k === active ? " on" : ""));
}

const head = (s, st) => `<div class="th"><div><b>${s.name}</b><span>${s.sub}</span></div>${st ? `<i class="st ${st}">${LBL[st]}</i>` : ""}</div>`;
function fill() {
  const s = SYS[active];
  if (!D) { tip.innerHTML = head(s, "") + '<div class="cap">Sin telemetría todavía. Elige un escenario para iniciar.</div>'; return; }
  const t = D.raw_telemetry, m = D.derived_metrics || {}, [st, hit] = status(active), [v, u] = s.big(t);
  hr = t.hr || 70;
  tip.innerHTML = head(s, st) +
    `<div class="big">${s.ecg ? `<i class="pulse" style="animation-duration:${60 / hr}s"></i>` : ""}<b>${v}</b><span>${u}</span></div>` +
    `<canvas width="456" height="112"></canvas><div class="cap">${s.cap}</div>` +
    `<dl>${s.rows(t, m, D).map(r => `<div><dt>${r[0]}</dt><dd>${r[1]}</dd></div>`).join("")}</dl>` +
    (hit.length ? `<div class="found">${hit.map(pretty).join(", ")}</div>` : "");
}

/* Latido: complejo PQRST sintético a la frecuencia cardíaca real */
const gs = (x, m, s, a) => a * Math.exp(-((x - m) ** 2) / (2 * s * s));
const wave = p => gs(p, .16, .025, .12) + gs(p, .30, .008, -.12) + gs(p, .33, .011, 1) + gs(p, .365, .010, -.25) + gs(p, .62, .05, .28);
function line(g, a, w, h, lo, hi) {
  if (a.length < 2) return;
  g.beginPath();
  a.forEach((v, i) => { const x = i / (a.length - 1) * w, y = h - 10 - (v - lo) / (hi - lo || 1) * (h - 20); i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.stroke();
}
function loop(ts) {
  if (!active) { raf = 0; return; }
  const dt = Math.min((ts - last) / 1000, .1); last = ts;
  const c = tip.querySelector("canvas");
  if (c && D) {
    const g = c.getContext("2d"), w = c.width, h = c.height, s = SYS[active];
    g.clearRect(0, 0, w, h); g.lineWidth = 3; g.lineJoin = g.lineCap = "round";
    if (s.ecg) {
      acc += dt * 60;
      while (acc >= 1) { acc--; phase = (phase + hr / 3600) % 1; buf.push(wave(phase)); buf.shift(); }
      g.strokeStyle = "#d93a3a"; line(g, buf, w, h, -.3, 1.1);
    } else {
      const a = H[s.spark], lo = Math.min(...a), hi = Math.max(...a), pad = (hi - lo) * .15 || 1;
      g.strokeStyle = "#3b6ef5"; line(g, a, w, h, lo - pad, hi + pad);
    }
  }
  raf = requestAnimationFrame(loop);
}

function setActive(k) {
  if (k === active) return;
  const old = active; active = k;
  if (old) paint(old);
  tip.classList.toggle("show", !!k);
  if (k) { paint(k); fill(); if (!raf) { last = performance.now(); raf = requestAnimationFrame(loop); } }
}
function place(e) {
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 24, y = e.clientY - h / 2;
  if (x + w > innerWidth - 8) x = e.clientX - w - 24;
  y = Math.max(8, Math.min(y, innerHeight - h - 8));
  tip.style.transform = `translate(${x}px,${y}px)`;
}
function move(e) {
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
  [lensA, lensM].forEach(c => { c.setAttribute("cx", p.x); c.setAttribute("cy", p.y); });
  let best = null, bd = 1;
  for (const k in SYS) for (const [x, y, r] of SYS[k].hits) {
    const d = Math.hypot(p.x - x, p.y - y) / r;
    if (d < bd) { bd = d; best = k; }
  }
  setActive(best);
  if (best) place(e);
}
svg.addEventListener("pointermove", move);
svg.addEventListener("pointerdown", move);
svg.addEventListener("pointerleave", () => {
  [lensA, lensM].forEach(c => { c.setAttribute("cx", -500); c.setAttribute("cy", -500); });
  setActive(null);
});

window.addEventListener("telemetry", e => {
  D = e.detail;
  const t = D.raw_telemetry;
  [["hr", "hr"], ["hrv", "hrv_rmssd"], ["spo2", "spo2"], ["resp", "resp_rate"], ["sbp", "sbp"], ["temp", "temp_c"]]
    .forEach(([k, s]) => { H[k].push(t[s]); if (H[k].length > N) H[k].shift(); });
  $("o-heart").style.setProperty("--beat", 60 / (t.hr || 70) + "s");
  Object.keys(SYS).forEach(paint);
  if (active) fill();
});
})();
