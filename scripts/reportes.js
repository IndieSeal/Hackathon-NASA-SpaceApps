(function () {
"use strict";
const sameOriginAsApi = location.port === "8000" || location.port === "";
const defaultApi = sameOriginAsApi ? "" : `${location.protocol}//${location.hostname}:8000`;
const API = (new URLSearchParams(location.search).get("api") || defaultApi).replace(/\/$/, "");

const $ = id => document.getElementById(id);
const emptyEl = $("empty"), tableEl = $("table"), tbody = $("tbody");
const modalOverlay = $("modalOverlay"), modalFrame = $("modalFrame"), modalTitle = $("modalTitle");

function openPreview(pdfUrl, label) {
  modalTitle.textContent = label;
  modalFrame.src = pdfUrl;
  modalOverlay.classList.add("open");
}

function closePreview() {
  modalOverlay.classList.remove("open");
  modalFrame.src = "about:blank";
}

$("modalClose").addEventListener("click", closePreview);
modalOverlay.addEventListener("click", e => { if (e.target === modalOverlay) closePreview(); });

function renderRow(r) {
  const tr = document.createElement("tr");

  const date = document.createElement("td");
  date.textContent = new Date(r.generated_at * 1000).toLocaleString("es-MX", { hour12: false });
  tr.appendChild(date);

  const astro = document.createElement("td");
  astro.textContent = r.astronaut_id;
  tr.appendChild(astro);

  const alert = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "badge " + r.alert_color;
  badge.textContent = r.alert_color;
  alert.appendChild(badge);
  tr.appendChild(alert);

  const diag = document.createElement("td");
  diag.textContent = r.diagnosis;
  tr.appendChild(diag);

  const inf = document.createElement("td");
  inf.textContent = r.inference_time_sec.toFixed(2) + " s";
  tr.appendChild(inf);

  const actions = document.createElement("td");
  const box = document.createElement("div");
  box.className = "actions";

  if (r.pdf_filename) {
    const pdfUrl = API + "/reportes_pdf/" + encodeURIComponent(r.pdf_filename);

    const preview = document.createElement("button");
    preview.type = "button";
    preview.textContent = "Vista previa";
    preview.addEventListener("click", () => openPreview(pdfUrl, r.astronaut_id + " - " + r.pdf_filename));
    box.appendChild(preview);

    const download = document.createElement("a");
    download.href = pdfUrl;
    download.download = r.pdf_filename;
    download.textContent = "Descargar";
    box.appendChild(download);
  } else {
    const pending = document.createElement("span");
    pending.className = "muted";
    pending.textContent = "PDF no disponible";
    box.appendChild(pending);
  }

  actions.appendChild(box);
  tr.appendChild(actions);
  return tr;
}

async function load() {
  try {
    const res = await fetch(API + "/reports");
    if (!res.ok) throw new Error(String(res.status));
    const reports = (await res.json()).slice().sort((a, b) => b.generated_at - a.generated_at);

    if (!reports.length) {
      emptyEl.textContent = "Sin reportes generados todavia.";
      emptyEl.style.display = "block";
      tableEl.style.display = "none";
      return;
    }

    tbody.innerHTML = "";
    reports.forEach(r => tbody.appendChild(renderRow(r)));
    emptyEl.style.display = "none";
    tableEl.style.display = "table";
  } catch (e) {
    emptyEl.textContent = "No se pudieron cargar los reportes. Verifica que la API este disponible.";
    emptyEl.style.display = "block";
    tableEl.style.display = "none";
  }
}

load();
setInterval(load, 15000);
})();
