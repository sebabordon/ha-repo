const ZONE_LABELS = {
  corona_izq: "Corona Izq", corona_der: "Corona Der",
  frente_izq: "Frente Izq", frente_der: "Frente Der",
  sien_izq: "Sien Izq", sien_der: "Sien Der",
  ojo_izq: "Ojo Izq", ojo_der: "Ojo Der",
  mejilla_izq: "Mejilla Izq", mejilla_der: "Mejilla Der",
  mandibula: "Mandíbula",
  parietal_izq: "Parietal Izq", parietal_der: "Parietal Der",
  occipital_izq: "Occipital Izq", occipital_der: "Occipital Der",
  cuello: "Cuello"
};

const INTENSITY_COLORS = [
  "", "#22c55e", "#4ade80", "#a3e635", "#facc15", "#fbbf24",
  "#f59e0b", "#f97316", "#ef4444", "#dc2626", "#991b1b"
];

const DEFAULT_MEDS = ["Ibuprofeno", "Paracetamol", "Ketorolac", "Triptán", "Ergotamina"];
const DEFAULT_SINTOMAS = ["Náuseas", "Vómitos", "Fotofobia", "Fonofobia", "Mareos",
  "Visión borrosa", "Rigidez cervical", "Congestión nasal", "Lagrimeo", "Internación"];

let state = {
  migraines: [],
  selectedZones: [],
  selectedTipo: "",
  selectedAura: 0,
  selectedIntensity: 0,
  selectedMeds: [],
  selectedSintomas: [],
  editingId: null,
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
  calData: {},
  meds: [...DEFAULT_MEDS],
  accent: "#16213e",
  online: navigator.onLine,
  extrasOpen: false
};

// ── Offline queue (IndexedDB) ───────────────────────────────────────────────

let _idbName = "headon_offline";
const DB_VER = 1;
let _idb = null;
let _currentEmail = "";

function _setIDBForUser(email) {
  if (email && email !== _currentEmail) {
    if (_idb) { _idb.close(); _idb = null; }
    _currentEmail = email;
    _idbName = "headon_" + email.replace(/[^a-zA-Z0-9]/g, "_");
  }
}

function openIDB() {
  return new Promise((resolve, reject) => {
    if (_idb) return resolve(_idb);
    const req = indexedDB.open(_idbName, DB_VER);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains("queue"))
        db.createObjectStore("queue", { keyPath: "tempId" });
      if (!db.objectStoreNames.contains("cache"))
        db.createObjectStore("cache", { keyPath: "key" });
    };
    req.onsuccess = e => { _idb = e.target.result; resolve(_idb); };
    req.onerror = () => reject(req.error);
  });
}

async function enqueue(op) {
  const db = await openIDB();
  op.tempId = op.tempId || "t_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
  const tx = db.transaction("queue", "readwrite");
  tx.objectStore("queue").put(op);
  return new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
}

async function getQueue() {
  const db = await openIDB();
  const tx = db.transaction("queue", "readonly");
  const req = tx.objectStore("queue").getAll();
  return new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = rej; });
}

async function clearQueue() {
  const db = await openIDB();
  const tx = db.transaction("queue", "readwrite");
  tx.objectStore("queue").clear();
  return new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
}

async function cacheSet(key, value) {
  const db = await openIDB();
  const tx = db.transaction("cache", "readwrite");
  tx.objectStore("cache").put({ key, value, ts: Date.now() });
  return new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
}

async function cacheGet(key) {
  const db = await openIDB();
  const tx = db.transaction("cache", "readonly");
  const req = tx.objectStore("cache").get(key);
  return new Promise((res, rej) => {
    req.onsuccess = () => res(req.result ? req.result.value : null);
    req.onerror = rej;
  });
}

async function syncQueue() {
  const ops = await getQueue();
  if (!ops.length) return;
  try {
    const r = await fetch("/api/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ops)
    });
    if (r.ok) {
      await clearQueue();
      toast("Sincronizado correctamente");
      await loadMigraines();
    }
  } catch {}
}

// ── Init ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  buildIntensityRow();
  setDefaultDates();
  await loadUser();
  await loadConfig();
  buildMedChips();
  buildSintomaChips();
  renderMedConfig();
  await loadMigraines();
  loadVersion();

  window.addEventListener("online", () => {
    state.online = true;
    document.getElementById("offline-banner").style.display = "none";
    document.getElementById("offline-dot").style.display = "none";
    syncQueue();
  });
  window.addEventListener("offline", () => {
    state.online = false;
    document.getElementById("offline-banner").style.display = "block";
    document.getElementById("offline-dot").style.display = "";
  });
  if (!navigator.onLine) {
    document.getElementById("offline-banner").style.display = "block";
    document.getElementById("offline-dot").style.display = "";
  }
});

async function loadVersion() {
  try {
    const r = await fetch("/api/version");
    const d = await r.json();
    document.getElementById("app-version").textContent = "v" + d.version;
  } catch {}
}

async function loadUser() {
  try {
    const r = await fetch("/api/me");
    if (!r.ok) return;
    const d = await r.json();
    if (d.email) {
      _setIDBForUser(d.email);
      await openIDB();
      document.getElementById("user-email").textContent = d.email;
      if (d.is_admin)
        document.getElementById("admin-link").style.display = "";
    }
  } catch {}
}

// ── Tabs ────────────────────────────────────────────────────────────────────

function initTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      document.getElementById("tab-" + tab).classList.add("active");
      if (tab === "calendario") renderCalendar();
    });
  });
}

// ── Config ──────────────────────────────────────────────────────────────────

async function loadConfig() {
  try {
    let r = await fetch("/api/config/accent");
    let d = await r.json();
    if (d.value) { state.accent = d.value; applyAccent(d.value, false); }
    r = await fetch("/api/config/meds");
    d = await r.json();
    if (d.value) state.meds = JSON.parse(d.value);
    r = await fetch("/api/config/extras_open");
    d = await r.json();
    if (d.value === "true") state.extrasOpen = true;
    document.getElementById("cfg-extras-open").checked = state.extrasOpen;
  } catch {
    const cached = await cacheGet("meds");
    if (cached) state.meds = JSON.parse(cached);
    const cachedAccent = await cacheGet("accent");
    if (cachedAccent) applyAccent(cachedAccent, false);
  }
}

function applyAccent(color, save) {
  state.accent = color;
  document.documentElement.style.setProperty("--color-accent", color);
  document.querySelector('meta[name="theme-color"]').content = color;
  document.getElementById("cfg-accent").value = color;
  document.getElementById("cfg-accent-hex").textContent = color;
  if (save) {
    fetch("/api/config/accent", {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({value: color})
    }).catch(() => {});
    cacheSet("accent", color);
  }
}

function renderMedConfig() {
  const list = document.getElementById("cfg-meds-list");
  list.innerHTML = "";
  state.meds.forEach((m, i) => {
    const row = document.createElement("div");
    row.className = "cfg-med-item";
    const span = document.createElement("span");
    span.textContent = m;
    const btn = document.createElement("button");
    btn.className = "cfg-med-del";
    btn.textContent = "✕";
    btn.onclick = () => { state.meds.splice(i, 1); saveMeds(); renderMedConfig(); buildMedChips(); };
    row.appendChild(span);
    row.appendChild(btn);
    list.appendChild(row);
  });
}

function addMedConfig() {
  const input = document.getElementById("cfg-med-new");
  const val = input.value.trim();
  if (!val || state.meds.includes(val)) return;
  state.meds.push(val);
  input.value = "";
  saveMeds();
  renderMedConfig();
  buildMedChips();
}

function saveMeds() {
  const v = JSON.stringify(state.meds);
  fetch("/api/config/meds", {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({value: v})
  }).catch(() => {});
  cacheSet("meds", v);
}

// ── Form helpers ────────────────────────────────────────────────────────────

function setDefaultDates() {
  const today = new Date().toISOString().slice(0, 10);
  const now = new Date().toTimeString().slice(0, 5);
  document.getElementById("f-fecha").value = today;
  document.getElementById("f-inicio").value = now;
  const y = new Date().getFullYear();
  document.getElementById("exp-desde").value = y + "-01-01";
  document.getElementById("exp-hasta").value = today;
}

function showForm(ep) {
  state.editingId = null;
  state.selectedZones = [];
  state.selectedTipo = "";
  state.selectedAura = 0;
  state.selectedIntensity = 0;
  state.selectedMeds = [];
  state.selectedSintomas = [];

  const finRow = document.getElementById("f-fin-row");

  if (ep) {
    state.editingId = ep.id;
    document.getElementById("f-fecha").value = ep.fecha;
    document.getElementById("f-inicio").value = ep.inicio;
    document.getElementById("f-fin").value = ep.fin || "";
    finRow.style.display = "flex";
    state.selectedIntensity = ep.intensidad;
    state.selectedZones = Array.isArray(ep.localizacion) ? [...ep.localizacion] : [];
    state.selectedTipo = ep.tipo_dolor || "";
    state.selectedAura = ep.aura ? 1 : 0;
    state.selectedMeds = ep.medicacion ? ep.medicacion.split(", ").filter(Boolean) : [];
    state.selectedSintomas = Array.isArray(ep.sintomas) ? [...ep.sintomas] : [];
    document.getElementById("f-comentarios").value = ep.comentarios || "";
    document.querySelector(".form-title").textContent = "Editar episodio";
  } else {
    setDefaultDates();
    document.getElementById("f-fin").value = "";
    finRow.style.display = "none";
    document.getElementById("f-comentarios").value = "";
    document.querySelector(".form-title").textContent = "Registrar episodio";
  }

  // extras section
  const showExtras = state.extrasOpen || state.selectedSintomas.length > 0;
  document.getElementById("f-extras").style.display = showExtras ? "block" : "none";
  document.getElementById("extras-arrow").classList.toggle("open", showExtras);

  updateIntensityUI();
  updateZonesUI();
  updateTipoUI();
  updateAuraUI();
  buildMedChips();
  buildSintomaChips();

  document.getElementById("form-wrap").style.display = "block";
  document.getElementById("btn-nuevo").style.display = "none";
  document.getElementById("form-wrap").scrollIntoView({ behavior: "smooth" });
}

function hideForm() {
  document.getElementById("form-wrap").style.display = "none";
  document.getElementById("btn-nuevo").style.display = "block";
}

// ── Intensity ───────────────────────────────────────────────────────────────

function buildIntensityRow() {
  const row = document.getElementById("f-intensidad");
  for (let i = 1; i <= 10; i++) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "int-btn";
    btn.textContent = i;
    btn.style.color = INTENSITY_COLORS[i];
    btn.onclick = () => { state.selectedIntensity = i; updateIntensityUI(); };
    row.appendChild(btn);
  }
}

function updateIntensityUI() {
  document.querySelectorAll(".int-btn").forEach((btn, idx) => {
    const n = idx + 1;
    btn.classList.toggle("selected", n === state.selectedIntensity);
    if (n === state.selectedIntensity) {
      btn.style.background = INTENSITY_COLORS[n];
      btn.style.color = "#fff";
    } else {
      btn.style.background = "#fafafa";
      btn.style.color = INTENSITY_COLORS[n];
    }
  });
}

// ── Head zones ──────────────────────────────────────────────────────────────

function toggleZone(el) {
  if (el.tagName === "text") el = el.previousElementSibling;
  const zone = el.dataset.zone;
  if (!zone) return;
  const idx = state.selectedZones.indexOf(zone);
  if (idx >= 0) state.selectedZones.splice(idx, 1);
  else state.selectedZones.push(zone);
  updateZonesUI();
}

function updateZonesUI() {
  document.querySelectorAll(".zone").forEach(z => {
    z.classList.toggle("active", state.selectedZones.includes(z.dataset.zone));
  });
  const wrap = document.getElementById("selected-zones");
  wrap.innerHTML = "";
  state.selectedZones.forEach(z => {
    const chip = document.createElement("span");
    chip.className = "sz-chip";
    chip.textContent = ZONE_LABELS[z] || z;
    wrap.appendChild(chip);
  });
}

// ── Tipo dolor ──────────────────────────────────────────────────────────────

function selectChip(el) {
  state.selectedTipo = el.dataset.val;
  updateTipoUI();
}

function updateTipoUI() {
  document.querySelectorAll("#f-tipo .chip").forEach(c => {
    c.classList.toggle("selected", c.dataset.val === state.selectedTipo);
  });
}

// ── Aura ────────────────────────────────────────────────────────────────────

function selectAura(el) {
  state.selectedAura = parseInt(el.dataset.val);
  updateAuraUI();
}

function updateAuraUI() {
  document.querySelectorAll("#f-aura .chip").forEach(c => {
    c.classList.toggle("selected", parseInt(c.dataset.val) === state.selectedAura);
  });
}

// ── Medications ─────────────────────────────────────────────────────────────

function buildMedChips() {
  const wrap = document.getElementById("f-med-chips");
  wrap.innerHTML = "";
  state.meds.forEach(m => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (state.selectedMeds.includes(m) ? " selected" : "");
    chip.textContent = m;
    chip.onclick = () => {
      const idx = state.selectedMeds.indexOf(m);
      if (idx >= 0) state.selectedMeds.splice(idx, 1);
      else state.selectedMeds.push(m);
      chip.classList.toggle("selected");
    };
    wrap.appendChild(chip);
  });
}

// ── Save / Load ─────────────────────────────────────────────────────────────

async function saveMigraine() {
  const fecha = document.getElementById("f-fecha").value;
  const inicio = document.getElementById("f-inicio").value;
  if (!fecha || !inicio || !state.selectedIntensity) {
    toast("Completá fecha, hora e intensidad", true);
    return;
  }

  const extra = document.getElementById("f-med-extra").value.trim();
  const allMeds = [...state.selectedMeds];
  if (extra) allMeds.push(extra);

  const fin = document.getElementById("f-fin").value || undefined;
  const data = {
    fecha, inicio,
    intensidad: state.selectedIntensity,
    localizacion: state.selectedZones,
    tipo_dolor: state.selectedTipo,
    aura: state.selectedAura,
    medicacion: allMeds.join(", "),
    sintomas: state.selectedSintomas,
    comentarios: document.getElementById("f-comentarios").value.trim()
  };
  if (fin) data.fin = fin;

  if (state.online) {
    const url = state.editingId ? "/api/migraines/" + state.editingId : "/api/migraines";
    const method = state.editingId ? "PUT" : "POST";
    try {
      const r = await fetch(url, {
        method, headers: {"Content-Type":"application/json"},
        body: JSON.stringify(data)
      });
      if (r.ok) {
        toast(state.editingId ? "Episodio actualizado" : "Episodio registrado");
        hideForm();
        document.getElementById("f-med-extra").value = "";
        await loadMigraines();
        return;
      }
    } catch {}
  }

  await enqueue({
    action: state.editingId ? "update" : "create",
    id: state.editingId || undefined,
    data
  });
  toast("Guardado offline — se sincronizará al conectar");
  hideForm();
  document.getElementById("f-med-extra").value = "";
  await loadMigraines();
}

async function loadMigraines() {
  try {
    const r = await fetch("/api/migraines?limit=20");
    if (r.ok) {
      state.migraines = await r.json();
      await cacheSet("migraines", JSON.stringify(state.migraines));
    } else throw new Error();
  } catch {
    const cached = await cacheGet("migraines");
    state.migraines = cached ? JSON.parse(cached) : [];
  }
  renderMigraines();
}

async function finishEpisode(id) {
  if (state.online) {
    try {
      const r = await fetch("/api/migraines/" + id + "/finish", { method: "POST" });
      if (r.ok) { toast("Episodio finalizado"); await loadMigraines(); return; }
    } catch {}
  }
  await enqueue({ action: "finish", id, data: { fin: new Date().toTimeString().slice(0, 5) } });
  toast("Finalizado offline — se sincronizará al conectar");
  await loadMigraines();
}

async function deleteEpisode(id) {
  if (!confirm("¿Eliminar este episodio?")) return;
  if (state.online) {
    try {
      const r = await fetch("/api/migraines/" + id, { method: "DELETE" });
      if (r.ok) { toast("Eliminado"); await loadMigraines(); return; }
    } catch {}
  }
  await enqueue({ action: "delete", id });
  toast("Eliminado offline — se sincronizará al conectar");
  await loadMigraines();
}

// ── Render episodes ─────────────────────────────────────────────────────────

function renderMigraines() {
  const today = new Date().toISOString().slice(0, 10);
  const activeWrap = document.getElementById("active-episode");
  const listWrap = document.getElementById("recent-list");
  activeWrap.innerHTML = "";
  activeWrap.style.display = "none";
  listWrap.innerHTML = "";

  state.migraines.forEach(ep => {
    const isActive = ep.fecha === today && !ep.fin;
    if (isActive) {
      activeWrap.style.display = "block";
      activeWrap.innerHTML = renderActiveCard(ep);
    }
    listWrap.appendChild(renderEpisodeCard(ep, isActive));
  });

  if (!state.migraines.length) {
    listWrap.innerHTML = '<p style="color:#aaa;text-align:center;padding:2rem 0">No hay episodios registrados</p>';
  }
}

function renderActiveCard(ep) {
  return `<div class="active-banner">
    <div class="ep-header">
      <span class="active-label">⚡ Episodio activo</span>
      <span class="ep-intensity" style="background:${INTENSITY_COLORS[ep.intensidad]}">${ep.intensidad}</span>
    </div>
    <div class="ep-details">
      <span>Desde ${ep.inicio}</span>
      ${ep.tipo_dolor ? `<span>${capitalize(ep.tipo_dolor)}</span>` : ""}
    </div>
    <div class="ep-actions">
      <button class="btn btn-sm btn-primary" onclick="finishEpisode(${ep.id})">Finalizar</button>
      <button class="btn btn-sm" onclick="showForm(state.migraines.find(m=>m.id===${ep.id}))">Editar</button>
    </div>
  </div>`;
}

function renderEpisodeCard(ep, isActive) {
  const card = document.createElement("div");
  card.className = "episode-card" + (isActive ? " active-card" : "");

  const dur = calcDuration(ep);
  const zones = Array.isArray(ep.localizacion) ? ep.localizacion : [];
  const zoneChips = zones.map(z => `<span class="sz-chip">${ZONE_LABELS[z] || z}</span>`).join("");

  card.innerHTML = `
    <div class="ep-header">
      <span class="ep-date">${formatDate(ep.fecha)} · ${ep.inicio}${ep.fin ? " – " + ep.fin : ""}</span>
      <span class="ep-intensity" style="background:${INTENSITY_COLORS[ep.intensidad]}">${ep.intensidad}</span>
    </div>
    <div class="ep-details">
      ${dur ? `<span>⏱ ${dur}</span>` : ""}
      ${ep.tipo_dolor ? `<span>${capitalize(ep.tipo_dolor)}</span>` : ""}
      ${ep.aura ? "<span>✨ Aura</span>" : ""}
      ${ep.medicacion ? `<span>💊 ${ep.medicacion}</span>` : ""}
      ${(ep.sintomas && ep.sintomas.length) ? `<span>🩺 ${ep.sintomas.join(", ")}</span>` : ""}
    </div>
    ${zoneChips ? `<div class="ep-zones">${zoneChips}</div>` : ""}
    ${ep.comentarios ? `<div class="ep-details" style="margin-top:.3rem;font-style:italic">${escHtml(ep.comentarios)}</div>` : ""}
    <div class="ep-actions">
      <button class="btn btn-sm" onclick="showForm(state.migraines.find(m=>m.id===${ep.id}))">Editar</button>
      <button class="btn btn-sm btn-danger" onclick="deleteEpisode(${ep.id})">Eliminar</button>
    </div>`;
  return card;
}

function calcDuration(ep) {
  const fin = ep.fin || (ep.fecha < new Date().toISOString().slice(0, 10) ? "23:59" : null);
  if (!fin) return "";
  try {
    const [h0, m0] = ep.inicio.split(":").map(Number);
    const [h1, m1] = fin.split(":").map(Number);
    let mins = (h1 * 60 + m1) - (h0 * 60 + m0);
    if (mins < 0) mins += 24 * 60;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  } catch { return ""; }
}

// ── Calendar ────────────────────────────────────────────────────────────────

const MONTH_NAMES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

function calPrev() {
  state.calMonth--;
  if (state.calMonth < 1) { state.calMonth = 12; state.calYear--; }
  renderCalendar();
}
function calNext() {
  state.calMonth++;
  if (state.calMonth > 12) { state.calMonth = 1; state.calYear++; }
  renderCalendar();
}

async function renderCalendar() {
  document.getElementById("cal-title").textContent =
    MONTH_NAMES[state.calMonth] + " " + state.calYear;

  try {
    const r = await fetch(`/api/calendar/${state.calYear}/${state.calMonth}`);
    if (r.ok) state.calData = await r.json();
    else throw new Error();
  } catch { state.calData = {}; }

  const grid = document.getElementById("cal-days");
  grid.innerHTML = "";
  document.getElementById("cal-detail").style.display = "none";

  const first = new Date(state.calYear, state.calMonth - 1, 1);
  let dow = first.getDay();
  if (dow === 0) dow = 7;
  const daysInMonth = new Date(state.calYear, state.calMonth, 0).getDate();
  const todayStr = new Date().toISOString().slice(0, 10);

  for (let i = 1; i < dow; i++) {
    const empty = document.createElement("div");
    empty.className = "cal-day empty";
    grid.appendChild(empty);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${state.calYear}-${String(state.calMonth).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const cell = document.createElement("div");
    cell.className = "cal-day";
    if (dateStr === todayStr) cell.classList.add("today");

    const num = document.createElement("span");
    num.textContent = d;
    cell.appendChild(num);

    const entries = state.calData[dateStr];
    if (entries && entries.length) {
      const barsWrap = document.createElement("div");
      barsWrap.className = "cal-bars";
      entries.forEach(e => {
        const bar = document.createElement("div");
        bar.className = "cal-bar";
        const [h0, m0] = (e.inicio || "0:0").split(":").map(Number);
        const fin = e.fin || "23:59";
        const [h1, m1] = fin.split(":").map(Number);
        const startPct = ((h0 * 60 + m0) / 1440) * 100;
        const endPct = ((h1 * 60 + m1) / 1440) * 100;
        bar.style.left = startPct + "%";
        bar.style.width = Math.max(endPct - startPct, 3) + "%";
        bar.style.background = INTENSITY_COLORS[e.intensidad] || "#9ca3af";
        barsWrap.appendChild(bar);
      });
      cell.appendChild(barsWrap);
    }

    cell.onclick = () => showCalDetail(dateStr, entries, cell);
    grid.appendChild(cell);
  }
}

function showCalDetail(dateStr, entries, cell) {
  document.querySelectorAll(".cal-day").forEach(d => d.classList.remove("selected"));
  if (cell) cell.classList.add("selected");

  const wrap = document.getElementById("cal-detail");
  if (!entries || !entries.length) {
    wrap.style.display = "block";
    wrap.innerHTML = `<div class="cal-detail-title">${formatDate(dateStr)}</div><p style="color:#aaa">Sin episodios</p>`;
    return;
  }
  wrap.style.display = "block";
  let html = `<div class="cal-detail-title">${formatDate(dateStr)} — ${entries.length} episodio${entries.length > 1 ? "s" : ""}</div>`;
  entries.forEach(e => {
    const fin = e.fin || (dateStr < new Date().toISOString().slice(0,10) ? "23:59" : "en curso");
    html += `<div style="margin-top:.5rem;padding:.4rem .6rem;background:#fff;border-radius:6px;border:1px solid #e5e7eb">
      <span class="ep-intensity" style="background:${INTENSITY_COLORS[e.intensidad]};font-size:.7rem;width:22px;height:22px">${e.intensidad}</span>
      <span style="font-size:.85rem;margin-left:.4rem">${e.inicio} – ${fin}</span>
    </div>`;
  });
  wrap.innerHTML = html;
}

// ── Export ───────────────────────────────────────────────────────────────────

function exportExcel() {
  const desde = document.getElementById("exp-desde").value;
  const hasta = document.getElementById("exp-hasta").value;
  let url = "/api/export?";
  if (desde) url += "fecha_desde=" + desde + "&";
  if (hasta) url += "fecha_hasta=" + hasta;
  window.open(url, "_blank");
}

// ── Síntomas ────────────────────────────────────────────────────────────────

function buildSintomaChips() {
  const wrap = document.getElementById("f-sintomas");
  wrap.innerHTML = "";
  DEFAULT_SINTOMAS.forEach(s => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (state.selectedSintomas.includes(s) ? " selected" : "");
    chip.textContent = s;
    chip.onclick = () => {
      const idx = state.selectedSintomas.indexOf(s);
      if (idx >= 0) state.selectedSintomas.splice(idx, 1);
      else state.selectedSintomas.push(s);
      chip.classList.toggle("selected");
    };
    wrap.appendChild(chip);
  });
}

function toggleExtras() {
  const body = document.getElementById("f-extras");
  const arrow = document.getElementById("extras-arrow");
  const open = body.style.display === "none";
  body.style.display = open ? "block" : "none";
  arrow.classList.toggle("open", open);
}

function saveExtrasDefault(checked) {
  state.extrasOpen = checked;
  fetch("/api/config/extras_open", {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({value: checked ? "true" : "false"})
  }).catch(() => {});
}

// ── Change password ─────────────────────────────────────────────────────────

async function changePassword() {
  const current = document.getElementById("cfg-pw-current").value;
  const newPw = document.getElementById("cfg-pw-new").value;
  const confirm = document.getElementById("cfg-pw-confirm").value;
  if (!current || !newPw) { toast("Completá todos los campos", true); return; }
  if (newPw !== confirm) { toast("Las contraseñas no coinciden", true); return; }
  if (newPw.length < 8) { toast("Mínimo 8 caracteres", true); return; }
  try {
    const r = await fetch("/api/change-password", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ current, new: newPw })
    });
    const d = await r.json();
    if (d.ok) {
      toast("Contraseña actualizada");
      document.getElementById("cfg-pw-current").value = "";
      document.getElementById("cfg-pw-new").value = "";
      document.getElementById("cfg-pw-confirm").value = "";
    } else {
      toast(d.error || "Error", true);
    }
  } catch { toast("Error de conexión", true); }
}

// ── Utils ───────────────────────────────────────────────────────────────────

function formatDate(str) {
  if (!str) return "";
  const [y, m, d] = str.split("-");
  return `${d}/${m}/${y}`;
}

function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

let _toastTimer;
function toast(msg, err) {
  let el = document.getElementById("toast-bar");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-bar";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.className = "toast show " + (err ? "toast-err" : "toast-ok");
  el.textContent = msg;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 2500);
}
