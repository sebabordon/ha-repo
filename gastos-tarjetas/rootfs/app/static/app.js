const BASE = window.INGRESS_PREFIX || "";
if (window.APP_VERSION) {
  const el = document.getElementById("app-version");
  if (el) el.textContent = "v" + window.APP_VERSION;
}

// ── UI settings (colors + prefs) applied immediately from localStorage ────────
const UI_COLOR_DEFAULTS = {
  ars: "#15803d", usd: "#2563eb", rg: "#94a3b8", tog: "#d97706", accent: "#16213e"
};
const UI_PREF_DEFAULTS = {
  dias_urgente:       3,
  dias_pronto:        7,
  graf_meses:         "6",
  graf_moneda:        "ARS",
  font_size:          14,
  venc_show_proximos: true,
  venc_show_rg5617:   true,
  venc_show_pdf_ref:  true,
};

function getUiPref(key) {
  const stored = JSON.parse(localStorage.getItem("ui_prefs") || "{}");
  return key in stored ? stored[key] : UI_PREF_DEFAULTS[key];
}

function applyUiColors() {
  const stored = JSON.parse(localStorage.getItem("ui_colors") || "{}");
  const c = { ...UI_COLOR_DEFAULTS, ...stored };
  const root = document.documentElement;
  root.style.setProperty("--color-ars",       c.ars);
  root.style.setProperty("--color-usd",       c.usd);
  root.style.setProperty("--color-rg5617",    c.rg);
  root.style.setProperty("--color-toggle-rg", c.tog);
  root.style.setProperty("--color-accent",    c.accent);
}

function applyUiPrefs() {
  // Font size
  const fs = getUiPref("font_size");
  document.documentElement.style.fontSize = fs + "px";
  // Chart defaults — set select values now so loadCharts() picks them up
  const mSel = document.getElementById("cf-meses");
  const monSel = document.getElementById("cf-moneda");
  if (mSel)   mSel.value   = getUiPref("graf_meses");
  if (monSel) monSel.value = getUiPref("graf_moneda");
}

applyUiColors();
applyUiPrefs();

// v0.2.35: unified sign convention — positive monto = egreso for ALL sources.
/** Devuelve true si el movimiento es un egreso (dinero que sale). */
function _isEgreso(monto) {
  return parseFloat(monto) > 0;
}

// ── Palette ───────────────────────────────────────────────────────────────────
const PALETTE = [
  "#6366f1","#22c55e","#f59e0b","#ef4444","#3b82f6",
  "#ec4899","#14b8a6","#f97316","#8b5cf6","#84cc16",
  "#06b6d4","#a855f7","#eab308","#10b981","#f43f5e",
];

// ── Toast / notifications ─────────────────────────────────────────────────────
function showToast(msg, type = "ok", duration = 3500) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span class="toast-msg">${escHtml(msg)}</span>
    <button class="toast-close" onclick="this.closest('.toast').classList.remove('show')">✕</button>`;
  el.className = `toast toast-${type} show`;
  clearTimeout(el._t);
  if (duration > 0) el._t = setTimeout(() => el.classList.remove("show"), duration);
}

function showConfirm(msg, onConfirm) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span class="toast-msg">${escHtml(msg)}</span>
    <button class="btn btn-sm btn-danger" id="t-ok">Confirmar</button>
    <button class="btn btn-sm" onclick="document.getElementById('toast').classList.remove('show')">Cancelar</button>`;
  el.className = "toast toast-warn show";
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 8000);
  document.getElementById("t-ok").onclick = () => { el.classList.remove("show"); onConfirm(); };
}

function showPrompt(msg, placeholder, onConfirm) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span class="toast-msg">${escHtml(msg)}</span>
    <input id="t-inp" type="text" placeholder="${escHtml(placeholder)}">
    <button class="btn btn-sm btn-primary" id="t-ok">OK</button>
    <button class="btn btn-sm" onclick="document.getElementById('toast').classList.remove('show')">✕</button>`;
  el.className = "toast toast-info show";
  clearTimeout(el._t);
  const inp = document.getElementById("t-inp");
  const ok  = () => { const v = inp.value.trim(); el.classList.remove("show"); if (v) onConfirm(v); };
  document.getElementById("t-ok").onclick = ok;
  inp.addEventListener("keydown", e => { if (e.key === "Enter") ok(); if (e.key === "Escape") el.classList.remove("show"); });
  setTimeout(() => inp.focus(), 30);
}

function showSelectPrompt(msg, options, onConfirm) {
  const el = document.getElementById("toast");
  const opts = options.map(o => `<option value="${o.value}">${escHtml(o.label)}</option>`).join("");
  el.innerHTML = `<span class="toast-msg">${escHtml(msg)}</span>
    <select id="t-sel" style="padding:.25rem .4rem;border:1px solid #93c5fd;border-radius:4px;font-size:.88rem">${opts}</select>
    <button class="btn btn-sm btn-primary" id="t-ok">OK</button>
    <button class="btn btn-sm" onclick="document.getElementById('toast').classList.remove('show')">✕</button>`;
  el.className = "toast toast-info show";
  clearTimeout(el._t);
  const sel = document.getElementById("t-sel");
  const ok  = () => { const v = sel.value; el.classList.remove("show"); onConfirm(v); };
  document.getElementById("t-ok").onclick = ok;
  sel.addEventListener("keydown", e => { if (e.key === "Enter") ok(); if (e.key === "Escape") el.classList.remove("show"); });
  setTimeout(() => sel.focus(), 30);
}

// ── Main tabs ─────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "graficos")    loadCharts();
    if (tab.dataset.tab === "presupuesto") { loadPresupuesto(); loadPresupuestoUsuario(); }
    if (tab.dataset.tab === "config")      { loadRules(); loadMatchRules(); renderUsuarios(); renderUserRules(); loadCuentas(); renderUiSettings(); renderScrapersConfig(); renderPwaShortcuts(); }
  });
});

// ── Config sub-tabs ───────────────────────────────────────────────────────────
function switchCfgTab(id) {
  document.querySelectorAll(".cfg-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".cfg-tab-content").forEach(p => p.classList.remove("active"));
  const btn   = document.querySelector(`.cfg-tab[data-cfgtab="${id}"]`);
  const panel = document.getElementById(`cfg-tab-${id}`);
  if (btn)   btn.classList.add("active");
  if (panel) panel.classList.add("active");
}
document.querySelectorAll(".cfg-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    switchCfgTab(tab.dataset.cfgtab);
    if (tab.dataset.cfgtab === "scrapers") renderScrapersConfig();
  });
});

// ── Config inner-accordion (expandable sections within sub-tabs) ──────────────
function toggleCfgSection(id) {
  const body  = document.getElementById(`cfg-body-${id}`);
  const arrow = document.getElementById(`cfg-arr-${id}`);
  if (!body) return;
  const open = body.style.display !== "none";
  body.style.display = open ? "none" : "";
  if (arrow) arrow.textContent = open ? "+" : "−";
}

// ── UI settings (Interfaz tab) ────────────────────────────────────────────────
function renderUiSettings() {
  // Colors
  const storedC = JSON.parse(localStorage.getItem("ui_colors") || "{}");
  const c = { ...UI_COLOR_DEFAULTS, ...storedC };
  ["ars","usd","rg","tog","accent"].forEach(k => {
    const picker = document.getElementById(`ui-col-${k}`);
    const hex    = document.getElementById(`ui-hex-${k}`);
    if (picker) picker.value = c[k];
    if (hex)    hex.value   = c[k];
  });
  // Prefs
  const storedP = JSON.parse(localStorage.getItem("ui_prefs") || "{}");
  const p = { ...UI_PREF_DEFAULTS, ...storedP };
  const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  const setChk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };
  const fsEl = document.getElementById("ui-font-size");
  const fsVal = document.getElementById("ui-font-size-val");
  if (fsEl)  fsEl.value = p.font_size;
  if (fsVal) fsVal.textContent = p.font_size + "px";
  setVal("ui-graf-meses",    p.graf_meses);
  setVal("ui-graf-moneda",   p.graf_moneda);
  setVal("ui-dias-urgente",  p.dias_urgente);
  setVal("ui-dias-pronto",   p.dias_pronto);
  setChk("ui-venc-show-proximos", p.venc_show_proximos);
  setChk("ui-venc-show-rg5617",   p.venc_show_rg5617);
  setChk("ui-venc-show-pdf-ref",  p.venc_show_pdf_ref);
  _updateUiPreview();
}

function syncColorHex(key) {
  const picker = document.getElementById(`ui-col-${key}`);
  const hex    = document.getElementById(`ui-hex-${key}`);
  if (hex && picker) hex.value = picker.value;
  _updateUiPreview();
}

function syncColorPicker(key) {
  const picker = document.getElementById(`ui-col-${key}`);
  const hex    = document.getElementById(`ui-hex-${key}`);
  if (hex && picker && /^#[0-9a-fA-F]{6}$/.test(hex.value)) picker.value = hex.value;
  _updateUiPreview();
}

function syncFontSize() {
  const el  = document.getElementById("ui-font-size");
  const lbl = document.getElementById("ui-font-size-val");
  if (!el) return;
  const px = parseInt(el.value, 10);
  if (lbl) lbl.textContent = px + "px";
  document.documentElement.style.fontSize = px + "px";   // live preview
}

function _getUiColorInputs() {
  const get = k => {
    const h = document.getElementById(`ui-hex-${k}`);
    return (h && /^#[0-9a-fA-F]{6}$/.test(h.value)) ? h.value : UI_COLOR_DEFAULTS[k];
  };
  return { ars: get("ars"), usd: get("usd"), rg: get("rg"), tog: get("tog"), accent: get("accent") };
}

function _getUiPrefInputs() {
  const num  = (id, def) => { const el = document.getElementById(id); return el ? parseInt(el.value,10)||def : def; };
  const sel  = (id, def) => { const el = document.getElementById(id); return el ? el.value : def; };
  const chk  = (id, def) => { const el = document.getElementById(id); return el ? el.checked : def; };
  return {
    dias_urgente:       num("ui-dias-urgente",  UI_PREF_DEFAULTS.dias_urgente),
    dias_pronto:        num("ui-dias-pronto",   UI_PREF_DEFAULTS.dias_pronto),
    graf_meses:         sel("ui-graf-meses",    UI_PREF_DEFAULTS.graf_meses),
    graf_moneda:        sel("ui-graf-moneda",   UI_PREF_DEFAULTS.graf_moneda),
    font_size:          num("ui-font-size",     UI_PREF_DEFAULTS.font_size),
    venc_show_proximos: chk("ui-venc-show-proximos", true),
    venc_show_rg5617:   chk("ui-venc-show-rg5617",   true),
    venc_show_pdf_ref:  chk("ui-venc-show-pdf-ref",  true),
  };
}

function _updateUiPreview() {
  const c = _getUiColorInputs();
  const set = (cls, color) => document.querySelectorAll(cls).forEach(el => el.style.color = color);
  set(".ui-prev-ars", c.ars);
  set(".ui-prev-usd", c.usd);
  set(".ui-prev-rg",  c.rg);
  set(".ui-prev-tog", c.tog);
  document.querySelectorAll(".ui-prev-accent").forEach(el => el.style.background = c.accent);
}

function saveUiSettings() {
  const c = _getUiColorInputs();
  const p = _getUiPrefInputs();
  localStorage.setItem("ui_colors", JSON.stringify(c));
  localStorage.setItem("ui_prefs",  JSON.stringify(p));
  applyUiColors();
  applyUiPrefs();
  loadVencimientos();   // refresh widget with new thresholds & visibility prefs
  showToast("Configuración guardada.", "ok", 2500);
}

function resetUiSettings() {
  localStorage.removeItem("ui_colors");
  localStorage.removeItem("ui_prefs");
  applyUiColors();
  applyUiPrefs();
  renderUiSettings();
  loadVencimientos();
  showToast("Configuración restablecida.", "ok", 2500);
}

// ── Scroll-to-top button ──────────────────────────────────────────────────────
window.addEventListener("scroll", () => {
  const btn = document.getElementById("btn-scroll-top");
  if (btn) btn.classList.toggle("visible", window.scrollY > 200);
});

// ── PWA service worker ────────────────────────────────────────────────────────
if (!window.INGRESS_PREFIX && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js")
      .catch(err => console.warn("SW registration failed:", err));
  });
}

// ── User info ─────────────────────────────────────────────────────────────────
fetch(`${BASE}/auth/me`).then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
  if (u.is_admin) {
    const link = document.getElementById("admin-link");
    link.href = `${BASE}/admin`;
    link.style.display = "";
  }
});

// ── Monthly overview chart ────────────────────────────────────────────────────
let _monthlyChart = null;

async function loadMonthlyChart() {
  let data;
  try {
    const res = await fetch(`${BASE}/api/gastos/monthly`);
    data = await res.json();
  } catch(e) {
    console.error("loadMonthlyChart error:", e);
    // Ensure chart system can still proceed even if this request fails
    if (!_monthFilterReady) {
      _monthFilterReady = true;
      _filtersReadyForCharts = true;
      _checkInitialChartLoad();
    }
    return;
  }
  _populateMonthFilter(data.map(d => d.mes));

  const labels   = data.map(d => _fmtMes(d.mes));
  const egresos  = data.map(d => d.egresos);
  const ingresos = data.map(d => d.ingresos);
  const ctx = document.getElementById("monthly-chart").getContext("2d");

  if (_monthlyChart) {
    _monthlyChart.data.labels = labels;
    _monthlyChart.data.datasets[0].data = egresos;
    _monthlyChart.data.datasets[1].data = ingresos;
    _monthlyChart.update();
    return;
  }
  _monthlyChart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [
      { label:"Egresos",  data:egresos,  backgroundColor:"rgba(220,80,60,.75)",  borderColor:"rgba(200,50,40,1)",  borderWidth:1, borderRadius:3 },
      { label:"Ingresos", data:ingresos, backgroundColor:"rgba(34,180,120,.75)", borderColor:"rgba(20,140,90,1)", borderWidth:1, borderRadius:3 },
    ]},
    options: { responsive:true, maintainAspectRatio:true,
      plugins:{ legend:{position:"top"},
        tooltip:{ callbacks:{ label: c => ` ${c.dataset.label}: ${_fmtNum(c.raw)}` }}},
      scales:{ y:{ ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v }}}},
  });
}

function _fmtMes(ym) {
  const [y,m] = ym.split("-");
  return ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][+m-1]+` ${y.slice(2)}`;
}
function _fmtNum(n) {
  return (+n||0).toLocaleString("es-AR",{minimumFractionDigits:0,maximumFractionDigits:0});
}
function _fmtNum2(n) {
  return (+n||0).toLocaleString("es-AR",{minimumFractionDigits:2,maximumFractionDigits:2});
}
function _fmtSaldo(n) {
  const v = +n || 0;
  const dec = Math.abs(v) >= 10000 ? 0 : 2;
  return v.toLocaleString("es-AR",{minimumFractionDigits:dec,maximumFractionDigits:dec});
}

let _monthFilterReady = false;

function _populateMonthFilter(meses) {
  const today = new Date().toISOString().slice(0, 7); // "YYYY-MM"

  // Gastos/presupuesto: mes activo (puede ser el corriente, con datos parciales)
  const defaultActive = meses.filter(m => m <= today).at(-1) || meses.at(-1) || "";
  // Gráficos: último mes *cerrado* (estrictamente anterior al mes en curso)
  const defaultClosed = meses.filter(m => m < today).at(-1) || defaultActive;

  const initialDefaults = { "filter-mes": defaultActive, "cf-mes": defaultClosed, "presup-mes": defaultActive };

  ["filter-mes","cf-mes","presup-mes"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    meses.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m; opt.textContent = _fmtMes(m);
      sel.appendChild(opt);
    });
    // After first load: always restore whatever the user had (including "" = Todos).
    // On first load only: auto-select the appropriate default per selector.
    if (_monthFilterReady) sel.value = current;
    else if (current)      sel.value = current;
    else                   sel.value = initialDefaults[id] || defaultActive;
  });

  // Trigger initial loads now that the month filters are set
  if (!_monthFilterReady) {
    _monthFilterReady = true;
    loadGastos();
    _filtersReadyForCharts = true;
    _checkInitialChartLoad();
  }
}

// Coordinate initial load: charts need both layout AND month filter ready
let _layoutReady      = false;
let _filtersReadyForCharts = false;
function _checkInitialChartLoad() {
  if (_layoutReady && _filtersReadyForCharts) loadCharts();
}

loadMonthlyChart(); // triggers _populateMonthFilter → loadGastos + sets _filtersReadyForCharts
loadChartLayout();  // fetches layout, rebuilds grid, sets _layoutReady

// ── Charts tab ────────────────────────────────────────────────────────────────
const _charts = {};
let _crossFilterCat = null;

// Consistent color map built by _drawDonut so all charts share the same
// category→color assignment.
const _categoryColors = {};
function _catColor(cat, fallbackIdx) {
  return _categoryColors[cat] || PALETTE[fallbackIdx % PALETTE.length];
}

function setCrossFilter(cat) {
  if (_crossFilterCat === cat) { clearCrossFilter(); return; }
  _crossFilterCat = cat;
  const badge = document.getElementById("cross-filter-badge");
  document.getElementById("cross-filter-label").textContent = cat;
  badge.style.display = "";
  loadCharts();
}
function clearCrossFilter() {
  _crossFilterCat = null;
  document.getElementById("cross-filter-badge").style.display = "none";
  loadCharts();
}

function _chartParams() {
  const p = new URLSearchParams();
  const fuente     = document.getElementById("cf-fuente").value;
  const usuario    = document.getElementById("cf-usuario").value;
  const mes        = document.getElementById("cf-mes").value;
  const meses      = document.getElementById("cf-meses").value;
  const moneda     = document.getElementById("cf-moneda").value;
  const excluirEsp = document.getElementById("chk-excluir-especiales-graf")?.checked ?? true;
  if (fuente)          p.set("fuente",    fuente);
  if (usuario)         p.set("usuario",   usuario);
  if (mes)             p.set("mes",       mes);
  else                 p.set("meses",     meses);
  if (moneda)          p.set("moneda",    moneda);
  if (_crossFilterCat) p.set("categoria", _crossFilterCat);
  p.set("excluir_especiales", excluirEsp ? "true" : "false");
  return p;
}

async function loadCharts() {
  const res  = await fetch(`${BASE}/api/stats?${_chartParams()}`);
  const data = await res.json();

  // The category donut always shows ALL categories (so the gray dimming makes
  // sense). When cross-filtering we make a second call without the categoria
  // param so we get the full list, then dim non-selected slices client-side.
  if (_crossFilterCat) {
    const p = new URLSearchParams(_chartParams().toString());
    p.delete("categoria");
    const res2 = await fetch(`${BASE}/api/stats?${p}`);
    const data2 = await res2.json();
    _drawDonut(data2.by_category);
  } else {
    _drawDonut(data.by_category);
  }
  _drawTopDesc(data.top_descriptions);
  _drawMonthlyCat(data.monthly_by_category);
  _drawByFuente(data.by_fuente);
  _drawByUsuario(data.by_usuario);
  loadForecast();
  // Draw any custom charts that are in the layout
  for (const cid of _chartLayout) {
    if (cid.startsWith("custom_")) _drawCustomChart(cid);
  }
}

// ── Chart layout & custom charts ─────────────────────────────────────────────
let _chartLayout    = [];
let _customChartsMap = {};

const _FIXED_META = {
  category:    { title:"Egresos por categoría",             totalId:"total-category",    full:false },
  top_desc:    { title:"Top 15 descripciones",              totalId:"total-top-desc",    full:false },
  monthly_cat: { title:"Egresos por categoría — mes a mes", totalId:"total-monthly-cat", full:true  },
  fuente:      { title:"Egresos por fuente",                totalId:"total-fuente",      full:false },
  usuario:     { title:"Egresos por persona",               totalId:"total-usuario",     full:false },
  forecast:    { title:"Forecast — próximos meses",                                      full:true  },
};

const _FIXED_CANVAS = {
  category:    "chart-by-category",
  top_desc:    "chart-top-desc",
  monthly_cat: "chart-monthly-cat",
  fuente:      "chart-by-fuente",
  usuario:     "chart-by-usuario",
  forecast:    "chart-forecast",
};

const _DEFAULT_LAYOUT_IDS = ["category", "top_desc", "monthly_cat", "fuente", "usuario", "forecast"];

async function loadChartLayout() {
  try {
    const res  = await fetch(`${BASE}/api/charts/layout`);
    const data = await res.json();
    _chartLayout = (data.layout && data.layout.length > 0) ? data.layout : [..._DEFAULT_LAYOUT_IDS];
    _customChartsMap = {};
    (data.custom || []).forEach(c => { _customChartsMap[`custom_${c.id}`] = c; });
  } catch(e) {
    console.error("loadChartLayout error:", e);
    if (!_chartLayout.length) _chartLayout = [..._DEFAULT_LAYOUT_IDS];
    _customChartsMap = {};
  }
  try { rebuildChartsGrid(); } catch(e) { console.error("rebuildChartsGrid error:", e); }
  _layoutReady = true;
  _checkInitialChartLoad();
}

function rebuildChartsGrid() {
  // Destroy existing Chart.js instances
  Object.values(_charts).forEach(c => { try { c.destroy(); } catch(_){} });
  Object.keys(_charts).forEach(k => delete _charts[k]);

  const grid = document.getElementById("charts-grid");
  grid.innerHTML = "";
  _chartLayout.forEach((cid, idx) => {
    const box = _buildChartBox(cid, idx, _chartLayout.length);
    if (box) grid.appendChild(box);
  });
  // Populate cm-mes and cm-usuario options (for the modal)
  _refreshModalSelects();
}

function _buildChartBox(cid, idx, total) {
  const meta   = _FIXED_META[cid];
  const custom = _customChartsMap[cid];
  if (!meta && !custom) return null;

  const title   = meta ? meta.title : custom.nombre;
  const totalId = meta?.totalId || null;
  const isFull  = meta ? meta.full : false;

  const div = document.createElement("div");
  div.className = `chart-box${isFull ? " chart-box-full" : ""}`;
  div.dataset.chartId = cid;

  const first = idx === 0, last = idx === total - 1;
  const ctrlsHtml = `
    <div class="chart-ctrls">
      <button class="chart-ctrl-btn" onclick="moveChart('${cid}',-1)" title="Mover izquierda" ${first?"disabled":""}>←</button>
      <button class="chart-ctrl-btn" onclick="moveChart('${cid}', 1)" title="Mover derecha"   ${last ?"disabled":""}>→</button>
      ${!meta ? `
        <button class="chart-ctrl-btn" onclick="editCustomChart('${cid}')" title="Editar">✎</button>
        <button class="chart-ctrl-btn chart-ctrl-del" onclick="deleteCustomChart('${cid}')" title="Eliminar">✕</button>
      ` : ""}
    </div>`;

  const headerHtml = `
    <div class="chart-box-header">
      <div class="chart-box-title">${escHtml(title)}<span class="chart-total"${totalId?` id="${totalId}"`:""}></span></div>
      ${ctrlsHtml}
    </div>`;

  if (cid === "forecast") {
    div.innerHTML = headerHtml + `
      <div style="display:flex;gap:1rem;align-items:center;margin-bottom:.6rem;flex-wrap:wrap;font-size:.85rem;color:#666">
        <label>Proyección:
          <select id="cf-forecast-meses" onchange="this.blur();loadForecast()">
            <option value="6" selected>6 meses</option><option value="12">12 meses</option>
          </select>
        </label>
        <label>Basado en:
          <select id="cf-forecast-historico" onchange="this.blur();loadForecast()">
            <option value="3" selected>Últimos 3 meses</option><option value="6">Últimos 6 meses</option>
          </select>
        </label>
        <div id="forecast-exclude-wrap" style="display:flex;align-items:center;gap:.35rem;flex-wrap:wrap">
          <span>Excluir de ingresos:</span>
          <span id="forecast-exclude-chips" style="display:inline-flex;flex-wrap:wrap;gap:.25rem"></span>
          <button id="btn-forecast-exclude-add" class="btn btn-sm" style="padding:.15rem .5rem;font-size:.82rem">+</button>
        </div>
      </div>
      <canvas id="chart-forecast"></canvas>`;
    // Re-bind exclude button (was lost on DOM rebuild)
    setTimeout(() => {
      document.getElementById("btn-forecast-exclude-add")?.addEventListener("click", _onForecastExcludeAdd);
      _renderForecastExcludes();
    }, 0);
  } else if (cid === "top_desc") {
    div.innerHTML = headerHtml + `<div id="top-desc-wrap" style="position:relative"><canvas id="chart-top-desc"></canvas></div>`;
  } else if (meta) {
    div.innerHTML = headerHtml + `<canvas id="${_FIXED_CANVAS[cid]}"></canvas>`;
  } else {
    // Custom chart
    div.innerHTML = headerHtml + `<canvas id="chart-custom-${custom.id}"></canvas>`;
  }
  return div;
}

function moveChart(cid, dir) {
  const idx = _chartLayout.indexOf(cid);
  if (idx < 0) return;
  const ni = idx + dir;
  if (ni < 0 || ni >= _chartLayout.length) return;
  [_chartLayout[idx], _chartLayout[ni]] = [_chartLayout[ni], _chartLayout[idx]];
  _saveLayout();
  rebuildChartsGrid();
  loadCharts();
}

function _saveLayout() {
  return fetch(`${BASE}/api/charts/layout`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({layout: _chartLayout}),
  });
}

// ── Custom chart draw ─────────────────────────────────────────────────────────
async function _drawCustomChart(cid) {
  const c = _customChartsMap[cid];
  if (!c) return;
  const filtros = c.filtros || {};
  const p = new URLSearchParams();
  p.set("dimension", c.dimension);
  p.set("metrica",   c.metrica);

  const mes    = filtros.mes     || document.getElementById("cf-mes").value;
  const meses  = filtros.meses   || document.getElementById("cf-meses").value;
  const fuente = filtros.fuente  || document.getElementById("cf-fuente").value;
  const usr    = filtros.usuario || document.getElementById("cf-usuario").value;
  const moneda = filtros.moneda  || document.getElementById("cf-moneda").value;
  const excl   = document.getElementById("chk-excluir-especiales-graf")?.checked ?? true;

  if (mes)            p.set("mes",     mes);
  else                p.set("meses",   meses);
  if (fuente)         p.set("fuente",  fuente);
  if (usr)            p.set("usuario", usr);
  if (moneda)         p.set("moneda",  moneda);
  if (filtros.categoria) p.set("categoria", filtros.categoria);
  if (_crossFilterCat)   p.set("categoria", _crossFilterCat);
  p.set("excluir_especiales", excl ? "true" : "false");

  const res  = await fetch(`${BASE}/api/stats/pivot?${p}`);
  const data = await res.json();
  const rows = data.data || [];

  const canvasId = `chart-custom-${c.id}`;
  const canvas   = document.getElementById(canvasId);
  if (!canvas) return;

  const labels = rows.map(r => r.label);
  const values = rows.map(r => r.valor);
  const ttl    = values.reduce((s, v) => s + v, 0);

  const titleSpan = canvas.closest(".chart-box")?.querySelector(".chart-total");
  if (titleSpan) titleSpan.textContent = ttl ? ` — ${_fmtNum2(ttl)}` : "";

  if (_charts[canvasId]) { try { _charts[canvasId].destroy(); } catch(_){} }

  const MET = {egresos:"Egresos", ingresos:"Ingresos", cantidad:"Cantidad"};
  const tipo = c.tipo || "bar";
  const baseOpts = {
    responsive:true, maintainAspectRatio:true,
    plugins:{ legend:{display:false},
      tooltip:{callbacks:{label: ctx => ` ${_fmtNum(ctx.raw)}`}} },
    scales:{ y:{ticks:{callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v}} },
  };

  const bgColors = labels.map((l, i) => _catColor(l, i));

  if (tipo === "doughnut" || tipo === "pie") {
    _charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type: tipo,
      data: { labels, datasets:[{ data:values,
        backgroundColor:bgColors, borderWidth:2, borderColor:"#fff" }] },
      options:{ responsive:true, maintainAspectRatio:true,
        plugins:{ legend:{position:"right",labels:{boxWidth:12,font:{size:11}}},
          tooltip:{callbacks:{label: ctx => ` ${ctx.label}: ${_fmtNum(ctx.raw)}`}} } },
    });
  } else if (tipo === "line") {
    _charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type:"line",
      data:{ labels, datasets:[{ label:MET[c.metrica]||c.metrica, data:values,
        borderColor:PALETTE[0], backgroundColor:PALETTE[0]+"33",
        fill:true, tension:.3, pointRadius:4 }] },
      options:{...baseOpts, plugins:{...baseOpts.plugins, legend:{display:false}}},
    });
  } else {
    _charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type:"bar",
      data:{ labels, datasets:[{ label:MET[c.metrica]||c.metrica, data:values,
        backgroundColor:bgColors, borderRadius:4 }] },
      options: baseOpts,
    });
  }
}

// ── Custom chart modal ────────────────────────────────────────────────────────
let _editingChartCid = null;

function _refreshModalSelects() {
  // Populate cm-mes from existing month options
  const cmMes = document.getElementById("cm-mes");
  if (cmMes) {
    const current = cmMes.value;
    while (cmMes.options.length > 1) cmMes.remove(1);
    const src = document.getElementById("cf-mes");
    if (src) [...src.options].forEach(o => { if (o.value) { const n = new Option(o.text, o.value); cmMes.appendChild(n); } });
    if (current) cmMes.value = current;
  }
  // Populate cm-usuario from _usuariosConfig
  const cmUsr = document.getElementById("cm-usuario");
  if (cmUsr) {
    while (cmUsr.options.length > 1) cmUsr.remove(1);
    (_usuariosConfig.usuarios || ["Titular","Adicional"]).forEach(u => {
      cmUsr.appendChild(new Option(u, u));
    });
  }
}

function openChartModal(cid) {
  _editingChartCid = cid || null;
  const c = cid ? _customChartsMap[cid] : null;
  document.getElementById("chart-modal-title").textContent = c ? "Editar chart" : "Nuevo chart";
  document.getElementById("cm-nombre").value    = c?.nombre    || "";
  document.getElementById("cm-tipo").value      = c?.tipo      || "bar";
  document.getElementById("cm-dimension").value = c?.dimension || "categoria";
  document.getElementById("cm-metrica").value   = c?.metrica   || "egresos";
  const f = c?.filtros || {};
  _refreshModalSelects();
  document.getElementById("cm-mes").value      = f.mes      || "";
  document.getElementById("cm-fuente").value   = f.fuente   || "";
  document.getElementById("cm-usuario").value  = f.usuario  || "";
  document.getElementById("cm-categoria").value = f.categoria || "";
  document.getElementById("chart-modal").style.display = "";
}

function closeChartModal() {
  document.getElementById("chart-modal").style.display = "none";
  _editingChartCid = null;
}

async function saveChartModal() {
  const nombre = document.getElementById("cm-nombre").value.trim();
  if (!nombre) { showToast("Ingresá un nombre para el chart", "err"); return; }
  const filtros = {};
  const mes      = document.getElementById("cm-mes").value;
  const fuente   = document.getElementById("cm-fuente").value;
  const usuario  = document.getElementById("cm-usuario").value;
  const categoria = document.getElementById("cm-categoria").value.trim();
  if (mes)       filtros.mes      = mes;
  if (fuente)    filtros.fuente   = fuente;
  if (usuario)   filtros.usuario  = usuario;
  if (categoria) filtros.categoria = categoria;

  const body = {
    nombre,
    tipo:      document.getElementById("cm-tipo").value,
    dimension: document.getElementById("cm-dimension").value,
    metrica:   document.getElementById("cm-metrica").value,
    filtros,
  };

  if (_editingChartCid) {
    const id = parseInt(_editingChartCid.replace("custom_",""));
    await fetch(`${BASE}/api/charts/custom/${id}`, {
      method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body),
    });
  } else {
    const res  = await fetch(`${BASE}/api/charts/custom`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body),
    });
    const data = await res.json();
    const newCid = `custom_${data.id}`;
    _chartLayout.push(newCid);
    await _saveLayout();
  }

  closeChartModal();
  await loadChartLayout();
  loadCharts();
}

function editCustomChart(cid) { openChartModal(cid); }

async function deleteCustomChart(cid) {
  if (!confirm("¿Eliminar este chart?")) return;
  const id = parseInt(cid.replace("custom_",""));
  await fetch(`${BASE}/api/charts/custom/${id}`, {method:"DELETE"});
  _chartLayout = _chartLayout.filter(c => c !== cid);
  await _saveLayout();
  await loadChartLayout();
  loadCharts();
}

function _destroyAndCreate(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas) { console.warn(`_destroyAndCreate: canvas #${id} not found`); return; }
  if (_charts[id]) { try { _charts[id].destroy(); } catch(_){} }
  _charts[id] = new Chart(canvas.getContext("2d"), config);
}

function _drawDonut(data) {
  const total = data.reduce((s, d) => s + (d.total || 0), 0);
  const _tc = document.getElementById("total-category");
  if (_tc) _tc.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  const top = data.slice(0, 12);
  // Build / refresh the global color map so other charts stay in sync
  top.forEach((d, i) => { _categoryColors[d.categoria] = PALETTE[i % PALETTE.length]; });
  _destroyAndCreate("chart-by-category", {
    type: "doughnut",
    data: {
      labels:   top.map(d => d.categoria),
      datasets: [{ data: top.map(d => d.total),
        backgroundColor: top.map(d =>
          _crossFilterCat && d.categoria !== _crossFilterCat
            ? "#d1d5db"
            : _categoryColors[d.categoria]),
        borderWidth: 2, borderColor: "#fff" }],
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      onClick: (_, elements) => {
        if (!elements.length) return;
        setCrossFilter(top[elements[0].index].categoria);
      },
      plugins: {
        legend: { position: "right", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: c => ` ${c.label}: ${_fmtNum(c.raw)}`,
            footer: () => "Click para filtrar",
          },
        },
      },
    },
  });
}

function _drawTopDesc(data) {
  const d = data.slice(0, 15);
  const total = d.reduce((s, r) => s + (r.total || 0), 0);
  const _tt = document.getElementById("total-top-desc");
  if (_tt) _tt.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  // Fix height on the wrapper BEFORE creating the chart so Chart.js reads
  // a stable size and doesn't enter a grow loop.
  const wrap = document.getElementById("top-desc-wrap");
  if (wrap) wrap.style.height = Math.max(240, d.length * 26 + 40) + "px";

  _destroyAndCreate("chart-top-desc", {
    type: "bar",
    data: {
      labels:   d.map(r => r.descripcion.length > 28 ? r.descripcion.slice(0,27)+"…" : r.descripcion),
      datasets: [{ label:"ARS", data: d.map(r => r.total),
        backgroundColor: PALETTE[2], borderRadius: 3 }],
    },
    options: {
      indexAxis: "y",
      responsive: true, maintainAspectRatio: false,
      plugins: { legend:{ display:false },
        tooltip:{ callbacks:{ label: c => ` ${_fmtNum(c.raw)}` }} },
      scales: { x:{ ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v }},
                y:{ ticks:{ font:{ size:10 } }} },
    },
  });
}

function _drawMonthlyCat(rows) {
  const total = rows.reduce((s, r) => s + (r.total || 0), 0);
  const _tm = document.getElementById("total-monthly-cat");
  if (_tm) _tm.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  const months = [...new Set(rows.map(r => r.mes))].sort();
  const cats   = [...new Map(
    rows.sort((a,b)=>b.total-a.total).map(r=>[r.categoria, r.total])
  ).entries()].slice(0, 10).map(([c]) => c);

  const datasets = cats.map((cat, i) => ({
    label: cat,
    data:  months.map(m => { const f = rows.find(r=>r.mes===m&&r.categoria===cat); return f?f.total:0; }),
    backgroundColor: _catColor(cat, i),
    borderRadius: 2, borderWidth: 0,
  }));

  _destroyAndCreate("chart-monthly-cat", {
    type: "bar",
    data: { labels: months.map(_fmtMes), datasets },
    options: {
      responsive: true, maintainAspectRatio: true,
      onClick: (_, elements) => {
        if (!elements.length) return;
        setCrossFilter(cats[elements[0].datasetIndex]);
      },
      plugins: {
        legend: {
          position:"top", labels:{ boxWidth:12, font:{size:11} },
          onClick: (e, item) => { setCrossFilter(item.text); },
        },
        tooltip: {
          mode:"index",
          callbacks:{
            label: c => ` ${c.dataset.label}: ${_fmtNum(c.raw)}`,
            footer: () => "Click para filtrar",
          },
        },
      },
      scales: {
        x: { stacked: true },
        y: { stacked: true, ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v } },
      },
    },
  });
}

function _drawByFuente(data) {
  const total = data.reduce((s, d) => s + (d.total || 0), 0);
  const _tf = document.getElementById("total-fuente");
  if (_tf) _tf.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  _destroyAndCreate("chart-by-fuente", {
    type: "bar",
    data: {
      labels:   data.map(d => d.fuente.replace("_"," ")),
      datasets: [{ label:"ARS", data: data.map(d => d.total),
        backgroundColor: data.map((_,i) => PALETTE[i % PALETTE.length]), borderRadius:4 }],
    },
    options: {
      responsive:true, maintainAspectRatio:true,
      onClick: (_, elements) => {
        if (!elements.length) return;
        const fuente = data[elements[0].index].fuente;
        const sel = document.getElementById("cf-fuente");
        sel.value = sel.value === fuente ? "" : fuente;
        loadCharts();
      },
      plugins:{ legend:{display:false},
        tooltip:{callbacks:{
          label: c => ` ${_fmtNum(c.raw)}`,
          footer: () => "Click para filtrar por fuente",
        }} },
      scales:{ y:{ ticks:{callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v} } },
    },
  });
}

function _drawByUsuario(data) {
  const total = data.reduce((s, d) => s + (d.total || 0), 0);
  const _tu = document.getElementById("total-usuario");
  if (_tu) _tu.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  _destroyAndCreate("chart-by-usuario", {
    type: "doughnut",
    data: {
      labels:   data.map(d => d.usuario),
      datasets: [{ data: data.map(d => d.total),
        backgroundColor: [PALETTE[0], PALETTE[3], PALETTE[4], PALETTE[7]],
        borderWidth:2, borderColor:"#fff" }],
    },
    options: {
      responsive:true, maintainAspectRatio:true,
      onClick: (_, elements) => {
        if (!elements.length) return;
        const usr = data[elements[0].index].usuario;
        const sel = document.getElementById("cf-usuario");
        sel.value = sel.value === usr ? "" : usr;
        loadCharts();
      },
      plugins:{ legend:{position:"bottom"},
        tooltip:{callbacks:{
          label: c => ` ${c.label}: ${_fmtNum(c.raw)}`,
          footer: () => "Click para filtrar por persona",
        }} },
    },
  });
}

["cf-fuente","cf-usuario","cf-mes","cf-meses","cf-moneda"].forEach(id =>
  document.getElementById(id).addEventListener("change", function() { this.blur(); loadCharts(); }));
document.getElementById("btn-refresh-charts").addEventListener("click", loadCharts);

// ── Category slicer ───────────────────────────────────────────────────────────
let _selectedCats = new Set();
let _sinCat = false;

async function loadCategorias() {
  const res = await fetch(`${BASE}/api/categorias`);
  const cats = await res.json();
  renderCatChips(cats);
}

let _catList = [];   // global list used by the gastos-table custom autocomplete

function renderCatChips(cats) {
  _catList = cats;   // keep a copy for the custom autocomplete
  // Populate shared datalist for other fields (new-mov form, chart modal)
  const dl = document.getElementById("cat-datalist");
  if (dl) dl.innerHTML = cats.map(c => `<option value="${escHtml(c)}"></option>`).join("");

  const container = document.getElementById("cat-chips");
  const allActive = !_sinCat && _selectedCats.size === 0;
  container.innerHTML = `<span class="cat-chip cat-todos ${allActive?"active":""}" onclick="toggleAllCats()">Todas</span>`;
  // "Sin categoría" special chip
  const sinChip = document.createElement("span");
  sinChip.className = `cat-chip cat-sincat${_sinCat?" active":""}`;
  sinChip.textContent = "Sin categoría";
  sinChip.onclick = () => toggleSinCat();
  container.appendChild(sinChip);
  // Regular chips
  cats.forEach(cat => {
    const chip = document.createElement("span");
    chip.className = `cat-chip${_selectedCats.has(cat)?" active":""}`;
    chip.textContent = cat;
    chip.title = "Click para filtrar · Doble clic para renombrar";
    chip.onclick = () => toggleCat(cat);
    chip.ondblclick = (e) => { e.stopPropagation(); startRenameCat(chip, cat); };
    container.appendChild(chip);
  });
}

function startRenameCat(chip, oldCat) {
  const inp = document.createElement("input");
  inp.type = "text";
  inp.value = oldCat;
  inp.className = "tag-edit-input";
  inp.style.cssText = "font-size:.8rem;padding:.2rem .5rem;border-radius:12px;min-width:80px;max-width:200px";
  inp.title = "Enter para guardar · Esc para cancelar · Vacío para limpiar";

  let saved = false;
  async function doSave() {
    if (saved) return; saved = true;
    const newCat = inp.value.trim();
    if (newCat === oldCat) { loadCategorias(); return; }
    const res = await fetch(`${BASE}/api/categorias/rename`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({old: oldCat, new: newCat}),
    });
    const data = res.ok ? await res.json() : {};
    if (res.ok) {
      const msg = newCat
        ? `✓ "${oldCat}" → "${newCat}" (${data.actualizados} gastos)`
        : `✓ Categoría "${oldCat}" eliminada de ${data.actualizados} gastos`;
      showToast(msg, "ok", 3000);
      if (_selectedCats.has(oldCat)) {
        _selectedCats.delete(oldCat);
        if (newCat) _selectedCats.add(newCat);
      }
    } else {
      showToast("Error al renombrar categoría", "err");
    }
    loadCategorias();
    loadGastos();
  }
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); doSave(); }
    if (e.key === "Escape") { saved = true; loadCategorias(); }
  });
  inp.addEventListener("blur", doSave);
  chip.replaceWith(inp);
  inp.focus(); inp.select();
}

function toggleSinCat() {
  _sinCat = !_sinCat;
  if (_sinCat) _selectedCats.clear();
  document.querySelectorAll(".cat-chip:not(.cat-todos):not(.cat-sincat)").forEach(c => c.classList.remove("active"));
  document.querySelector(".cat-sincat")?.classList.toggle("active", _sinCat);
  document.querySelector(".cat-todos")?.classList.toggle("active", !_sinCat && _selectedCats.size === 0);
  loadGastos();
}

function toggleCat(cat) {
  _sinCat = false;
  if (_selectedCats.has(cat)) _selectedCats.delete(cat); else _selectedCats.add(cat);
  document.querySelectorAll(".cat-chip:not(.cat-todos):not(.cat-sincat)").forEach(c =>
    c.classList.toggle("active", _selectedCats.has(c.textContent)));
  document.querySelector(".cat-sincat")?.classList.remove("active");
  document.querySelector(".cat-todos")?.classList.toggle("active", _selectedCats.size === 0);
  loadGastos();
}
function toggleAllCats() {
  _sinCat = false;
  _selectedCats.clear();
  document.querySelectorAll(".cat-chip").forEach(c => c.classList.remove("active"));
  document.querySelector(".cat-todos")?.classList.add("active");
  loadGastos();
}

loadCategorias();

// ── Filter toggle ─────────────────────────────────────────────────────────────
document.getElementById("btn-toggle-filters").addEventListener("click", function () {
  const panel = document.getElementById("filter-panel");
  const open  = panel.style.display !== "none";
  panel.style.display = open ? "none" : "";
  this.textContent = open ? "Filtros ▾" : "Filtros ▴";
  this.setAttribute("aria-expanded", !open);
  // Hide import filter row too when collapsing the whole filter panel
  if (open) {
    const importRow = document.getElementById("import-filter-row");
    const importBtn = document.getElementById("btn-toggle-import-filter");
    importRow.style.display = "none";
    importBtn.textContent = "+";
    importBtn.setAttribute("aria-expanded", "false");
  }
});

document.getElementById("btn-toggle-import-filter").addEventListener("click", function () {
  const row  = document.getElementById("import-filter-row");
  const open = row.style.display !== "none";
  row.style.display = open ? "none" : "";
  this.textContent = open ? "+" : "−";
  this.setAttribute("aria-expanded", !open);
  // Reset import filter when hiding
  if (!open) {
    document.getElementById("filter-import").focus();
  } else {
    const sel = document.getElementById("filter-import");
    if (sel.value) { sel.value = ""; loadGastos(); }
  }
});

// ── Gastos ────────────────────────────────────────────────────────────────────
function _gastosParams() {
  const p = new URLSearchParams();
  const fuente    = document.getElementById("filter-fuente").value;
  const usuario   = document.getElementById("filter-usuario").value;
  const mes       = document.getElementById("filter-mes").value;
  const moneda    = document.getElementById("filter-moneda").value;
  const importId  = document.getElementById("filter-import")?.value;
  const excluirEsp = document.getElementById("chk-excluir-especiales")?.checked;
  if (fuente)    p.set("fuente",    fuente);
  if (usuario)   p.set("usuario",   usuario);
  if (mes)       p.set("mes",       mes);
  if (moneda)    p.set("moneda",    moneda);
  if (importId)  p.set("import_id", importId);
  if (excluirEsp) p.set("excluir_especiales", "true");
  if (_sinCat) {
    p.set("sin_categoria", "true");
  } else if (_selectedCats.size > 0) {
    p.set("categorias", [..._selectedCats].join(","));
  }
  return p;
}

let _gastosData = [];
let _gastosSort = {col: null, dir: 1};

function sortGastos(col) {
  if (_gastosSort.col === col) _gastosSort.dir *= -1;
  else { _gastosSort.col = col; _gastosSort.dir = col === "monto" ? -1 : 1; }
  _renderGastos();
}

async function loadGastos() {
  const res  = await fetch(`${BASE}/api/gastos?${_gastosParams()}`);
  _gastosData = await res.json();
  _renderGastos();
}

function _renderGastos() {
  let gastos = _gastosData;

  // Sort client-side
  if (_gastosSort.col) {
    const col = _gastosSort.col, dir = _gastosSort.dir;
    gastos = [...gastos].sort((a, b) => {
      let va = a[col], vb = b[col];
      if (col === "monto") { va = Math.abs(parseFloat(va)||0); vb = Math.abs(parseFloat(vb)||0); }
      if (typeof va === "string" || typeof vb === "string")
        return dir * (va||"").localeCompare(vb||"", "es");
      return dir * ((va||0) - (vb||0));
    });
  }

  // Update sort indicators
  ["fecha","descripcion","monto","usuario","categoria"].forEach(c => {
    const el = document.getElementById(`gsort-${c}`);
    if (el) el.textContent = _gastosSort.col === c ? (_gastosSort.dir > 0 ? "▲" : "▼") : "";
  });

  const tbody  = document.getElementById("gastos-body");
  tbody.innerHTML = "";

  if (!gastos.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#aaa;padding:2rem">Sin movimientos</td></tr>`;
    document.getElementById("gastos-summary").textContent = "";
    return;
  }

  // Normalized summary: always show egresos/ingresos as positive amounts
  let egARS = 0, inARS = 0, egUSD = 0, inUSD = 0;
  gastos.forEach(g => {
    const abs = Math.abs(parseFloat(g.monto));
    const eg  = _isEgreso(g.monto);
    if (g.moneda === "ARS") { if (eg) egARS += abs; else inARS += abs; }
    else if (g.moneda === "USD") { if (eg) egUSD += abs; else inUSD += abs; }
  });
  let summary = `${gastos.length} movimientos`;
  if (egARS)  summary += ` — Egresos ARS ${_fmtNum2(egARS)}`;
  if (inARS)  summary += ` · Ingresos +${_fmtNum2(inARS)}`;
  if (egUSD)  summary += ` — Egresos USD ${_fmtNum2(egUSD)}`;
  if (inUSD)  summary += ` · Ingresos +${_fmtNum2(inUSD)}`;
  document.getElementById("gastos-summary").textContent = summary;

  gastos.forEach(g => {
    const tr = document.createElement("tr");
    const u = g.usuario || "";
    const egreso = _isEgreso(g.monto);
    const displayMonto = Math.abs(parseFloat(g.monto));
    const displayStr   = egreso ? _fmtNum2(displayMonto) : `+${_fmtNum2(displayMonto)}`;
    tr.innerHTML = `
      <td><input class="fecha-input" data-id="${g.id}" type="date" value="${g.fecha}"></td>
      <td>${escHtml(g.descripcion)}</td>
      <td class="monto ${g.moneda==="USD"?"usd":""} ${egreso?"egreso":"ingreso"}">${displayStr}</td>
      <td class="col-moneda">${g.moneda}</td>
      <td><span class="badge badge-${g.fuente}">${g.fuente.replace("_"," ")}</span></td>
      <td>
        <select class="usuario-select" onchange="saveUsuario(${g.id},this)">
          <option value="" ${!u?"selected":""}>—</option>
          ${(_usuariosConfig.usuarios||["Titular","Adicional"]).map(usr=>`<option value="${escHtml(usr)}" ${u===usr?"selected":""}>${escHtml(usr)}</option>`).join("")}
        </select>
      </td>
      <td>
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria||"")}"
          title="${g.categoria_fuente?"Fuente: "+g.categoria_fuente:""}"
          autocomplete="off" spellcheck="false" />
      </td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-action" onclick="saveCategoria(${g.id},this)">✓</button>
        ${g.tipo==="manual"?`<button class="btn btn-sm btn-action btn-danger" title="Eliminar movimiento manual" onclick="deleteGasto(${g.id})">✕</button>`:`<button class="btn btn-sm btn-action" style="visibility:hidden">✕</button>`}
      </td>`;

    const catInput   = tr.querySelector(".cat-input");
    const saveBtn    = tr.querySelector("td:last-child .btn");
    const fechaInput = tr.querySelector(".fecha-input");
    const origCat    = catInput.value;
    const origFecha  = fechaInput.value;

    _setupCatAC(catInput, origCat, saveBtn, g.id);

    fechaInput.addEventListener("change", () => {
      if (fechaInput.value !== origFecha) saveFecha(g.id, fechaInput);
    });

    tbody.appendChild(tr);
  });
}

// ── Gastos-table category autocomplete ───────────────────────────────────────
// Custom floating dropdown so full category names are always readable,
// and Escape always cancels (restores the original value).
function _setupCatAC(input, origCat, saveBtn = null, gastoId = null) {
  let acEl  = null;
  let acIdx = -1;

  function _notifyChange() {
    const changed = input.value !== origCat;
    input.classList.toggle("dirty", changed);
    if (saveBtn) saveBtn.classList.toggle("btn-dirty", changed);
  }

  function _showAC() {
    _hideAC();
    const q = (input.value || "").toLowerCase();
    const matches = _catList.filter(c => c.toLowerCase().includes(q));
    if (!matches.length) return;

    acEl = document.createElement("div");
    acEl.className = "cat-ac";
    acEl.innerHTML = matches.map((c, i) =>
      `<div class="cat-ac-item" data-i="${i}" data-val="${escHtml(c)}">${escHtml(c)}</div>`
    ).join("");

    // Float below the input, wide enough to show full names
    const rect = input.getBoundingClientRect();
    acEl.style.top      = (rect.bottom + window.scrollY) + "px";
    acEl.style.left     = (rect.left   + window.scrollX) + "px";
    acEl.style.minWidth = Math.max(rect.width, 220) + "px";
    document.body.appendChild(acEl);
    acIdx = -1;

    acEl.querySelectorAll(".cat-ac-item").forEach(item => {
      item.addEventListener("mousedown", e => {
        e.preventDefault();           // keep input focused
        input.value = item.dataset.val;
        _notifyChange();
        _hideAC();
      });
    });
  }

  function _hideAC() {
    if (acEl) { acEl.remove(); acEl = null; }
    acIdx = -1;
  }

  function _highlight(delta) {
    if (!acEl) return;
    const items = acEl.querySelectorAll(".cat-ac-item");
    if (!items.length) return;
    acIdx = Math.max(0, Math.min(items.length - 1, acIdx + delta));
    items.forEach((el, i) => el.classList.toggle("active", i === acIdx));
    items[acIdx].scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("focus", _showAC);
  input.addEventListener("input", () => { _notifyChange(); _showAC(); });
  input.addEventListener("blur",  () => setTimeout(_hideAC, 160));

  input.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      e.preventDefault();
      input.value = origCat;          // always undo the edit
      _notifyChange();
      _hideAC();
      input.blur();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (acEl && acIdx >= 0) {
        const item = acEl.querySelectorAll(".cat-ac-item")[acIdx];
        if (item) { input.value = item.dataset.val; _notifyChange(); }
      }
      _hideAC();
      if (gastoId !== null) saveCategoria(gastoId, saveBtn);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!acEl) _showAC();
      else _highlight(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      _highlight(-1);
    }
  });
}

async function saveCategoria(id, btn) {
  const input = document.querySelector(`.cat-input[data-id="${id}"]`);
  const res   = await fetch(`${BASE}/api/gastos/${id}/categoria`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({categoria: input.value}),
  });
  if (res.ok) {
    input.classList.remove("dirty"); btn.classList.remove("btn-dirty");
    loadMonthlyChart();
  }
  btn.textContent = res.ok ? "✓" : "✗";
  setTimeout(() => btn.textContent = "✓", 1500);
}

async function saveFecha(id, input) {
  const res = await fetch(`${BASE}/api/gastos/${id}/fecha`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({fecha: input.value}),
  });
  if (res.ok) {
    input.classList.remove("dirty");
    showToast("Fecha actualizada.", "ok", 1500);
    loadMonthlyChart();
  } else {
    showToast("Error al guardar fecha.", "err");
  }
}

async function saveUsuario(id, sel) {
  await fetch(`${BASE}/api/gastos/${id}/usuario`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({usuario: sel.value}),
  });
}

["filter-fuente","filter-usuario","filter-mes","filter-moneda","filter-import"].forEach(id =>
  document.getElementById(id).addEventListener("change", function() { this.blur(); loadGastos(); }));
document.getElementById("chk-excluir-especiales").addEventListener("change", loadGastos);
document.getElementById("chk-excluir-especiales-graf").addEventListener("change", loadCharts);
document.getElementById("btn-load").addEventListener("click", loadGastos);
document.getElementById("btn-export").addEventListener("click", () =>
  window.open(`${BASE}/api/gastos/export?${_gastosParams()}`, "_blank"));

// Initial loadGastos() is triggered by _populateMonthFilter (called from loadMonthlyChart)
// so it runs with the auto-selected month filter already set.

// ── Nuevo movimiento manual (desde Gastos) ────────────────────────────────────
async function _populateNmCuentas() {
  const res     = await fetch(`${BASE}/api/cuentas`);
  const cuentas = await res.json();
  const sel     = document.getElementById("nm-cuenta");
  const manual  = cuentas.filter(c => c.tipo === "manual");
  sel.innerHTML = `<option value="" data-moneda="">— Cuenta manual —</option>` +
    manual.map(c => `<option value="${c.fuente}" data-moneda="${c.moneda}">${escHtml(c.nombre)}</option>`).join("");
}

document.getElementById("nm-cuenta").addEventListener("change", function() {
  const opt    = this.options[this.selectedIndex];
  const moneda = opt?.dataset?.moneda || "";
  if (moneda && moneda !== "MULTI") {
    document.getElementById("nm-mon").value = moneda;
  }
});

document.getElementById("nm-fecha").value = new Date().toISOString().slice(0, 10);
_setupCatAC(document.getElementById("nm-cat"), "");  // floating dropdown for new-mov form

document.getElementById("btn-new-mov").addEventListener("click", async () => {
  const panel = document.getElementById("new-mov-panel");
  const open  = panel.style.display === "none";
  panel.style.display = open ? "block" : "none";
  if (open) { await _populateNmCuentas(); document.getElementById("nm-desc").focus(); }
});

document.getElementById("btn-save-new-mov").addEventListener("click", async () => {
  const fuente = document.getElementById("nm-cuenta").value;
  const fecha  = document.getElementById("nm-fecha").value;
  const desc   = document.getElementById("nm-desc").value.trim();
  const tipo   = document.getElementById("nm-tipo").value;
  const raw    = parseFloat(document.getElementById("nm-monto").value);
  const cat    = document.getElementById("nm-cat").value.trim();
  const mon    = document.getElementById("nm-mon").value;

  if (!fuente) { showToast("Seleccioná una cuenta.", "err"); return; }
  if (!fecha || !desc || isNaN(raw) || raw <= 0) {
    showToast("Completá fecha, descripción y monto.", "err"); return;
  }
  // v0.2.35: positive = egreso, negative = ingreso for all sources
  const monto = tipo === "egreso" ? raw : -raw;
  const res = await fetch(`${BASE}/api/cuentas/${fuente}/movimientos`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({fecha, descripcion: desc, monto, moneda: mon, categoria: cat||null}),
  });
  if (res.ok) {
    document.getElementById("nm-desc").value  = "";
    document.getElementById("nm-monto").value = "";
    document.getElementById("nm-cat").value   = "";
    showToast("Movimiento guardado.", "ok");
    loadGastos(); loadSaldos(); loadMonthlyChart();
  } else {
    showToast("Error al guardar.", "err");
  }
});

// ── Transfer detection modal ──────────────────────────────────────────────────
let _transferPairs = [];

document.getElementById("btn-detect-transfers").addEventListener("click", async () => {
  const res = await fetch(`${BASE}/api/gastos/detect-transfers`);
  _transferPairs = await res.json();
  const list = document.getElementById("transfer-list");
  if (!_transferPairs.length) {
    list.innerHTML = `<p style="color:#888;padding:.5rem 0">No se encontraron transferencias candidatas sin categorizar.</p>`;
  } else {
    list.innerHTML = _transferPairs.map((p,i) => `
      <div class="transfer-row">
        <input type="checkbox" id="tp-${i}" checked />
        <label for="tp-${i}" class="transfer-pair">
          <div class="transfer-pair-line">
            <span class="t-date">${p.fecha_out}</span>
            <span class="badge badge-${p.fuente_out}">${p.fuente_out.replace("_"," ")}</span>
            ${escHtml(p.desc_out)}
            <span class="t-amt"> −${_fmtNum2(Math.abs(p.monto_out))}</span>
          </div>
          <div class="transfer-pair-line" style="color:#888;font-size:.8rem;margin-top:.15rem">
            <span class="transfer-arrow">↕</span>
            <span class="t-date">${p.fecha_in}</span>
            <span class="badge badge-${p.fuente_in}">${p.fuente_in.replace("_"," ")}</span>
            ${escHtml(p.desc_in)}
            <span class="t-amt"> +${_fmtNum2(Math.abs(p.monto_in))}</span>
          </div>
        </label>
      </div>`).join("");
  }
  document.getElementById("transfer-modal").style.display = "flex";
});

function closeTransferModal() { document.getElementById("transfer-modal").style.display = "none"; }

async function confirmTransfers() {
  const selected = _transferPairs
    .filter((_,i) => document.getElementById(`tp-${i}`)?.checked)
    .map(p => [p.id_out, p.id_in]);
  if (!selected.length) { closeTransferModal(); return; }
  const res  = await fetch(`${BASE}/api/gastos/mark-transfers`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({pairs: selected}),
  });
  const data = await res.json();
  closeTransferModal();
  showToast(`✓ ${data.marcados} movimientos marcados como Transferencia`, "ok");
  loadGastos(); loadMonthlyChart();
}
document.getElementById("transfer-modal").addEventListener("click", function(e) {
  if (e.target === this) closeTransferModal();
});

// ── Import batches ────────────────────────────────────────────────────────────
const _FUENTE_LABEL = {
  amex:"AMEX", bbva_mc:"BBVA MC", bbva_visa:"BBVA Visa",
  bbva_cuenta:"BBVA Cuenta", galicia_mc:"Galicia MC", mercadopago:"MercadoPago",
};

async function loadImportaciones() {
  const res  = await fetch(`${BASE}/api/importaciones`);
  const data = await res.json();
  const grp  = document.getElementById("delete-import-optgroup");

  // Populate delete-target optgroup
  if (grp) {
    if (!data.length) {
      grp.innerHTML = "<option disabled>Sin importaciones registradas</option>";
    } else {
      grp.innerHTML = data.map(imp => {
        const fLabel = _FUENTE_LABEL[imp.fuente] || imp.fuente;
        const mes    = imp.mes_resumen ? ` (${_fmtMes(imp.mes_resumen)})` : "";
        const arch   = imp.archivo && imp.archivo !== imp.fuente ? ` — ${imp.archivo}` : "";
        const fecha  = (imp.fecha_import || "").slice(0, 10);
        const label  = `[${fecha}] ${fLabel}${mes}${arch} · ${imp.cantidad} mov.`;
        return `<option value="import:${imp.id}">${label}</option>`;
      }).join("");
    }
  }

  // Populate gastos filter-import combo
  const filterImport = document.getElementById("filter-import");
  if (filterImport) {
    const current = filterImport.value;
    filterImport.innerHTML = `<option value="">Todas las importaciones</option>` +
      data.map(imp => {
        const fLabel = _FUENTE_LABEL[imp.fuente] || imp.fuente;
        const mes    = imp.mes_resumen ? ` (${_fmtMes(imp.mes_resumen)})` : "";
        const arch   = imp.archivo && imp.archivo !== imp.fuente ? ` — ${imp.archivo}` : "";
        const fecha  = (imp.fecha_import || "").slice(0, 10);
        const label  = `[${fecha}] ${fLabel}${mes}${arch} · ${imp.cantidad} mov.`;
        return `<option value="${imp.id}">${label}</option>`;
      }).join("");
    if (current && filterImport.querySelector(`option[value="${current}"]`)) {
      filterImport.value = current;
    }
  }

  // Populate parser grid with last-import-per-fuente info
  renderParserGrid(data);
}

// ── Delete all ────────────────────────────────────────────────────────────────
document.getElementById("btn-delete-all").addEventListener("click", () => {
  const val = document.getElementById("delete-target").value;
  if (!val) {
    showToast("Seleccioná una fuente o importación primero.", "err");
    return;
  }
  const label = document.querySelector(`#delete-target option[value="${val}"]`)?.textContent || val;

  showConfirm(`⚠️ Eliminar movimientos: ${label}`, async () => {
    let url;
    if (val.startsWith("fuente:")) {
      url = `${BASE}/api/gastos?fuente=${val.slice(7)}`;
    } else if (val.startsWith("import:")) {
      url = `${BASE}/api/gastos?import_id=${val.slice(7)}`;
    } else {
      // __all__ — delete everything
      url = `${BASE}/api/gastos`;
    }
    const res  = await fetch(url, {method:"DELETE"});
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${data.eliminados} movimientos eliminados`, "ok");
      // Reset select to placeholder so it can't be accidentally re-fired
      document.getElementById("delete-target").value = "";
      loadGastos(); loadMonthlyChart(); loadCategorias(); loadImportaciones(); loadVencimientos();
    } else { showToast("Error al borrar", "err", 0); }
  });
});

// ── Upload — per-parser grid ──────────────────────────────────────────────────
const _PARSERS = [
  { fuente: "amex",        label: "AMEX",        sub: "PDF",  accept: ".pdf" },
  { fuente: "bbva_mc",     label: "BBVA MC",      sub: "PDF",  accept: ".pdf" },
  { fuente: "bbva_visa",   label: "BBVA Visa",    sub: "PDF",  accept: ".pdf" },
  { fuente: "bbva_cuenta", label: "BBVA Cuenta",  sub: "PDF",  accept: ".pdf" },
  { fuente: "galicia_mc",  label: "Galicia MC",   sub: "PDF",  accept: ".pdf" },
  { fuente: "mercadopago", label: "MercadoPago",  sub: "XLSX", accept: ".xls,.xlsx" },
];

let _pendingUploadFuente = null;

function renderParserGrid(importaciones) {
  // Build map: fuente → most recent import info
  const lastByFuente = {};
  for (const imp of importaciones) {
    if (!lastByFuente[imp.fuente]) lastByFuente[imp.fuente] = imp;
  }

  const grid = document.getElementById("parser-grid");
  if (!grid) return;
  grid.innerHTML = _PARSERS.map(p => {
    const last = lastByFuente[p.fuente];
    const lastLine = last
      ? `<span class="parser-card-last">${last.mes_resumen ? _fmtMes(last.mes_resumen) : (last.fecha_import||"").slice(0,10)} · ${last.cantidad} mov.</span>`
      : `<span class="parser-card-last parser-card-last-none">Sin imports</span>`;
    return `
      <div class="parser-card" onclick="triggerUpload('${p.fuente}')" title="Importar ${p.label}">
        <div class="parser-card-label">${p.label}</div>
        <div class="parser-card-sub">${p.sub}</div>
        ${lastLine}
        <div class="parser-card-uploading" id="pc-uploading-${p.fuente}" style="display:none">⏳</div>
      </div>`;
  }).join("");
}

function triggerUpload(fuente) {
  const parser = _PARSERS.find(p => p.fuente === fuente);
  if (!parser) return;
  _pendingUploadFuente = fuente;
  const inp = document.getElementById("upload-file-hidden");
  inp.accept = parser.accept;
  inp.click();
}

document.getElementById("upload-file-hidden").addEventListener("change", async function () {
  const file   = this.files[0];
  const fuente = _pendingUploadFuente;
  this.value   = "";   // reset so same file can be re-selected
  if (!file || !fuente) return;

  const result    = document.getElementById("upload-result-global");
  const spinner   = document.getElementById(`pc-uploading-${fuente}`);
  if (spinner) spinner.style.display = "";
  result.className = ""; result.textContent = "Procesando…";

  const chk = document.getElementById("chk-include-rg5617");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("fuente", fuente);
  fd.append("include_rg5617_credits", chk && chk.checked ? "true" : "false");
  try {
    const res  = await fetch(`${BASE}/api/upload`, {method:"POST", body:fd});
    const data = await res.json();
    if (res.ok) {
      showResult(result, `✅ ${data.importados} movimientos importados (${data.total_parseados} parseados).`, true);
      loadGastos(); loadMonthlyChart(); loadCategorias(); loadSaldos(); loadImportaciones(); loadVencimientos();
    } else {
      showResult(result, `❌ ${data.detail||JSON.stringify(data)}`, false);
    }
  } catch(e) {
    showResult(result, `❌ Error de red: ${e}`, false);
  } finally {
    if (spinner) spinner.style.display = "none";
  }
});

// ── Categorization rules ──────────────────────────────────────────────────────
let _rules = [];

async function loadRules() {
  const res  = await fetch(`${BASE}/api/rules`);
  const data = await res.json();
  _rules = (data.reglas||[]).map(r => ({
    palabras: Array.isArray(r.palabras) ? r.palabras.map(String) : _patternToWords(r.patron||""),
    categoria: r.categoria||"",
    especial: !!r.especial,
  }));
  renderRules();
}

function _patternToWords(patron) {
  const m = patron.match(/^\(\?i\)\((.+)\)$/s);
  return m ? m[1].split("|").map(w=>w.trim()).filter(Boolean) : patron ? [patron] : [];
}

function renderRules() {
  const list = document.getElementById("rules-list");
  list.innerHTML = "";
  _rules.forEach((rule,i) => {
    const card = document.createElement("div");
    card.className = "rule-card" + (rule.especial ? " rule-especial" : "");
    const tagsHtml = rule.palabras.map((w,j) =>
      `<span class="tag"><span class="tag-label" title="Doble clic para editar" ondblclick="editTag(${i},${j})">${escHtml(w)}</span><button class="tag-x" type="button" onclick="removeTag(${i},${j})">×</button></span>`
    ).join("");
    card.innerHTML = `
      <div class="rule-header">
        <input class="rule-cat" data-i="${i}" value="${escHtml(rule.categoria)}" placeholder="Nombre de categoría">
        <label class="rule-especial-label" title="Categoría especial: se excluye de totales y gráficos">
          <input type="checkbox" class="rule-especial-chk" data-i="${i}" ${rule.especial?"checked":""}> Especial
        </label>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeRule(${i})">Eliminar</button>
      </div>
      <div class="rule-tags" id="tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input" data-i="${i}" placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addTag(event,${i})">
      </div>`;
    list.appendChild(card);
  });
  // Wire especial checkboxes immediately (they fire _scheduleSaveRules on change)
  document.querySelectorAll(".rule-especial-chk").forEach(chk => {
    chk.addEventListener("change", function() {
      const i = parseInt(this.dataset.i);
      _syncRules();
      _rules[i].especial = this.checked;
      this.closest(".rule-card").classList.toggle("rule-especial", this.checked);
      _scheduleSaveRules();
    });
  });
}

function _syncRules() {
  document.querySelectorAll(".rule-cat").forEach((inp,i) => { if (_rules[i]) _rules[i].categoria = inp.value; });
  document.querySelectorAll(".rule-especial-chk").forEach((chk,i) => { if (_rules[i]) _rules[i].especial = chk.checked; });
}

// Auto-save with debounce
let _saveRulesTimer = null;
function _scheduleSaveRules() {
  clearTimeout(_saveRulesTimer);
  _saveRulesTimer = setTimeout(async () => {
    _syncRules();
    const reglas = _rules
      .filter(r => r.palabras.length > 0 && r.categoria.trim())
      .map(r => ({palabras: r.palabras, categoria: r.categoria, especial: !!r.especial}));
    const res = await fetch(`${BASE}/api/rules`, {
      method:"PUT", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({reglas}),
    });
    showToast(res.ok ? "✓ Reglas guardadas" : "❌ Error al guardar reglas", res.ok ? "ok" : "err", res.ok ? 2000 : 0);
  }, 800);
}
// Save on any focusout inside the rules list
document.getElementById("rules-list").addEventListener("focusout", _scheduleSaveRules);

function removeRule(i)  { _syncRules(); _rules.splice(i,1); renderRules(); _scheduleSaveRules(); }
function removeTag(i,j) { _syncRules(); _rules[i].palabras.splice(j,1); renderRules(); _scheduleSaveRules(); }
function addTag(event,i) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const word = event.target.value.trim();
  if (!word) return;
  _syncRules();
  if (!_rules[i].palabras.includes(word)) _rules[i].palabras.push(word);
  renderRules();
  document.querySelectorAll(".tag-input")[i]?.focus();
  _scheduleSaveRules();
}
function editTag(i, j) {
  _syncRules();
  const labelEl = document.querySelector(`#tags-${i} .tag:nth-child(${j+1}) .tag-label`);
  if (!labelEl) return;
  const orig = _rules[i].palabras[j];
  const inp = document.createElement("input");
  inp.className = "tag-edit-input";
  inp.value = orig;
  inp.style.width = Math.max(60, orig.length * 8) + "px";
  let saved = false;
  function doSave() {
    if (saved) return; saved = true;
    const val = inp.value.trim();
    if (!val) { _rules[i].palabras.splice(j, 1); }
    else       { _rules[i].palabras[j] = val; }
    renderRules(); _scheduleSaveRules();
  }
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); doSave(); }
    if (e.key === "Escape") { saved = true; renderRules(); }
  });
  inp.addEventListener("blur", doSave);
  labelEl.replaceWith(inp);
  inp.focus(); inp.select();
}

document.getElementById("btn-add-rule").addEventListener("click", () => {
  _syncRules(); _rules.push({palabras:[],categoria:"",especial:false}); renderRules();
  const el = document.querySelectorAll(".rule-cat").at(-1);
  el?.focus();
  el?.scrollIntoView({behavior:"smooth", block:"nearest"});
});

document.getElementById("btn-apply-rules").addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-rules");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/rules/apply`, {method:"POST"});
    const data = await res.json();
    if (res.ok) { showToast(`✓ ${data.categorizados} movimientos categorizados`, "ok"); loadGastos(); loadCategorias(); }
    else showToast("Error al aplicar reglas", "err", 0);
  } finally { btn.disabled = false; btn.textContent = "Reaplicar a todos"; }
});

loadRules();

// ── Match rules ───────────────────────────────────────────────────────────────
const _FUENTES_FALLBACK = [
  {fuente:"amex",        nombre:"AMEX"},
  {fuente:"bbva_mc",     nombre:"BBVA Mastercard"},
  {fuente:"bbva_visa",   nombre:"BBVA Visa"},
  {fuente:"bbva_cuenta", nombre:"BBVA Cuenta"},
  {fuente:"galicia_mc",  nombre:"Galicia Mastercard"},
  {fuente:"mercadopago", nombre:"MercadoPago"},
];

function _buildFuenteOpts() {
  const src = _cuentasData.length > 0 ? _cuentasData : _FUENTES_FALLBACK;
  return `<option value="">Cualquier fuente</option>` +
    src.map(c => `<option value="${escHtml(c.fuente)}">${escHtml(c.nombre)}</option>`).join("");
}

function _populateFuenteSelects() {
  const src = _cuentasData.length > 0 ? _cuentasData : _FUENTES_FALLBACK;
  const optHtml = `<option value="">Todas las fuentes</option>` +
    src.map(c => `<option value="${escHtml(c.fuente)}">${escHtml(c.nombre)}</option>`).join("");
  ["filter-fuente","cf-fuente"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = optHtml;
    if (cur) sel.value = cur;
  });
  // delete-target "Por fuente" optgroup
  const dtGroup = document.querySelector('#delete-target optgroup[label="Por fuente"]');
  if (dtGroup) {
    dtGroup.innerHTML = src.map(c =>
      `<option value="fuente:${escHtml(c.fuente)}">${escHtml(c.nombre)}</option>`
    ).join("");
  }
}

let _matchRules = [];

async function loadMatchRules() {
  const res  = await fetch(`${BASE}/api/rules/match`);
  const data = await res.json();
  _matchRules = data.reglas || [];
  renderMatchRules();
}

function renderMatchRules() {
  const list = document.getElementById("match-rules-list");
  list.innerHTML = "";
  _matchRules.forEach((r, i) => {
    const card = document.createElement("div");
    card.className = "match-rule-card";
    card.innerHTML = `
      <div class="match-rule-header">
        <input class="match-nombre" data-i="${i}" value="${escHtml(r.nombre)}" placeholder="Nombre de la regla">
        <div style="display:flex;gap:.4rem;align-items:center">
          <button class="btn btn-sm" onclick="applyOneMatchRule(${i})">Aplicar</button>
          <button class="btn btn-danger btn-sm" onclick="removeMatchRule(${i})">✕</button>
        </div>
      </div>
      <div class="match-sides">
        <div class="match-side">
          <div class="match-side-label">Lado A <span class="match-side-hint">(obligatorio)</span></div>
          <input class="match-patron-a" data-i="${i}" value="${escHtml(r.patron_a)}" placeholder="Patrón en descripción">
          <select class="match-fuente-a" data-i="${i}">${_buildFuenteOpts()}</select>
        </div>
        <div class="match-arrow-col">↔</div>
        <div class="match-side">
          <div class="match-side-label">Lado B <span class="match-side-hint">(opcional, para emparejado)</span></div>
          <input class="match-patron-b" data-i="${i}" value="${escHtml(r.patron_b||"")}" placeholder="Patrón (vacío = cualquiera)">
          <select class="match-fuente-b" data-i="${i}">${_buildFuenteOpts()}</select>
        </div>
      </div>
      <div class="match-rule-footer">
        <label>Ventana <input type="number" class="match-ventana" data-i="${i}" value="${r.ventana_dias??3}" min="0" max="60"> días</label>
        <label>Categoría <input class="match-cat" data-i="${i}" value="${escHtml(r.categoria||"Transferencia")}" placeholder="Transferencia"></label>
      </div>`;

    // Set select values after inserting
    card.querySelector(".match-fuente-a").value = r.fuente_a || "";
    card.querySelector(".match-fuente-b").value = r.fuente_b || "";
    list.appendChild(card);
  });
}

function _syncMatchRules() {
  _matchRules = _matchRules.map((_, i) => ({
    nombre:      document.querySelector(`.match-nombre[data-i="${i}"]`)?.value    || "",
    patron_a:    document.querySelector(`.match-patron-a[data-i="${i}"]`)?.value  || "",
    fuente_a:    document.querySelector(`.match-fuente-a[data-i="${i}"]`)?.value  || "",
    patron_b:    document.querySelector(`.match-patron-b[data-i="${i}"]`)?.value  || "",
    fuente_b:    document.querySelector(`.match-fuente-b[data-i="${i}"]`)?.value  || "",
    ventana_dias:+document.querySelector(`.match-ventana[data-i="${i}"]`)?.value  || 3,
    categoria:   document.querySelector(`.match-cat[data-i="${i}"]`)?.value       || "Transferencia",
  }));
}

let _saveMatchTimer = null;
function _scheduleSaveMatchRules() {
  clearTimeout(_saveMatchTimer);
  _saveMatchTimer = setTimeout(async () => {
    _syncMatchRules();
    const res = await fetch(`${BASE}/api/rules/match`, {
      method:"PUT", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({reglas: _matchRules}),
    });
    showToast(res.ok ? "✓ Reglas de emparejado guardadas" : "❌ Error al guardar", res.ok ? "ok" : "err", res.ok ? 2000 : 0);
  }, 800);
}
document.getElementById("match-rules-list").addEventListener("focusout", _scheduleSaveMatchRules);

function removeMatchRule(i) { _syncMatchRules(); _matchRules.splice(i,1); renderMatchRules(); _scheduleSaveMatchRules(); }

document.getElementById("btn-add-match-rule").addEventListener("click", () => {
  _syncMatchRules();
  _matchRules.push({nombre:"",patron_a:"",fuente_a:"",patron_b:"",fuente_b:"",ventana_dias:3,categoria:"Transferencia"});
  renderMatchRules();
  const el = document.querySelectorAll(".match-nombre").at(-1);
  el?.focus();
  el?.scrollIntoView({behavior:"smooth", block:"nearest"});
});

document.getElementById("btn-apply-match-rules").addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-match-rules");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/rules/match/apply`, {method:"POST"});
    const data = await res.json();
    if (res.ok) { showToast(`✓ ${data.marcados} movimientos marcados`, "ok"); loadGastos(); loadCategorias(); }
    else showToast("Error al aplicar", "err", 0);
  } finally { btn.disabled = false; btn.textContent = "Aplicar todas"; }
});

async function applyOneMatchRule(i) {
  _syncMatchRules();
  const rule = _matchRules[i];
  const btn  = document.querySelectorAll(".match-rule-card")[i]?.querySelector(".btn");
  if (btn) { btn.disabled = true; btn.textContent = "…"; }
  try {
    const res  = await fetch(`${BASE}/api/rules/match/apply-one`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(rule),
    });
    const data = await res.json();
    showToast(`✓ ${data.marcados} movimientos marcados`, "ok");
    loadGastos(); loadCategorias();
  } finally { if (btn) { btn.disabled = false; btn.textContent = "Aplicar"; } }
}

loadMatchRules();

// ── Saldos widget ─────────────────────────────────────────────────────────────
let _widgetCuentas = [];

async function loadSaldos() {
  const res    = await fetch(`${BASE}/api/cuentas`);
  _widgetCuentas = await res.json();
  // Reuse the same fetch to keep fuente dropdowns up-to-date
  _cuentasData = _widgetCuentas;
  _populateFuenteSelects();
  renderSaldos(_widgetCuentas.filter(c => c.activa));
}

function _saldoMonto(saldo, moneda) {
  const cls = moneda === "USD" ? "usd-val" : "ars-val";
  return `<div class="saldo-monto ${cls}">${_fmtSaldo(saldo)} ${moneda}</div>`;
}

function renderSaldos(cuentas) {
  const widget = document.getElementById("saldos-widget");
  if (!cuentas.length) { widget.style.display = "none"; return; }
  widget.style.display = "flex";
  widget.innerHTML = cuentas.map(c => {
    const moneda  = c.moneda || "ARS";
    const isMulti = moneda === "MULTI";
    const isUsd   = moneda === "USD";
    const sArs    = c.saldo     || 0;
    const sUsd    = c.saldo_usd || 0;

    const montoHtml = isMulti
      ? _saldoMonto(sArs, "ARS") + _saldoMonto(sUsd, "USD")
      : isUsd ? _saldoMonto(sUsd, "USD") : _saldoMonto(sArs, "ARS");

    const editInputs = isMulti ? `
      <div style="display:flex;flex-direction:column;gap:.2rem">
        <div style="display:flex;gap:.3rem;align-items:center">
          <span style="font-size:.72rem;color:#999;width:26px">ARS</span>
          <input type="text" id="saldo-input-ars-${c.fuente}" value="${_fmtNum2(sArs)}" style="width:80px"
                 onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')">
        </div>
        <div style="display:flex;gap:.3rem;align-items:center">
          <span style="font-size:.72rem;color:#999;width:26px">USD</span>
          <input type="text" id="saldo-input-usd-${c.fuente}" value="${_fmtNum2(sUsd)}" style="width:80px"
                 onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')">
        </div>
      </div>` : `
      <input type="text" id="saldo-input-${c.fuente}" value="${_fmtNum2(isUsd ? sUsd : sArs)}"
             onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')" style="width:90px">`;

    return `
      <div class="saldo-card" id="saldo-card-${c.fuente}">
        <button class="saldo-edit-btn" title="Editar saldo" onclick="toggleSaldoEdit('${c.fuente}')">✏</button>
        <div class="saldo-nombre">${escHtml(c.nombre)}</div>
        ${montoHtml}
        <div class="saldo-fecha">${c.fecha_actualizacion ? `Actualizado ${c.fecha_actualizacion}` : "Sin datos"}</div>
        <div class="saldo-edit-row" id="saldo-edit-${c.fuente}" style="display:none">
          ${editInputs}
          <button class="btn btn-sm btn-primary" onclick="saveSaldo('${c.fuente}')">✓</button>
        </div>
      </div>`;
  }).join("");
}

function toggleSaldoEdit(fuente) {
  const row  = document.getElementById(`saldo-edit-${fuente}`);
  const open = row.style.display === "none";
  row.style.display = open ? "flex" : "none";
  if (open) {
    (document.getElementById(`saldo-input-ars-${fuente}`) ||
     document.getElementById(`saldo-input-${fuente}`))?.select();
  }
}

function _parseNum(s) { return parseFloat(String(s).replace(/\./g,"").replace(",",".")) || 0; }

async function saveSaldo(fuente) {
  const cuenta  = _widgetCuentas.find(c => c.fuente === fuente);
  const moneda  = cuenta?.moneda || "ARS";
  let body = {};
  if (moneda === "MULTI") {
    body.saldo     = _parseNum(document.getElementById(`saldo-input-ars-${fuente}`)?.value);
    body.saldo_usd = _parseNum(document.getElementById(`saldo-input-usd-${fuente}`)?.value);
  } else if (moneda === "USD") {
    body.saldo_usd = _parseNum(document.getElementById(`saldo-input-${fuente}`)?.value);
  } else {
    body.saldo = _parseNum(document.getElementById(`saldo-input-${fuente}`)?.value);
  }
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  });
  loadSaldos();
}

loadSaldos();

// ── Vencimientos widget ───────────────────────────────────────────────────────

const _FUENTE_LABELS = {
  amex: "AMEX", bbva_mc: "BBVA Mastercard", bbva_visa: "BBVA Visa",
  galicia_mc: "Galicia MC", bbva_cuenta: "BBVA Cuenta",
  mercadopago: "MercadoPago",
};

async function loadVencimientos() {
  try {
    const res  = await fetch(`${BASE}/api/stats/vencimientos`);
    const data = await res.json();
    renderVencimientos(data.vencimientos || []);
  } catch(e) {
    console.error("loadVencimientos error:", e);
  }
}

function renderVencimientos(items) {
  const widget = document.getElementById("vencimientos-widget");
  if (!items.length) { widget.style.display = "none"; return; }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Keep only the most-recent entry per fuente (already ordered DESC by fecha_venc)
  const seen = new Set();
  const deduped = items.filter(v => {
    if (seen.has(v.fuente)) return false;
    seen.add(v.fuente);
    return true;
  });

  // Read visibility / threshold prefs once before the map loop
  const _tUrgente  = getUiPref("dias_urgente");
  const _tPronto   = getUiPref("dias_pronto");
  const _showProx  = getUiPref("venc_show_proximos");
  const _showRg    = getUiPref("venc_show_rg5617");
  const _showPdf   = getUiPref("venc_show_pdf_ref");

  widget.style.display = "flex";
  widget.innerHTML = deduped.map(v => {
    const vencDate = new Date(v.fecha_venc + "T00:00:00");
    const diffMs   = vencDate - today;
    const dias     = Math.round(diffMs / 86400000);

    let cls, diasTxt;
    if (dias < 0) {
      cls = "vencido";
      diasTxt = `Vencido hace ${-dias} día${-dias === 1 ? "" : "s"}`;
    } else if (dias === 0) {
      cls = "urgente";
      diasTxt = "Vence hoy";
    } else if (dias <= _tUrgente) {
      cls = "urgente";
      diasTxt = `Vence en ${dias} día${dias === 1 ? "" : "s"}`;
    } else if (dias <= _tPronto) {
      cls = "pronto";
      diasTxt = `En ${dias} días`;
    } else {
      cls = "ok";
      diasTxt = `En ${dias} días`;
    }

    const label  = _FUENTE_LABELS[v.fuente] || v.fuente;

    // Primary: always show computed sum of egresos from the gastos table.
    // Secondary: if the PDF total is available and differs from the computed sum
    // by more than 0.50, show it as a "PDF: $X" reference line so any
    // discrepancy (missed transactions, parser error) is immediately visible.
    // Use net (egresos − already-imported credits) so the widget shows what
    // you actually owe, consistent with the PDF's TOTAL A PAGAR / SALDO ACTUAL.
    // Fall back to sum_ars for older imports that pre-date the net_ars column.
    const arsSum   = v.net_ars != null ? v.net_ars : (v.sum_ars || 0);
    const usdSum   = v.net_usd != null ? v.net_usd : (v.sum_usd || 0);
    const rg5617   = v.rg5617_ars || 0;   // declared early — used by hasRg below
    // ARS amounts → green, USD amounts → blue
    const arsStr   = arsSum > 0 ? `<span class="venc-ars">$ ${_fmtNum2(arsSum)}</span>` : "";
    const usdStr   = usdSum > 0 ? `<span class="venc-usd"> · U$S ${_fmtNum2(usdSum)}</span>` : "";
    // Store raw values as data-attrs for the RG-5617 toggle (double-click)
    const hasRg = rg5617 > 0.5 && arsSum > 0;
    const montoHtml = (arsStr || usdStr)
      ? `<div class="venc-monto${hasRg ? " venc-monto--has-rg" : ""}"` +
        ` data-ars-full="${arsSum.toFixed(2)}" data-rg5617="${rg5617.toFixed(2)}"` +
        `${hasRg ? ' title="Doble clic: ver sin RG 5617"' : ""}>${arsStr}${usdStr}</div>` : "";

    const fuenteCls = "venc-fuente";  // name always grey; colour is on the amounts

    // Compare NET (egresos + synthetic credits) against PDF total.
    // When the synthetic "Créditos del resumen" row was inserted correctly,
    // net_ars == total_ars and no amber line appears.  A mismatch means the
    // parser missed something or the PDF total couldn't be extracted at all.
    const arsDiff = v.total_ars != null ? Math.abs((v.net_ars ?? arsSum) - v.total_ars) : 0;
    const usdDiff = v.total_usd != null ? Math.abs((v.net_usd ?? usdSum) - v.total_usd) : 0;
    const pdfArsStr = (v.total_ars != null && arsDiff > 0.5) ? `PDF: $ ${_fmtNum2(v.total_ars)}` : "";
    const pdfUsdStr = (v.total_usd != null && usdDiff > 0.5) ? ` · U$S ${_fmtNum2(v.total_usd)}` : "";
    const pdfHtml = (_showPdf && (pdfArsStr || pdfUsdStr))
      ? `<div class="venc-pdf-ref">${pdfArsStr}${pdfUsdStr}</div>` : "";

    // RG 5617 perception line — grey, shows only the current-period charge
    const rg5617Html = (_showRg && Math.abs(rg5617) > 0.5)
      ? `<div class="venc-rg5617">RG 5617: ${rg5617 < 0 ? "−" : ""}$ ${_fmtNum2(Math.abs(rg5617))}</div>`
      : "";

    // Próximo cierre / próximo vencimiento
    const _fmtD = iso => {
      const [y,m,d] = iso.split("-");
      return `${d}/${m}/${y.slice(2)}`;
    };
    let proxHtml = "";
    if (_showProx && (v.proximo_cierre || v.proximo_venc)) {
      const parts = [];
      if (v.proximo_cierre) parts.push(`cierre ${_fmtD(v.proximo_cierre)}`);
      if (v.proximo_venc)   parts.push(`venc. ${_fmtD(v.proximo_venc)}`);
      proxHtml = `<div class="venc-proximos">Próx. ${parts.join(" · ")}</div>`;
    }

    // Format current due date as DD/MM/YYYY
    const d = vencDate;
    const fechaStr = `${String(d.getDate()).padStart(2,"0")}/${String(d.getMonth()+1).padStart(2,"0")}/${d.getFullYear()}`;

    return `<div class="venc-card ${cls}">
      <div class="${fuenteCls}">${escHtml(label)}</div>
      <div class="venc-fecha">${fechaStr}</div>
      <div class="venc-dias">${diasTxt}</div>
      ${montoHtml}
      ${rg5617Html}
      ${pdfHtml}
      ${proxHtml}
    </div>`;
  }).join("");
}

loadVencimientos();

// Double-click on an ARS amount to toggle the RG-5617-free view
document.getElementById("vencimientos-widget").addEventListener("dblclick", e => {
  const monto = e.target.closest(".venc-monto--has-rg");
  if (!monto) return;
  const full   = parseFloat(monto.dataset.arsFull  || "0");
  const rg5617 = parseFloat(monto.dataset.rg5617   || "0");
  const span   = monto.querySelector(".venc-ars");
  if (!span) return;
  const toggled = monto.classList.toggle("venc-monto--sin-rg");
  if (toggled) {
    const sinRg = full - rg5617;
    span.innerHTML = `$ ${_fmtNum2(sinRg)}<span class="venc-sin-rg-tag"> −RG</span>`;
    monto.title = "Doble clic: ver total";
  } else {
    span.textContent = `$ ${_fmtNum2(full)}`;
    monto.title = "Doble clic: ver sin RG 5617";
  }
});

// ── Presupuesto tab ───────────────────────────────────────────────────────────
let _presupItems    = [];  // [{categoria, monto_mensual, moneda}]
let _presupVsActual = [];
let _presupSort     = {col: "gastado", dir: -1};

function sortPresup(col) {
  if (_presupSort.col === col) _presupSort.dir *= -1;
  else { _presupSort.col = col; _presupSort.dir = col === "categoria" ? 1 : -1; }
  renderPresupuesto();
}

async function loadPresupuesto() {
  const mes = document.getElementById("presup-mes").value;
  const url = mes ? `${BASE}/api/presupuesto?mes=${mes}` : `${BASE}/api/presupuesto`;
  const res  = await fetch(url);
  const data = await res.json();
  _presupItems    = data.items || [];
  _presupVsActual = data.vs_actual || [];
  renderPresupuesto();
}

function renderPresupuesto() {
  const vsActual = _presupVsActual;
  const wrap = document.getElementById("presup-table-wrap");
  if (!vsActual.length && !_presupItems.length) {
    wrap.innerHTML = `<p style="color:#aaa;padding:1rem 0">No hay categorías con gastos ni presupuesto definido. Importá movimientos primero.</p>`;
    return;
  }

  const budgetMap = {};
  _presupItems.forEach(it => { budgetMap[it.categoria] = it.monto_mensual; });

  let rows = vsActual.length ? vsActual : _presupItems.map(it => ({
    categoria: it.categoria, presupuesto: it.monto_mensual, gastado: 0, diferencia: it.monto_mensual, pct: null,
  }));

  // Sort
  const sc = _presupSort.col, sd = _presupSort.dir;
  rows = [...rows].sort((a, b) => {
    if (sc === "categoria") return sd * (a.categoria||"").localeCompare(b.categoria||"", "es");
    return sd * ((a[sc]||0) - (b[sc]||0));
  });

  // Totals
  let totalPresup = 0, totalGastado = 0;
  rows.forEach(r => {
    totalPresup  += r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.categoria] || 0);
    totalGastado += r.gastado || 0;
  });
  const totalDiff = totalPresup - totalGastado;
  const totalPct  = totalPresup > 0 ? Math.round(totalGastado / totalPresup * 100) : 0;
  const totalBarCls = totalPct >= 100 ? "over" : totalPct >= 80 ? "warn" : "";

  // Summary bar (only when month is selected and there's real spending data)
  const summaryHtml = vsActual.length ? `
    <div class="presup-summary">
      <span>Presupuestado: <strong>${_fmtNum2(totalPresup)}</strong></span>
      <span>Gastado: <strong>${_fmtNum2(totalGastado)}</strong></span>
      <span class="${totalDiff >= 0 ? "presup-diff-pos" : "presup-diff-neg"}">
        Diferencia: <strong>${totalDiff >= 0 ? "+" : ""}${_fmtNum2(totalDiff)}</strong>
      </span>
      ${totalPresup > 0 ? `<span style="color:#888">${totalPct}% utilizado</span>` : ""}
    </div>` : "";

  const _psi = col => _presupSort.col === col ? (_presupSort.dir > 0 ? "▲" : "▼") : "";
  wrap.innerHTML = summaryHtml + `
    <div class="table-wrap">
    <table class="presup-table">
      <thead>
        <tr>
          <th class="th-sort" onclick="sortPresup('categoria')">Categoría <span class="sort-ind">${_psi("categoria")}</span></th>
          <th class="th-sort" onclick="sortPresup('presupuesto')">Presupuesto <span class="sort-ind">${_psi("presupuesto")}</span></th>
          <th class="th-sort" onclick="sortPresup('gastado')">Gastado <span class="sort-ind">${_psi("gastado")}</span></th>
          <th class="th-sort" onclick="sortPresup('diferencia')">Diferencia <span class="sort-ind">${_psi("diferencia")}</span></th>
          <th>Progreso</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(r => {
          const budget  = r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.categoria] || 0);
          const pct     = budget > 0 ? Math.round(r.gastado / budget * 100) : 0;
          const barW    = Math.min(pct, 100);
          const barCls  = pct >= 100 ? "over" : pct >= 80 ? "warn" : "";
          const diffCls = r.diferencia >= 0 ? "presup-diff-pos" : "presup-diff-neg";
          return `<tr>
            <td>${escHtml(r.categoria)}</td>
            <td>
              <input type="text" class="presup-input" data-cat="${escHtml(r.categoria)}"
                     value="${_fmtNum2(budget)}"
                     onfocus="this.select()"
                     onchange="updatePresupItem('${escHtml(r.categoria)}',this.value)" />
            </td>
            <td style="font-variant-numeric:tabular-nums">${_fmtNum2(r.gastado)}</td>
            <td class="${budget > 0 ? diffCls : ""}">
              ${budget > 0 ? (r.diferencia >= 0 ? "+" : "") + _fmtNum2(r.diferencia) : "—"}
            </td>
            <td>
              ${budget > 0 ? `
                <div class="progress-bar-wrap"><div class="progress-bar ${barCls}" style="width:${barW}%"></div></div>
                <span class="presup-pct">${pct}%</span>
              ` : "—"}
            </td>
            <td>
              <button class="btn btn-sm btn-danger"
                      onclick="removePresupItem('${escHtml(r.categoria)}')">✕</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
      <tfoot>
        <tr class="presup-total-row">
          <td><strong>Total</strong></td>
          <td><strong style="font-variant-numeric:tabular-nums">${_fmtNum2(totalPresup)}</strong></td>
          <td><strong style="font-variant-numeric:tabular-nums">${_fmtNum2(totalGastado)}</strong></td>
          <td class="${totalPresup > 0 ? (totalDiff >= 0 ? "presup-diff-pos" : "presup-diff-neg") : ""}">
            <strong>${totalPresup > 0 ? (totalDiff >= 0 ? "+" : "") + _fmtNum2(totalDiff) : "—"}</strong>
          </td>
          <td>
            ${totalPresup > 0 ? `
              <div class="progress-bar-wrap"><div class="progress-bar ${totalBarCls}" style="width:${Math.min(totalPct,100)}%"></div></div>
              <span class="presup-pct">${totalPct}%</span>
            ` : "—"}
          </td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    </div>`;
}

function updatePresupItem(categoria, rawValue) {
  const val = parseFloat(rawValue.replace(/\./g,"").replace(",",".")) || 0;
  const existing = _presupItems.find(it => it.categoria === categoria);
  if (existing) existing.monto_mensual = val;
  else _presupItems.push({categoria, monto_mensual: val, moneda: "ARS"});
}

function removePresupItem(categoria) {
  _presupItems = _presupItems.filter(it => it.categoria !== categoria);
  _presupVsActual = _presupVsActual.filter(r => r.categoria !== categoria);
  renderPresupuesto();
  _scheduleSavePresup();
}

document.getElementById("presup-mes").addEventListener("change", function() {
  this.blur();
  loadPresupuesto();
  loadPresupuestoUsuario();
});

// Auto-save helpers — same debounce pattern as rules
let _savePresupTimer = null;
function _scheduleSavePresup() {
  clearTimeout(_savePresupTimer);
  _savePresupTimer = setTimeout(savePresupuesto, 800);
}

async function savePresupuesto() {
  // Sync any values still in the DOM inputs
  document.querySelectorAll(".presup-input").forEach(inp => {
    updatePresupItem(inp.dataset.cat, inp.value);
  });
  const items = _presupItems.filter(it => it.monto_mensual > 0);
  const res = await fetch(`${BASE}/api/presupuesto`, {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({items}),
  });
  if (res.ok) { showToast("✓ Presupuesto guardado", "ok"); loadPresupuesto(); }
  else showToast("Error al guardar presupuesto", "err", 0);
}

// Auto-save on focus-out anywhere inside the table
document.getElementById("presup-table-wrap").addEventListener("focusout", _scheduleSavePresup);

// Save on Enter key inside any presup-input
document.getElementById("presup-table-wrap").addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.classList.contains("presup-input")) {
    e.preventDefault();
    e.target.blur();
    savePresupuesto();
  }
});

document.getElementById("btn-add-presup-row").addEventListener("click", () => {
  showPrompt("Nueva categoría de presupuesto:", "ej: Supermercado", name => {
    if (!_presupItems.find(it => it.categoria === name))
      _presupItems.push({categoria: name, monto_mensual: 0, moneda: "ARS"});
    renderPresupuesto();
    _scheduleSavePresup();
  });
});

// ── Presupuesto por usuario ───────────────────────────────────────────────────
let _presupUItems    = [];  // [{usuario, monto_mensual, moneda}]
let _presupUVsActual = [];
let _presupUSort     = {col: "gastado", dir: -1};

function sortPresupU(col) {
  if (_presupUSort.col === col) _presupUSort.dir *= -1;
  else { _presupUSort.col = col; _presupUSort.dir = col === "usuario" ? 1 : -1; }
  renderPresupuestoUsuario();
}

async function loadPresupuestoUsuario() {
  const mes = document.getElementById("presup-mes").value;
  const url = mes ? `${BASE}/api/presupuesto/usuario?mes=${mes}` : `${BASE}/api/presupuesto/usuario`;
  const res  = await fetch(url);
  const data = await res.json();
  _presupUItems    = data.items || [];
  _presupUVsActual = data.vs_actual || [];
  renderPresupuestoUsuario();
}

function renderPresupuestoUsuario() {
  const vsActual = _presupUVsActual;
  const wrap = document.getElementById("presup-u-table-wrap");
  if (!vsActual.length && !_presupUItems.length) {
    wrap.innerHTML = `<p style="color:#aaa;padding:1rem 0">No hay personas con gastos ni presupuesto definido.</p>`;
    return;
  }

  const budgetMap = {};
  _presupUItems.forEach(it => { budgetMap[it.usuario] = it.monto_mensual; });

  let rows = vsActual.length ? vsActual : _presupUItems.map(it => ({
    usuario: it.usuario, presupuesto: it.monto_mensual, gastado: 0, diferencia: it.monto_mensual, pct: null,
  }));

  // Sort
  const sc = _presupUSort.col, sd = _presupUSort.dir;
  rows = [...rows].sort((a, b) => {
    if (sc === "usuario") return sd * (a.usuario||"").localeCompare(b.usuario||"", "es");
    return sd * ((a[sc]||0) - (b[sc]||0));
  });

  let totalPresup = 0, totalGastado = 0;
  rows.forEach(r => {
    totalPresup  += r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.usuario] || 0);
    totalGastado += r.gastado || 0;
  });
  const totalDiff   = totalPresup - totalGastado;
  const totalPct    = totalPresup > 0 ? Math.round(totalGastado / totalPresup * 100) : 0;
  const totalBarCls = totalPct >= 100 ? "over" : totalPct >= 80 ? "warn" : "";

  const summaryHtml = vsActual.length ? `
    <div class="presup-summary">
      <span>Presupuestado: <strong>${_fmtNum2(totalPresup)}</strong></span>
      <span>Gastado: <strong>${_fmtNum2(totalGastado)}</strong></span>
      <span class="${totalDiff >= 0 ? "presup-diff-pos" : "presup-diff-neg"}">
        Diferencia: <strong>${totalDiff >= 0 ? "+" : ""}${_fmtNum2(totalDiff)}</strong>
      </span>
      ${totalPresup > 0 ? `<span style="color:#888">${totalPct}% utilizado</span>` : ""}
    </div>` : "";

  const _psi = col => _presupUSort.col === col ? (_presupUSort.dir > 0 ? "▲" : "▼") : "";
  wrap.innerHTML = summaryHtml + `
    <div class="table-wrap">
    <table class="presup-table">
      <thead>
        <tr>
          <th class="th-sort" onclick="sortPresupU('usuario')">Persona <span class="sort-ind">${_psi("usuario")}</span></th>
          <th class="th-sort" onclick="sortPresupU('presupuesto')">Presupuesto <span class="sort-ind">${_psi("presupuesto")}</span></th>
          <th class="th-sort" onclick="sortPresupU('gastado')">Gastado <span class="sort-ind">${_psi("gastado")}</span></th>
          <th class="th-sort" onclick="sortPresupU('diferencia')">Diferencia <span class="sort-ind">${_psi("diferencia")}</span></th>
          <th>Progreso</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(r => {
          const budget  = r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.usuario] || 0);
          const pct     = budget > 0 ? Math.round(r.gastado / budget * 100) : 0;
          const barW    = Math.min(pct, 100);
          const barCls  = pct >= 100 ? "over" : pct >= 80 ? "warn" : "";
          const diffCls = r.diferencia >= 0 ? "presup-diff-pos" : "presup-diff-neg";
          return `<tr>
            <td>${escHtml(r.usuario)}</td>
            <td>
              <input type="text" class="presup-u-input" data-usr="${escHtml(r.usuario)}"
                     value="${_fmtNum2(budget)}"
                     onfocus="this.select()"
                     onchange="updatePresupUItem('${escHtml(r.usuario)}',this.value)" />
            </td>
            <td style="font-variant-numeric:tabular-nums">${_fmtNum2(r.gastado)}</td>
            <td class="${budget > 0 ? diffCls : ""}">
              ${budget > 0 ? (r.diferencia >= 0 ? "+" : "") + _fmtNum2(r.diferencia) : "—"}
            </td>
            <td>
              ${budget > 0 ? `
                <div class="progress-bar-wrap"><div class="progress-bar ${barCls}" style="width:${barW}%"></div></div>
                <span class="presup-pct">${pct}%</span>
              ` : "—"}
            </td>
            <td>
              <button class="btn btn-sm btn-danger"
                      onclick="removePresupUItem('${escHtml(r.usuario)}')">✕</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
      <tfoot>
        <tr class="presup-total-row">
          <td><strong>Total</strong></td>
          <td><strong style="font-variant-numeric:tabular-nums">${_fmtNum2(totalPresup)}</strong></td>
          <td><strong style="font-variant-numeric:tabular-nums">${_fmtNum2(totalGastado)}</strong></td>
          <td class="${totalPresup > 0 ? (totalDiff >= 0 ? "presup-diff-pos" : "presup-diff-neg") : ""}">
            <strong>${totalPresup > 0 ? (totalDiff >= 0 ? "+" : "") + _fmtNum2(totalDiff) : "—"}</strong>
          </td>
          <td>
            ${totalPresup > 0 ? `
              <div class="progress-bar-wrap"><div class="progress-bar ${totalBarCls}" style="width:${Math.min(totalPct,100)}%"></div></div>
              <span class="presup-pct">${totalPct}%</span>
            ` : "—"}
          </td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    </div>`;
}

function updatePresupUItem(usuario, rawValue) {
  const val = parseFloat(rawValue.replace(/\./g,"").replace(",",".")) || 0;
  const existing = _presupUItems.find(it => it.usuario === usuario);
  if (existing) existing.monto_mensual = val;
  else _presupUItems.push({usuario, monto_mensual: val, moneda: "ARS"});
}

function removePresupUItem(usuario) {
  _presupUItems    = _presupUItems.filter(it => it.usuario !== usuario);
  _presupUVsActual = _presupUVsActual.filter(r => r.usuario !== usuario);
  renderPresupuestoUsuario();
  _scheduleSavePresupU();
}

let _savePresupUTimer = null;
function _scheduleSavePresupU() {
  clearTimeout(_savePresupUTimer);
  _savePresupUTimer = setTimeout(savePresupuestoUsuario, 800);
}

async function savePresupuestoUsuario() {
  document.querySelectorAll(".presup-u-input").forEach(inp => {
    updatePresupUItem(inp.dataset.usr, inp.value);
  });
  const items = _presupUItems.filter(it => it.monto_mensual > 0);
  const res = await fetch(`${BASE}/api/presupuesto/usuario`, {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({items}),
  });
  if (res.ok) { showToast("✓ Presupuesto por persona guardado", "ok"); loadPresupuestoUsuario(); }
  else showToast("Error al guardar presupuesto por persona", "err", 0);
}

document.getElementById("presup-u-table-wrap").addEventListener("focusout", _scheduleSavePresupU);
document.getElementById("presup-u-table-wrap").addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.classList.contains("presup-u-input")) {
    e.preventDefault();
    e.target.blur();
    savePresupuestoUsuario();
  }
});

document.getElementById("btn-add-presup-u-row").addEventListener("click", () => {
  showPrompt("Nombre de la persona:", "ej: Titular", name => {
    if (!_presupUItems.find(it => it.usuario === name))
      _presupUItems.push({usuario: name, monto_mensual: 0, moneda: "ARS"});
    renderPresupuestoUsuario();
    _scheduleSavePresupU();
  });
});

// ── Forecast chart ─────────────────────────────────────────────────────────────

// Categories excluded from income trend (persisted in localStorage)
let _forecastExcludes = [];
(function _initForecastExcludes() {
  try { _forecastExcludes = JSON.parse(localStorage.getItem("forecastExcludeCategories") || "[]"); }
  catch { _forecastExcludes = []; }
})();

function _renderForecastExcludes() {
  const wrap = document.getElementById("forecast-exclude-chips");
  if (!wrap) return;
  wrap.innerHTML = _forecastExcludes.map((c, i) =>
    `<span class="cat-chip active" style="font-size:.78rem;padding:.18rem .55rem">${escHtml(c)
    }<button class="tag-x" type="button" onclick="removeForecastExclude(${i})">×</button></span>`
  ).join("");
}

function removeForecastExclude(i) {
  _forecastExcludes.splice(i, 1);
  localStorage.setItem("forecastExcludeCategories", JSON.stringify(_forecastExcludes));
  _renderForecastExcludes();
  loadForecast();
}

async function _onForecastExcludeAdd() {
  const cats = await fetch(`${BASE}/api/categorias`).then(r => r.json());
  const available = cats.filter(c => !_forecastExcludes.includes(c));
  if (!available.length) { showToast("No hay más categorías para excluir.", "ok"); return; }
  showSelectPrompt(
    "Excluir categoría de ingresos:",
    available.map(c => ({value: c, label: c})),
    cat => {
      if (!_forecastExcludes.includes(cat)) {
        _forecastExcludes.push(cat);
        localStorage.setItem("forecastExcludeCategories", JSON.stringify(_forecastExcludes));
        _renderForecastExcludes();
        loadForecast();
      }
    }
  );
}
// Note: btn-forecast-exclude-add is re-bound in _buildChartBox each time the grid rebuilds

async function loadForecast() {
  const meses     = document.getElementById("cf-forecast-meses")?.value || "6";
  const historico = document.getElementById("cf-forecast-historico")?.value || "3";
  const params    = new URLSearchParams({meses, historico});
  if (_forecastExcludes.length > 0) params.set("exclude_cats", _forecastExcludes.join(","));
  const res  = await fetch(`${BASE}/api/stats/forecast?${params}`);
  const data = await res.json();
  _drawForecast(data);
}

function _drawForecast(data) {
  const historical = data.historical || [];
  const forecast   = data.forecast   || [];
  if (!historical.length) return;

  const allMonths = [...historical.map(d => d.mes), ...forecast.map(d => d.mes)];
  const labels    = allMonths.map(_fmtMes);
  const nH        = historical.length;

  // Extend historical data with nulls for forecast slots
  const egH  = [...historical.map(d => d.egresos),  ...Array(forecast.length).fill(null)];
  const inH  = [...historical.map(d => d.ingresos), ...Array(forecast.length).fill(null)];
  // Forecast starts at last historical point for visual continuity
  const egF  = [...Array(nH - 1).fill(null), historical.at(-1).egresos,  ...forecast.map(d => d.egresos)];
  const inF  = [...Array(nH - 1).fill(null), historical.at(-1).ingresos, ...forecast.map(d => d.ingresos)];

  _destroyAndCreate("chart-forecast", {
    type: "line",
    data: { labels, datasets: [
      { label:"Egresos",          data:egH, borderColor:"rgba(220,80,60,1)",   backgroundColor:"rgba(220,80,60,.08)",  borderWidth:2, pointRadius:3, tension:.3, fill:false },
      { label:"Ingresos",         data:inH, borderColor:"rgba(34,180,120,1)",  backgroundColor:"rgba(34,180,120,.08)", borderWidth:2, pointRadius:3, tension:.3, fill:false },
      { label:"Egresos (proy.)",  data:egF, borderColor:"rgba(220,80,60,.55)", backgroundColor:"transparent",           borderWidth:2, pointRadius:3, tension:.3, fill:false, borderDash:[6,4] },
      { label:"Ingresos (proy.)", data:inF, borderColor:"rgba(34,180,120,.55)",backgroundColor:"transparent",           borderWidth:2, pointRadius:3, tension:.3, fill:false, borderDash:[6,4] },
    ]},
    options: {
      responsive:true, maintainAspectRatio:true,
      spanGaps: false,
      plugins:{
        legend:{ position:"top", labels:{ boxWidth:12, font:{size:11} } },
        tooltip:{ callbacks:{ label: c => c.raw!=null ? ` ${c.dataset.label}: ${_fmtNum(c.raw)}` : null } },
      },
      scales:{ y:{ ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v } } },
    },
  });
}

// forecast controls use inline onchange="loadForecast()" — no module-level binding needed

// ── Cuentas tab ───────────────────────────────────────────────────────────────
let _cuentasData = [];

async function loadCuentas() {
  const res = await fetch(`${BASE}/api/cuentas`);
  _cuentasData = await res.json();
  _populateFuenteSelects();
  renderCuentas();
}

function renderCuentas() {
  const list = document.getElementById("cuentas-list");
  if (!_cuentasData.length) {
    list.innerHTML = `<p style="color:#aaa;padding:1rem 0">Sin cuentas.</p>`;
    return;
  }
  list.innerHTML = _cuentasData.map(c => _renderCuentaCard(c)).join("");
  // Auto-load movements for manual accounts
  _cuentasData.filter(c => c.tipo === "manual").forEach(c => loadMovimientos(c.fuente));
}

function _renderCuentaCard(c) {
  const tipo     = c.tipo || "auto";
  const isManual = tipo === "manual";
  const isMulti  = c.moneda === "MULTI";
  const isUsd    = c.moneda === "USD";

  const badge = isManual
    ? `<span class="cuenta-badge cuenta-badge-manual">Manual</span>`
    : `<span class="cuenta-badge cuenta-badge-auto">Auto</span>`;

  // Saldo display
  let saldoDisplay;
  if (isMulti) {
    const ars = c.saldo     || 0;
    const usd = c.saldo_usd || 0;
    const aC  = ars < 0 ? "negativo" : ars > 0 ? "positivo" : "";
    const uC  = usd < 0 ? "negativo" : usd > 0 ? "positivo" : "";
    saldoDisplay = `<span class="cuenta-saldo ${aC}">${_fmtSaldo(ars)} ARS</span>
                    <span class="cuenta-saldo ${uC}" style="margin-left:.4rem">${_fmtSaldo(usd)} USD</span>`;
  } else if (isUsd) {
    const usd = c.saldo_usd || 0;
    const cls = usd < 0 ? "negativo" : usd > 0 ? "positivo" : "";
    saldoDisplay = `<span class="cuenta-saldo ${cls}">${_fmtSaldo(usd)} USD</span>`;
  } else {
    const ars = c.saldo || 0;
    const cls = ars < 0 ? "negativo" : ars > 0 ? "positivo" : "";
    saldoDisplay = `<span class="cuenta-saldo ${cls}">${_fmtSaldo(ars)} ARS</span>`;
  }

  // Moneda selector (manual: ARS|USD; auto: ARS|USD|MULTI)
  const monedaOpts = (isManual ? ["ARS","USD"] : ["ARS","USD","MULTI"])
    .map(m => `<option value="${m}"${c.moneda===m?" selected":""}>${m}</option>`).join("");
  const monedaSel = `<select class="moneda-sel" title="Moneda de la cuenta"
    onchange="saveCuentaMoneda('${c.fuente}',this.value);this.blur()">${monedaOpts}</select>`;

  // "activa" controls visibility in the saldos widget at the top
  const widgetBtn = c.activa
    ? `<button class="btn btn-sm" title="Ocultar del widget de saldos" onclick="toggleCuentaActiva('${c.fuente}',0)">Widget ✓</button>`
    : `<button class="btn btn-sm" title="Mostrar en el widget de saldos" onclick="toggleCuentaActiva('${c.fuente}',1)">Widget ✗</button>`;

  // Saldo edit row (auto only — manual recalculated from movements)
  let editSaldoRow;
  if (isManual) {
    editSaldoRow = `<p class="cuenta-meta" style="padding:.1rem 1rem .5rem;color:#aaa;font-size:.75rem">
      Saldo calculado automáticamente de los movimientos.</p>`;
  } else if (isMulti) {
    editSaldoRow = `
    <div class="saldo-edit-row" id="ce-edit-${c.fuente}" style="display:none;padding:0 1rem .75rem;flex-wrap:wrap">
      <label style="font-size:.8rem;align-self:center">ARS</label>
      <input id="ce-inp-ars-${c.fuente}" type="text" value="${_fmtNum2(c.saldo||0)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <label style="font-size:.8rem;align-self:center">USD</label>
      <input id="ce-inp-usd-${c.fuente}" type="text" value="${_fmtNum2(c.saldo_usd||0)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <button class="btn btn-sm btn-primary" onclick="saveCuentaSaldo('${c.fuente}')">✓</button>
      <button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">Cancelar</button>
    </div>`;
  } else {
    const curVal = isUsd ? (c.saldo_usd||0) : (c.saldo||0);
    editSaldoRow = `
    <div class="saldo-edit-row" id="ce-edit-${c.fuente}" style="display:none;padding:0 1rem .75rem">
      <input id="ce-inp-${c.fuente}" type="text" value="${_fmtNum2(curVal)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <button class="btn btn-sm btn-primary" onclick="saveCuentaSaldo('${c.fuente}')">✓</button>
      <button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">Cancelar</button>
    </div>`;
  }

  const actions = isManual
    ? `${widgetBtn}
       <button class="btn btn-sm btn-danger" onclick="deleteCuenta('${c.fuente}')">Eliminar cuenta</button>`
    : `<button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">✏ Editar saldo</button>
       ${widgetBtn}`;

  // Movements section (manual accounts only)
  const movsSection = isManual ? `
    <div class="cuenta-movs">
      <div class="cuenta-movs-title">Movimientos</div>
      <div id="movs-list-${c.fuente}"></div>
    </div>` : "";

  return `
  <div class="cuenta-card" id="cuenta-card-${c.fuente}">
    <div class="cuenta-header">
      <span class="cuenta-nombre" title="Click para renombrar"
            onclick="startRenameCuenta('${c.fuente}')">${escHtml(c.nombre)}</span>
      ${badge}
      ${monedaSel}
      ${saldoDisplay}
    </div>
    <div class="cuenta-meta">
      ${c.fecha_actualizacion ? `Actualizado: ${c.fecha_actualizacion}` : "Sin datos"}${!isManual ? ` · <code style="font-size:.75rem">${c.fuente}</code>` : ""}
    </div>
    <div class="cuenta-actions">${actions}</div>
    ${editSaldoRow}
    ${movsSection}
  </div>`;
}

function toggleCuentaEdit(fuente) {
  const row = document.getElementById(`ce-edit-${fuente}`);
  const open = row.style.display === "none";
  row.style.display = open ? "flex" : "none";
  if (open) document.getElementById(`ce-inp-${fuente}`)?.select();
}

async function saveCuentaSaldo(fuente) {
  const cuenta = _cuentasData.find(c => c.fuente === fuente);
  const moneda = cuenta?.moneda || "ARS";
  let body = {};
  if (moneda === "MULTI") {
    body.saldo     = _parseNum(document.getElementById(`ce-inp-ars-${fuente}`)?.value || "0");
    body.saldo_usd = _parseNum(document.getElementById(`ce-inp-usd-${fuente}`)?.value || "0");
  } else if (moneda === "USD") {
    body.saldo_usd = _parseNum(document.getElementById(`ce-inp-${fuente}`)?.value || "0");
  } else {
    body.saldo = _parseNum(document.getElementById(`ce-inp-${fuente}`)?.value || "0");
  }
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  });
  loadCuentas(); loadSaldos();
}

async function saveCuentaMoneda(fuente, moneda) {
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({moneda}),
  });
  loadCuentas(); loadSaldos();
}

async function toggleCuentaActiva(fuente, activa) {
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({activa}),
  });
  loadCuentas(); loadSaldos();
}

async function deleteCuenta(fuente) {
  showConfirm("¿Eliminar esta cuenta y todos sus movimientos?", async () => {
    await fetch(`${BASE}/api/cuentas/${fuente}`, {method:"DELETE"});
    loadCuentas(); loadSaldos();
  });
}

function startRenameCuenta(fuente) {
  const span = document.querySelector(`#cuenta-card-${fuente} .cuenta-nombre`);
  if (!span || span.tagName === "INPUT") return; // already editing
  const oldName = span.textContent.trim();

  const inp = document.createElement("input");
  inp.type = "text";
  inp.value = oldName;
  inp.className = "cuenta-nombre";
  inp.style.cssText = "border:1px solid #93c5fd;border-radius:4px;padding:.1rem .4rem;" +
                      "font-size:inherit;font-weight:inherit;background:#fff;color:inherit;" +
                      "cursor:text;min-width:100px;width:auto;max-width:220px";

  let saved = false;
  async function doSave() {
    if (saved) return;
    saved = true;
    const newName = inp.value.trim();
    if (!newName || newName === oldName) { loadCuentas(); return; }
    const res = await fetch(`${BASE}/api/cuentas/${fuente}`, {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({nombre: newName}),
    });
    if (res.ok) {
      showToast(`✓ Cuenta renombrada a "${newName}"`, "ok", 2000);
      loadCuentas(); loadSaldos();
    } else {
      showToast("Error al renombrar", "err");
      loadCuentas();
    }
  }

  inp.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); doSave(); }
    if (e.key === "Escape") { saved = true; loadCuentas(); }
  });
  inp.addEventListener("blur", () => doSave());

  span.replaceWith(inp);
  inp.focus(); inp.select();
}

async function loadMovimientos(fuente) {
  const res  = await fetch(`${BASE}/api/cuentas/${fuente}/movimientos`);
  const movs = await res.json();
  const wrap = document.getElementById(`movs-list-${fuente}`);
  if (!movs.length) {
    wrap.innerHTML = `<p style="color:#aaa;font-size:.82rem;padding:.25rem 0">Sin movimientos.</p>`;
    return;
  }
  wrap.innerHTML = `<table class="cuenta-movs-table">
    <thead><tr><th>Fecha</th><th>Descripción</th><th>Monto</th><th>Cat.</th><th></th></tr></thead>
    <tbody>
      ${movs.map(m => {
        const v = parseFloat(m.monto);
        // v0.2.35: positive = egreso (red), negative = ingreso (green)
        const isEg = v > 0;
        const cls  = isEg ? "mov-monto-neg" : "mov-monto-pos";
        const sign = isEg ? "" : "+";
        return `<tr>
          <td>${m.fecha}</td>
          <td>${escHtml(m.descripcion)}</td>
          <td class="${cls}">${sign}${_fmtNum2(Math.abs(v))} ${escHtml(m.moneda)}</td>
          <td>${escHtml(m.categoria||"")}</td>
          <td><button class="btn btn-sm btn-danger" style="padding:.15rem .4rem"
              onclick="deleteMovimiento('${fuente}',${m.id})">✕</button></td>
        </tr>`;
      }).join("")}
    </tbody>
  </table>`;
}

async function deleteMovimiento(fuente, id) {
  await fetch(`${BASE}/api/cuentas/${fuente}/movimientos/${id}`, {method:"DELETE"});
  loadMovimientos(fuente);
  loadCuentas(); loadSaldos();
}

async function deleteGasto(id) {
  showConfirm("¿Eliminar este movimiento manual?", async () => {
    const res = await fetch(`${BASE}/api/gastos/${id}`, {method:"DELETE"});
    if (res.ok) { loadGastos(); loadSaldos(); }
    else showToast("No se puede eliminar (solo manuales).", "err");
  });
}

document.getElementById("btn-add-cuenta").addEventListener("click", () => {
  showPrompt("Nombre de la nueva cuenta:", "ej: Efectivo, Cuenta Nación", nombre => {
    showSelectPrompt("Moneda de la cuenta:", [
      {value:"ARS", label:"ARS – pesos"},
      {value:"USD", label:"USD – dólares"},
    ], async moneda => {
      const res = await fetch(`${BASE}/api/cuentas`, {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({nombre, moneda}),
      });
      if (res.ok) { showToast(`Cuenta "${nombre}" (${moneda}) creada.`, "ok"); loadCuentas(); loadSaldos(); }
      else showToast("Error al crear la cuenta.", "err");
    });
  });
});

// ── Personas (Config tab) ─────────────────────────────────────────────────────
let _usuariosConfig = {usuarios: ["Titular","Adicional"], fuente_usuario: {}, reglas_usuario: []};
let _userRules = [];

async function loadUsuarios() {
  const res = await fetch(`${BASE}/api/config/usuarios`);
  _usuariosConfig = await res.json();
  _userRules = (_usuariosConfig.reglas_usuario || []).map(r => ({
    palabras: Array.isArray(r.palabras) ? r.palabras.map(String) : [],
    usuario:  r.usuario || "",
  }));
  _populateUsuarioDropdowns();
  renderUsuarios();
  renderUserRules();
}

function _populateUsuarioDropdowns() {
  // TODO: agregar opción "Sin usuario" (value="__none__") para filtrar gastos
  // sin persona asignada y poder categorizarlos fácilmente desde la tabla.
  ["filter-usuario","cf-usuario"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">Todos</option>` +
      (_usuariosConfig.usuarios || []).map(u =>
        `<option value="${escHtml(u)}">${escHtml(u)}</option>`
      ).join("");
    if (cur) sel.value = cur;
  });
}

function renderUsuarios() {
  const list = document.getElementById("usuarios-list");
  if (!list) return;
  const users = _usuariosConfig.usuarios || [];
  // Chips for existing users + an inline "+" chip at the end
  list.innerHTML = users.map((u, i) => `
    <div class="usuario-chip" title="Click para renombrar">
      <span onclick="startRenameUsuario(${i})">${escHtml(u)}</span>
      ${i >= 2 ? `<button class="tag-x" type="button" onclick="removeUsuario(${i})">×</button>` : ""}
    </div>`).join("") +
    `<div class="usuario-chip usuario-add-chip" id="usuario-add-chip" onclick="startAddUsuario()" title="Agregar usuario">
      <span>+</span>
    </div>`;

  const _autoFuentesFallback = [
    {id:"amex",        label:"AMEX"},
    {id:"bbva_mc",     label:"BBVA Mastercard"},
    {id:"bbva_visa",   label:"BBVA Visa"},
    {id:"bbva_cuenta", label:"BBVA Cuenta"},
    {id:"galicia_mc",  label:"Galicia MC"},
    {id:"mercadopago", label:"MercadoPago"},
  ];
  const _FUENTES = _cuentasData.length > 0
    ? _cuentasData.filter(c => c.tipo !== "manual").map(c => ({id: c.fuente, label: c.nombre}))
    : _autoFuentesFallback;
  const map = document.getElementById("fuente-usuario-map");
  if (!map) return;
  const fuMap = _usuariosConfig.fuente_usuario || {};
  map.innerHTML = `
    <table class="presup-table" style="max-width:500px">
      <thead><tr><th>Fuente</th><th>Persona por defecto</th></tr></thead>
      <tbody>
        ${_FUENTES.map(f => `<tr>
          <td>${f.label}</td>
          <td>
            <select class="fuente-usuario-sel" data-fuente="${f.id}"
                    onchange="saveFuenteUsuario('${f.id}',this.value)">
              <option value="">— Sin asignar —</option>
              ${users.map(u =>
                `<option value="${escHtml(u)}" ${fuMap[f.id]===u?"selected":""}>${escHtml(u)}</option>`
              ).join("")}
            </select>
          </td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

async function removeUsuario(i) {
  if (i < 2) return;
  _usuariosConfig.usuarios.splice(i, 1);
  await _saveUsuariosConfig();
  _populateUsuarioDropdowns();
  renderUsuarios();
}

async function saveFuenteUsuario(fuente, usuario) {
  _usuariosConfig.fuente_usuario = _usuariosConfig.fuente_usuario || {};
  _usuariosConfig.fuente_usuario[fuente] = usuario;
  await _saveUsuariosConfig();
  showToast("✓ Guardado", "ok", 1500);
}

async function _saveUsuariosConfig() {
  _syncUserRules();
  await fetch(`${BASE}/api/config/usuarios`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({..._usuariosConfig, reglas_usuario: _userRules}),
  });
}

function startAddUsuario() {
  const chip = document.getElementById("usuario-add-chip");
  if (!chip) return;
  chip.onclick = null;
  chip.innerHTML = `
    <input id="nuevo-usuario-input" type="text" placeholder="Nombre…"
           style="border:none;background:transparent;outline:none;font-size:.85rem;width:110px"
           onkeydown="handleAddUsuarioKey(event)">
    <button class="tag-x" type="button" onclick="saveNewUsuario()">✓</button>
    <button class="tag-x" type="button" onclick="renderUsuarios()">×</button>`;
  document.getElementById("nuevo-usuario-input")?.focus();
}

async function saveNewUsuario() {
  const n = (document.getElementById("nuevo-usuario-input")?.value || "").trim();
  if (!n) { renderUsuarios(); return; }
  if ((_usuariosConfig.usuarios || []).includes(n)) {
    showToast("Ya existe esa persona.", "err"); return;
  }
  _usuariosConfig.usuarios = [...(_usuariosConfig.usuarios || []), n];
  await _saveUsuariosConfig();
  _populateUsuarioDropdowns();
  renderUsuarios();
  showToast(`✓ Persona "${n}" agregada`, "ok");
}

function handleAddUsuarioKey(e) {
  if (e.key === "Enter")  { e.preventDefault(); saveNewUsuario(); }
  if (e.key === "Escape") renderUsuarios();
}

function startRenameUsuario(i) {
  const chips = document.querySelectorAll("#usuarios-list .usuario-chip:not(.usuario-add-chip)");
  const chip  = chips[i];
  if (!chip) return;
  const span = chip.querySelector("span");
  if (!span) return;
  const old = _usuariosConfig.usuarios[i] || "";
  span.outerHTML = `
    <input id="ru-inp-${i}" type="text" value="${escHtml(old)}"
           style="border:none;background:transparent;outline:none;font-size:.85rem;width:110px;color:inherit"
           onkeydown="handleRenameUsuarioKey(event,${i})">
    <button class="tag-x" type="button" onclick="saveRenameUsuario(${i})">✓</button>
    <button class="tag-x" type="button" onclick="renderUsuarios()">×</button>`;
  const inp = document.getElementById(`ru-inp-${i}`);
  inp?.focus(); inp?.select();
}

async function saveRenameUsuario(i) {
  const inp     = document.getElementById(`ru-inp-${i}`);
  const newName = (inp?.value || "").trim();
  const oldName = _usuariosConfig.usuarios[i];
  if (!newName || newName === oldName) { renderUsuarios(); return; }
  if ((_usuariosConfig.usuarios || []).some((u, j) => j !== i && u === newName)) {
    showToast("Ya existe esa persona.", "err"); return;
  }
  _usuariosConfig.usuarios[i] = newName;
  // Propagate rename into fuente_usuario map
  Object.keys(_usuariosConfig.fuente_usuario || {}).forEach(f => {
    if (_usuariosConfig.fuente_usuario[f] === oldName)
      _usuariosConfig.fuente_usuario[f] = newName;
  });
  // Propagate into user rules
  _userRules.forEach(r => { if (r.usuario === oldName) r.usuario = newName; });
  await _saveUsuariosConfig();
  // Also rename in existing gastos rows in the DB
  const dbRes = await fetch(`${BASE}/api/config/usuarios/rename-db`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({old: oldName, new: newName}),
  });
  const dbData = dbRes.ok ? await dbRes.json() : {};
  _populateUsuarioDropdowns();
  renderUsuarios();
  renderUserRules();
  const extra = dbData.actualizados > 0 ? ` (${dbData.actualizados} gastos actualizados)` : "";
  showToast(`✓ "${oldName}" → "${newName}"${extra}`, "ok", 3000);
}

function handleRenameUsuarioKey(e, i) {
  if (e.key === "Enter")  { e.preventDefault(); saveRenameUsuario(i); }
  if (e.key === "Escape") renderUsuarios();
}

loadUsuarios();
loadImportaciones();

// ── Reglas de asignación de persona ──────────────────────────────────────────

function renderUserRules() {
  const list = document.getElementById("user-rules-list");
  if (!list) return;
  const users = _usuariosConfig.usuarios || ["Titular", "Adicional"];
  list.innerHTML = "";
  _userRules.forEach((rule, i) => {
    const card = document.createElement("div");
    card.className = "rule-card";
    const tagsHtml = rule.palabras.map((w, j) =>
      `<span class="tag"><span class="tag-label" title="Doble clic para editar" ondblclick="editUserTag(${i},${j})">${escHtml(w)}</span><button class="tag-x" type="button" onclick="removeUserTag(${i},${j})">×</button></span>`
    ).join("");
    const userOpts = users.map(u =>
      `<option value="${escHtml(u)}" ${rule.usuario === u ? "selected" : ""}>${escHtml(u)}</option>`
    ).join("");
    card.innerHTML = `
      <div class="rule-header">
        <select class="user-rule-sel" data-i="${i}" style="min-width:140px">
          <option value="">— Persona —</option>
          ${userOpts}
        </select>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeUserRule(${i})">Eliminar</button>
      </div>
      <div class="rule-tags" id="user-tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input user-tag-input" data-i="${i}"
               placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addUserTag(event,${i})">
      </div>`;
    list.appendChild(card);
  });
}

function _syncUserRules() {
  document.querySelectorAll(".user-rule-sel").forEach((sel, i) => {
    if (_userRules[i]) _userRules[i].usuario = sel.value;
  });
}

let _saveUserRulesTimer = null;
function _scheduleSaveUserRules() {
  clearTimeout(_saveUserRulesTimer);
  _saveUserRulesTimer = setTimeout(async () => {
    _syncUserRules();
    const reglas = _userRules.filter(r => r.palabras.length > 0 && r.usuario);
    const res = await fetch(`${BASE}/api/config/usuarios`, {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({..._usuariosConfig, reglas_usuario: reglas}),
    });
    showToast(res.ok ? "✓ Reglas guardadas" : "❌ Error al guardar", res.ok ? "ok" : "err", res.ok ? 2000 : 0);
  }, 800);
}

document.getElementById("user-rules-list")?.addEventListener("focusout", _scheduleSaveUserRules);

function removeUserRule(i)   { _syncUserRules(); _userRules.splice(i, 1); renderUserRules(); _scheduleSaveUserRules(); }
function removeUserTag(i, j) { _syncUserRules(); _userRules[i].palabras.splice(j, 1); renderUserRules(); _scheduleSaveUserRules(); }
function addUserTag(event, i) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const word = event.target.value.trim();
  if (!word) return;
  _syncUserRules();
  if (!_userRules[i].palabras.includes(word)) _userRules[i].palabras.push(word);
  renderUserRules();
  document.querySelectorAll(".user-tag-input")[i]?.focus();
  _scheduleSaveUserRules();
}
function editUserTag(i, j) {
  _syncUserRules();
  const labelEl = document.querySelector(`#user-tags-${i} .tag:nth-child(${j+1}) .tag-label`);
  if (!labelEl) return;
  const orig = _userRules[i].palabras[j];
  const inp = document.createElement("input");
  inp.className = "tag-edit-input";
  inp.value = orig;
  inp.style.width = Math.max(60, orig.length * 8) + "px";
  let saved = false;
  function doSave() {
    if (saved) return; saved = true;
    const val = inp.value.trim();
    if (!val) { _userRules[i].palabras.splice(j, 1); }
    else       { _userRules[i].palabras[j] = val; }
    renderUserRules(); _scheduleSaveUserRules();
  }
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); doSave(); }
    if (e.key === "Escape") { saved = true; renderUserRules(); }
  });
  inp.addEventListener("blur", doSave);
  labelEl.replaceWith(inp);
  inp.focus(); inp.select();
}

document.getElementById("btn-add-user-rule")?.addEventListener("click", () => {
  _syncUserRules();
  _userRules.push({palabras: [], usuario: ""});
  renderUserRules();
  const el = document.querySelectorAll(".user-rule-sel").at(-1);
  el?.focus();
  el?.scrollIntoView({behavior: "smooth", block: "nearest"});
});

document.getElementById("btn-apply-user-rules")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-user-rules");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/config/usuarios/apply`, {method: "POST"});
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${data.asignados} movimientos asignados`, "ok");
      loadGastos();
    } else {
      showToast("Error al aplicar reglas", "err", 0);
    }
  } finally { btn.disabled = false; btn.textContent = "Reaplicar a todos"; }
});

// ── Scrapers config ───────────────────────────────────────────────────────────
// Estado local de las credenciales (se carga desde la API, nunca incluye passwords reales)
let _scraperCreds = {};
let _scraperStatuses = {};

async function renderScrapersConfig() {
  const container = document.getElementById("scrapers-config-list");
  if (!container) return;

  // Cargar credenciales y estado en paralelo
  try {
    const [credsRes, statusRes] = await Promise.all([
      fetch(`${BASE}/api/scrapers/credentials`),
      fetch(`${BASE}/api/scrapers/status`),
    ]);
    _scraperCreds    = credsRes.ok    ? await credsRes.json()    : {};
    const statuses   = statusRes.ok   ? await statusRes.json()   : [];
    _scraperStatuses = Object.fromEntries(statuses.map(s => [s.fuente, s]));
  } catch (e) {
    container.innerHTML = `<p style="color:#b91c1c">Error cargando configuración: ${escHtml(e.message)}</p>`;
    return;
  }

  container.innerHTML = "";
  for (const [banco, data] of Object.entries(_scraperCreds)) {
    container.appendChild(_buildScraperCard(banco, data));
  }
}

function _buildScraperCard(banco, data) {
  const st      = _scraperStatuses[banco] || {};
  const enabled = data.enabled || false;

  // ── Badge de estado ──────────────────────────────────────────────────
  const badgeClass = {
    ok:      "scraper-status-ok",
    error:   "scraper-status-error",
    running: "scraper-status-running",
    session_expired: "scraper-status-error",
  }[st.estado] || "scraper-status-idle";

  const badgeText = {
    ok:              "✓ OK",
    error:           "✗ Error",
    running:         "⟳ Corriendo",
    session_expired: "⚠ Sesión expirada",
    idle:            "Sin correr",
  }[st.estado] || "Sin correr";

  // ── Campos ─────────────────────────────────────────────────────────────
  const fieldsHtml = (data.campos || []).map(campo => {
    const val = (data[campo.key] || "");
    const hasPwd = campo.type === "password" && data[`has_${campo.key}`];
    const placeholder = campo.type === "password"
      ? (hasPwd ? "••••••••  (guardada — dejá vacío para no cambiar)" : "Nueva contraseña")
      : (campo.hint ? campo.hint : "");
    const hintHtml = campo.hint && campo.type !== "password"
      ? `<span class="field-hint">${escHtml(campo.hint)}</span>` : "";
    const hasPwdHtml = hasPwd
      ? `<span class="has-pwd-note">✓ Contraseña guardada</span>` : "";
    return `
      <div class="scraper-field">
        <label for="scr-${banco}-${campo.key}">${escHtml(campo.label)}</label>
        <input id="scr-${banco}-${campo.key}"
               type="${campo.type === 'password' ? 'password' : 'text'}"
               value="${campo.type === 'password' ? '' : escHtml(val)}"
               placeholder="${escHtml(placeholder)}"
               autocomplete="${campo.type === 'password' ? 'new-password' : 'off'}">
        ${hintHtml}${hasPwdHtml}
      </div>`;
  }).join("");

  // ── TOTP (solo Galicia) ────────────────────────────────────────────────
  const totpHtml = data.totp ? `
    <div class="scraper-totp-area" id="totp-area-${banco}">
      <label>Código de verificación (TOTP / email)</label>
      <p style="font-size:.82rem;color:#92400e;margin-bottom:.5rem">
        Primero hacé click en "Iniciar sesión" — el servidor abrirá el browser,
        completará usuario y contraseña y te pedirá el código de verificación aquí.
      </p>
      <div class="scraper-totp-row">
        <input id="totp-input-${banco}" type="text" maxlength="8"
               placeholder="123456" inputmode="numeric">
        <button class="btn btn-sm btn-primary" onclick="submitTotpCode('${banco}')">Enviar código</button>
      </div>
      <p id="totp-msg-${banco}" style="font-size:.8rem;margin-top:.4rem"></p>
    </div>` : "";

  // ── Card completa ──────────────────────────────────────────────────────
  const card = document.createElement("div");
  card.className = "scraper-card";
  card.id = `scraper-card-${banco}`;
  card.innerHTML = `
    <div class="scraper-card-header" onclick="_toggleScraperCard('${banco}')">
      <label class="scraper-toggle" onclick="event.stopPropagation()">
        <input type="checkbox" id="scr-${banco}-enabled"
               ${enabled ? "checked" : ""}
               onchange="_toggleScraperEnabled('${banco}', this.checked)">
        <span class="scraper-toggle-slider"></span>
      </label>
      <span class="scraper-name">${escHtml(data.nombre || banco)}</span>
      <span class="scraper-status-badge ${badgeClass}">${badgeText}</span>
      <span style="font-size:.8rem;color:#999;margin-left:auto">▼</span>
    </div>
    <div class="scraper-card-body ${enabled ? 'open' : ''}" id="scraper-body-${banco}">
      <div class="scraper-fields">
        ${fieldsHtml}
        <div class="scraper-field">
          <label for="scr-${banco}-schedule">Hora de ejecución diaria</label>
          <input id="scr-${banco}-schedule" type="time"
                 value="${escHtml(data.schedule || '07:00')}">
        </div>
      </div>
      ${totpHtml}
      <div class="scraper-actions">
        <button class="btn btn-primary btn-sm" onclick="saveScraperConfig('${banco}')">
          Guardar
        </button>
        <button class="btn btn-sm" onclick="runScraperNow('${banco}')" id="btn-run-${banco}">
          ▶ Ejecutar ahora
        </button>
        ${data.totp ? `<button class="btn btn-sm" onclick="startTotpSetup('${banco}')" id="btn-totp-${banco}">
          🔑 Iniciar sesión TOTP
        </button>` : ""}
        <button class="btn btn-sm" style="color:#b91c1c" onclick="deleteScraperSession('${banco}')">
          🗑 Borrar sesión
        </button>
        <span class="scraper-save-msg" id="save-msg-${banco}"></span>
      </div>
      ${st.error_msg ? `<p style="font-size:.8rem;color:#b91c1c;margin-top:.5rem">
        Último error: ${escHtml(st.error_msg)}</p>` : ""}
      ${st.ultimo_ok ? `<p style="font-size:.78rem;color:#888;margin-top:.25rem">
        Último OK: ${escHtml(st.ultimo_ok.replace('T',' ').slice(0,16))}</p>` : ""}
      ${st.last_log ? `<details class="scraper-log-details">
        <summary>
          <span>📋 Detalle del último run</span>
          <button class="btn-copy-log" id="copy-log-btn-${banco}"
                  onclick="event.stopPropagation();copyScraperLog('${banco}')"
                  title="Copiar al portapapeles">⎘ Copiar</button>
        </summary>
        <pre class="scraper-log-pre" id="scraper-log-pre-${banco}">${escHtml(st.last_log)}</pre>
      </details>` : ""}
      <details class="scraper-movs-details" id="movs-details-${banco}">
        <summary onclick="loadScraperMovimientos('${banco}')">
          <span>📦 Registros ingresados</span>
          <button class="btn-refresh-movs" id="btn-refresh-movs-${banco}"
                  onclick="event.stopPropagation();refreshScraperMovimientos('${banco}')"
                  title="Actualizar lista">↻</button>
        </summary>
        <div id="movs-list-${banco}" class="scraper-movs-list">
          <span style="font-size:.78rem;color:#94a3b8">Abrí para ver los registros.</span>
        </div>
      </details>
    </div>`;
  return card;
}

function _toggleScraperCard(banco) {
  const body = document.getElementById(`scraper-body-${banco}`);
  if (body) body.classList.toggle("open");
}

function _toggleScraperEnabled(banco, checked) {
  // Abrir/cerrar el cuerpo de la card según el toggle
  const body = document.getElementById(`scraper-body-${banco}`);
  if (body) {
    if (checked) body.classList.add("open");
    else body.classList.remove("open");
  }
}

async function saveScraperConfig(banco) {
  const data = _scraperCreds[banco] || {};
  const campos = data.campos || [];

  // Leer valores del form
  const body = { enabled: document.getElementById(`scr-${banco}-enabled`)?.checked || false };
  for (const campo of campos) {
    const el = document.getElementById(`scr-${banco}-${campo.key}`);
    if (el) body[campo.key] = el.value;
  }
  const schedEl = document.getElementById(`scr-${banco}-schedule`);
  if (schedEl) body.schedule = schedEl.value;

  const msgEl = document.getElementById(`save-msg-${banco}`);
  if (msgEl) { msgEl.className = "scraper-save-msg"; msgEl.textContent = ""; }

  try {
    const res = await fetch(`${BASE}/api/scrapers/credentials/${banco}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Error desconocido" }));
      throw new Error(err.detail || "Error al guardar");
    }
    if (msgEl) { msgEl.className = "scraper-save-msg ok"; msgEl.textContent = "✓ Guardado"; }
    // Refrescar la tarjeta después de guardar para actualizar has_password
    setTimeout(renderScrapersConfig, 800);
  } catch (e) {
    if (msgEl) { msgEl.className = "scraper-save-msg error"; msgEl.textContent = "✗ " + e.message; }
  }
}

async function runScraperNow(banco) {
  const btn = document.getElementById(`btn-run-${banco}`);
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Corriendo…"; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/run`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${banco}: ${data.movimientos ?? 0} movimientos nuevos`, "ok");
    } else {
      showToast(`✗ ${banco}: ${data.detail || "Error"}`, "err", 0);
    }
    // Refrescar estado
    setTimeout(renderScrapersConfig, 1000);
  } catch (e) {
    showToast(`✗ Error: ${e.message}`, "err", 0);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "▶ Ejecutar ahora"; }
  }
}

async function deleteScraperSession(banco) {
  if (!confirm(`¿Borrar la sesión guardada de ${banco}? Se volverá a hacer login en el próximo run.`)) return;
  const res  = await fetch(`${BASE}/api/scrapers/${banco}/session`, { method: "DELETE" });
  const data = await res.json();
  showToast(data.message || "Sesión eliminada", res.ok ? "ok" : "err");
}

// ── Log de diagnóstico ────────────────────────────────────────────────────────

function copyScraperLog(banco) {
  const pre = document.getElementById(`scraper-log-pre-${banco}`);
  if (!pre) return;
  navigator.clipboard.writeText(pre.textContent).then(() => {
    const btn = document.getElementById(`copy-log-btn-${banco}`);
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "✓ Copiado";
      setTimeout(() => { btn.textContent = orig; }, 2000);
    }
  }).catch(() => showToast("No se pudo copiar", "err"));
}

// ── Registros ingresados (movimientos_raw) ─────────────────────────────────────

const _ESTADO_MOV = {
  new:       { cls: "mov-estado-new",       txt: "Nuevo"      },
  matched:   { cls: "mov-estado-matched",   txt: "Conciliado" },
  unmatched: { cls: "mov-estado-unmatched", txt: "Sin match"  },
  imported:  { cls: "mov-estado-imported",  txt: "Importado"  },
  ignored:   { cls: "mov-estado-ignored",   txt: "Ignorado"   },
};

async function loadScraperMovimientos(banco) {
  const details = document.getElementById(`movs-details-${banco}`);
  const el      = document.getElementById(`movs-list-${banco}`);
  if (!el || !details) return;
  if (details.open) return;          // clicking to close — do nothing
  if (details.dataset.loaded === "1") return;   // already loaded
  details.dataset.loaded = "1";
  await _fetchScraperMovimientos(banco, el);
}

async function refreshScraperMovimientos(banco) {
  const details = document.getElementById(`movs-details-${banco}`);
  const el      = document.getElementById(`movs-list-${banco}`);
  if (!el) return;
  if (details) details.dataset.loaded = "0";
  if (details && !details.open) details.open = true;
  details.dataset.loaded = "1";
  await _fetchScraperMovimientos(banco, el);
}

async function _fetchScraperMovimientos(banco, el) {
  el.innerHTML = '<span style="font-size:.78rem;color:#94a3b8">Cargando…</span>';
  try {
    const res  = await fetch(`${BASE}/api/scrapers/movimientos-raw?fuente=${encodeURIComponent(banco)}&limit=100`);
    const rows = res.ok ? await res.json() : [];
    if (!rows.length) {
      el.innerHTML = '<span style="font-size:.78rem;color:#94a3b8">Sin registros guardados.</span>';
      return;
    }
    el.innerHTML = rows.map(r => {
      const b      = _ESTADO_MOV[r.estado] || { cls: "", txt: r.estado };
      const monto  = Math.abs(r.monto).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const prefix = r.moneda === "USD" ? "U$S " : "$ ";
      const neg    = r.monto < 0;
      return `<div class="scraper-mov-row" id="mov-row-${r.id}">
        <span class="scraper-mov-fecha">${escHtml(r.fecha)}</span>
        <span class="scraper-mov-desc" title="${escHtml(r.descripcion)}">${escHtml(r.descripcion)}</span>
        <span class="scraper-mov-monto${neg ? " neg" : ""}">${prefix}${monto}</span>
        <span class="mov-estado-badge ${b.cls}">${b.txt}</span>
        <button class="btn-del-mov" onclick="deleteMovimientoRaw(${r.id},'${banco}')" title="Borrar">✕</button>
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<span style="font-size:.78rem;color:#b91c1c">Error: ${escHtml(e.message)}</span>`;
  }
}

async function deleteMovimientoRaw(rawId, banco) {
  if (!confirm("¿Borrar este registro?\nSi fue importado a gastos, también se borrará el gasto.")) return;
  try {
    const res = await fetch(`${BASE}/api/scrapers/movimientos-raw/${rawId}`, { method: "DELETE" });
    if (res.ok) {
      const row = document.getElementById(`mov-row-${rawId}`);
      if (row) { row.style.opacity = "0"; setTimeout(() => row.remove(), 200); }
    } else {
      const d = await res.json().catch(() => ({}));
      showToast(`✗ ${d.detail || "Error al borrar"}`, "err");
    }
  } catch(e) {
    showToast(`✗ ${e.message}`, "err");
  }
}

// ── TOTP (Galicia) ─────────────────────────────────────────────────────────────
let _totpRequestId = {};

async function startTotpSetup(banco) {
  const btn = document.getElementById(`btn-totp-${banco}`);
  if (btn) { btn.disabled = true; btn.textContent = "Iniciando…"; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/session-setup`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error");
    _totpRequestId[banco] = data.request_id;
    // Mostrar área de TOTP
    const area = document.getElementById(`totp-area-${banco}`);
    if (area) area.classList.add("open");
    document.getElementById(`totp-input-${banco}`)?.focus();
    showToast("Browser iniciado — esperando código TOTP", "ok", 5000);
  } catch (e) {
    showToast(`✗ ${e.message}`, "err", 0);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🔑 Iniciar sesión TOTP"; }
  }
}

async function submitTotpCode(banco) {
  const code = document.getElementById(`totp-input-${banco}`)?.value?.trim();
  if (!code) { showToast("Ingresá el código primero", "err"); return; }
  const requestId = _totpRequestId[banco];
  if (!requestId) { showToast("Primero iniciá la sesión TOTP", "err"); return; }

  const msgEl = document.getElementById(`totp-msg-${banco}`);
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/totp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error");
    if (msgEl) { msgEl.style.color = "#166534"; msgEl.textContent = "✓ " + data.message; }
    // Ocultar área después de éxito
    setTimeout(() => {
      const area = document.getElementById(`totp-area-${banco}`);
      if (area) area.classList.remove("open");
      delete _totpRequestId[banco];
    }, 3000);
  } catch (e) {
    if (msgEl) { msgEl.style.color = "#b91c1c"; msgEl.textContent = "✗ " + e.message; }
  }
}

// ── PWA Shortcuts config ──────────────────────────────────────────────────────

const _FUENTES_CONOCIDAS = [
  { fuente: "amex",        label: "AMEX" },
  { fuente: "bbva_mc",     label: "BBVA Mastercard" },
  { fuente: "bbva_visa",   label: "BBVA Visa" },
  { fuente: "bbva_cuenta", label: "BBVA Cuenta" },
  { fuente: "galicia_mc",  label: "Galicia Mastercard" },
  { fuente: "mercadopago", label: "MercadoPago" },
];

let _pwaShortcuts = [];     // [{fuente, label}, ...]
let _cuentasManuales = [];  // cuentas manuales del usuario

async function renderPwaShortcuts() {
  try {
    const [scRes, cRes] = await Promise.all([
      fetch(`${BASE}/api/config/pwa-shortcuts`),
      fetch(`${BASE}/api/cuentas`),
    ]);
    _pwaShortcuts    = scRes.ok ? await scRes.json() : [];
    const allCuentas = cRes.ok ? await cRes.json() : [];
    _cuentasManuales = allCuentas.filter(c => c.tipo === "manual");
  } catch {
    _pwaShortcuts = [];
  }
  _renderPwaShortcutsList();
}

function _allFuenteOptions() {
  const opts = [..._FUENTES_CONOCIDAS];
  for (const c of _cuentasManuales) {
    if (!opts.find(o => o.fuente === c.fuente)) {
      opts.push({ fuente: c.fuente, label: c.nombre });
    }
  }
  return opts;
}

function _renderPwaShortcutsList() {
  const container = document.getElementById("pwa-shortcuts-list");
  if (!container) return;
  if (!_pwaShortcuts.length) {
    container.innerHTML = `<p style="color:var(--text-muted);font-style:italic;font-size:.85rem">Sin accesos rápidos configurados.</p>`;
    _renderIosGuide();
    return;
  }
  const opts = _allFuenteOptions();
  container.innerHTML = _pwaShortcuts.map((sc, idx) => `
    <div style="display:flex;align-items:center;gap:.5rem">
      <select onchange="_pwaShortcutChange(${idx},'fuente',this.value)" style="flex:1;padding:.35rem .5rem;font-size:.85rem;border:1px solid #ccc;border-radius:4px">
        ${opts.map(o => `<option value="${escHtml(o.fuente)}" ${o.fuente===sc.fuente?"selected":""}>${escHtml(o.label)}</option>`).join("")}
      </select>
      <input type="text" value="${escHtml(sc.label)}" placeholder="Nombre del shortcut"
        oninput="_pwaShortcutChange(${idx},'label',this.value)"
        style="flex:1;padding:.35rem .5rem;font-size:.85rem;border:1px solid #ccc;border-radius:4px">
      <button class="btn btn-sm btn-danger" onclick="_removePwaShortcut(${idx})" style="padding:.3rem .6rem">✕</button>
    </div>
  `).join("");
  _renderIosGuide();
}

function _renderIosGuide() {
  const el = document.getElementById("pwa-ios-guide");
  if (!el) return;
  if (!_pwaShortcuts.length) { el.innerHTML = ""; return; }

  const prefix = window.INGRESS_PREFIX || "";
  const links = _pwaShortcuts.map(sc => {
    const url = `${prefix}/quick?fuente=${encodeURIComponent(sc.fuente)}&label=${encodeURIComponent(sc.label)}`;
    return `<a href="${url}" target="_blank" style="display:inline-flex;align-items:center;gap:.35rem;padding:.3rem .7rem;border:1px solid #cbd5e1;border-radius:6px;font-size:.85rem;text-decoration:none;color:inherit;background:#f8fafc">
      <span style="font-size:1rem">↗</span> ${escHtml(sc.label)}
    </a>`;
  }).join("");

  el.innerHTML = `
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:.85rem 1rem;margin-bottom:1.5rem;background:#f8fafc">
      <div style="font-weight:600;font-size:.85rem;margin-bottom:.5rem">Instalar en iOS</div>
      <p style="font-size:.82rem;color:#64748b;margin-bottom:.65rem;line-height:1.5">
        Abrí el link de cada acceso rápido en Safari, luego
        <strong>Compartir → Agregar al inicio</strong>.
        Cada uno queda como ícono independiente con el nombre correcto.
      </p>
      <div style="display:flex;flex-wrap:wrap;gap:.4rem">${links}</div>
    </div>`;
}

function _pwaShortcutChange(idx, field, value) {
  if (_pwaShortcuts[idx]) _pwaShortcuts[idx][field] = value;
}

function _removePwaShortcut(idx) {
  _pwaShortcuts.splice(idx, 1);
  _renderPwaShortcutsList();
}

function addPwaShortcut() {
  const opts = _allFuenteOptions();
  const first = opts[0] || { fuente: "amex", label: "AMEX" };
  _pwaShortcuts.push({ fuente: first.fuente, label: first.label });
  _renderPwaShortcutsList();
}

async function savePwaShortcuts() {
  const res = await fetch(`${BASE}/api/config/pwa-shortcuts`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(_pwaShortcuts),
  });
  if (res.ok) showToast("Shortcuts guardados. Recargá la PWA para verlos.", "ok", 4000);
  else        showToast("Error al guardar shortcuts.", "err");
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function showResult(el, msg, ok) { el.textContent = msg; el.className = ok?"ok":"err"; }
