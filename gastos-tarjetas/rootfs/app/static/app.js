const BASE = window.INGRESS_PREFIX || "";
if (window.APP_VERSION) {
  const el = document.getElementById("app-version");
  if (el) el.textContent = "v" + window.APP_VERSION;
}

// ── UI settings (colors + prefs) applied immediately from localStorage ────────
const UI_COLOR_DEFAULTS = {
  ars: "#15803d", usd: "#2563eb", rg: "#94a3b8", tog: "#d97706", accent: "#16213e",
  cat_parent: "#111827", cat_child: "#4b5563",
  // Montos y gráficos (configurables)
  egreso: "#dc2626", ingreso: "#16a34a",   // grilla + chart mes a mes
  presup: "#22c55e", real: "#eab308",       // chart Presupuesto vs Real
  venc_urg: "#dc2626", venc_pronto: "#f59e0b",  // urgencia de vencimientos
};

// Lee una variable CSS del :root (para pasar colores configurables a Chart.js).
function _cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
const UI_PREF_DEFAULTS = {
  dias_urgente:          3,
  dias_pronto:           7,
  graf_meses:            "6",
  graf_moneda:           "ARS",
  font_size:             14,
  venc_show_proximos:    true,
  venc_show_rg5617:      true,
  venc_show_pdf_ref:     true,
  chart_home_mode:       "normal",     // "normal" | "compact" | "hidden"
  bud_chart_mode:        "normal",     // "normal" | "compact" | "hidden"
  tab_icon_mode:         "icons_text", // "icons_text" | "icons" | "text"
  pago_btn_mode:         "icons_text", // botones de acción de Pagos: "icons_text" | "icons" | "text"
  widget_refresh_mins:   "5",          // intervalo de refresco automático de widgets ("0" = desactivado)
};

function getUiPref(key) {
  const stored = JSON.parse(localStorage.getItem("ui_prefs") || "{}");
  return key in stored ? stored[key] : UI_PREF_DEFAULTS[key];
}

function applyUiColors() {
  const stored = JSON.parse(localStorage.getItem("ui_colors") || "{}");
  const c = { ...UI_COLOR_DEFAULTS, ...stored };
  const root = document.documentElement;
  root.style.setProperty("--color-ars",        c.ars);
  root.style.setProperty("--color-usd",        c.usd);
  root.style.setProperty("--color-rg5617",     c.rg);
  root.style.setProperty("--color-toggle-rg",  c.tog);
  root.style.setProperty("--color-accent",     c.accent);
  root.style.setProperty("--color-cat-parent", c.cat_parent);
  root.style.setProperty("--color-cat-child",  c.cat_child);
  root.style.setProperty("--color-egreso",      c.egreso);
  root.style.setProperty("--color-ingreso",     c.ingreso);
  root.style.setProperty("--color-presup",      c.presup);
  root.style.setProperty("--color-real",        c.real);
  root.style.setProperty("--color-venc-urg",    c.venc_urg);
  root.style.setProperty("--color-venc-pronto", c.venc_pronto);
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
  // Home chart size
  _applyChartMode(getUiPref("chart_home_mode"));
  _applyBudChartMode(getUiPref("bud_chart_mode"));
  // Tab icon mode
  _applyTabIconMode(getUiPref("tab_icon_mode"));
  // Pago action buttons mode (independiente del de pestañas)
  _applyPagoBtnMode(getUiPref("pago_btn_mode"));
  // Top charts order
  _applyTopChartsOrder();
}

function _applyTabIconMode(mode) {
  document.body.classList.remove("tab-mode-icons", "tab-mode-text");
  if (mode === "icons") document.body.classList.add("tab-mode-icons");
  if (mode === "text")  document.body.classList.add("tab-mode-text");
}

function _applyPagoBtnMode(mode) {
  document.body.classList.remove("pago-btns-icons", "pago-btns-text");
  if (mode === "icons") document.body.classList.add("pago-btns-icons");
  if (mode === "text")  document.body.classList.add("pago-btns-text");
}

function _applyTopChartsOrder() {
  const swapped = localStorage.getItem("top_charts_swapped") === "1";
  const bud     = document.getElementById("bud-chart-card");
  const monthly = document.getElementById("home-chart-card");
  if (!bud || !monthly) return;
  bud.style.order     = swapped ? 1 : 0;
  monthly.style.order = swapped ? 0 : 1;
  const budUp    = document.getElementById("bud-ctrl-up");
  const budDn    = document.getElementById("bud-ctrl-dn");
  const monthUp  = document.getElementById("monthly-ctrl-up");
  const monthDn  = document.getElementById("monthly-ctrl-dn");
  if (budUp)   budUp.disabled   = !swapped;
  if (budDn)   budDn.disabled   =  swapped;
  if (monthUp) monthUp.disabled =  swapped;
  if (monthDn) monthDn.disabled = !swapped;
}

function _swapTopCharts() {
  const swapped = localStorage.getItem("top_charts_swapped") === "1";
  localStorage.setItem("top_charts_swapped", swapped ? "0" : "1");
  _applyTopChartsOrder();
}

const _CHART_MODE_CYCLE  = ["normal", "compact", "hidden"];
const _CHART_MODE_LABELS = { normal: "▾", compact: "▸", hidden: "▴" };
const _CHART_MODE_TITLES = { normal: "Compactar gráfico", compact: "Ocultar gráfico", hidden: "Mostrar gráfico" };

const _BUD_MODE_CYCLE  = ["normal", "compact", "hidden"];
const _BUD_MODE_LABELS = { normal: "▾", compact: "▸", hidden: "▴" };
const _BUD_MODE_TITLES = { normal: "Compactar gráfico", compact: "Ocultar gráfico", hidden: "Mostrar gráfico" };

function _applyChartMode(mode) {
  const card = document.getElementById("home-chart-card");
  const btn  = document.getElementById("home-chart-toggle");
  if (!card) return;
  card.classList.remove("chart-card--compact", "chart-card--hidden");
  if (mode === "compact") card.classList.add("chart-card--compact");
  if (mode === "hidden")  card.classList.add("chart-card--hidden");
  if (btn) {
    btn.textContent = _CHART_MODE_LABELS[mode] || "▾";
    btn.title       = _CHART_MODE_TITLES[mode] || "";
  }
}

function toggleChartMode() {
  const current = getUiPref("chart_home_mode");
  const idx     = _CHART_MODE_CYCLE.indexOf(current);
  const next    = _CHART_MODE_CYCLE[(idx + 1) % _CHART_MODE_CYCLE.length];
  const stored  = JSON.parse(localStorage.getItem("ui_prefs") || "{}");
  stored.chart_home_mode = next;
  localStorage.setItem("ui_prefs", JSON.stringify(stored));
  _applyChartMode(next);
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
    <button class="btn btn-sm" onclick="document.getElementById('toast').classList.remove('show')">❌ Cancelar</button>`;
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

function showLearnPrompt(keyword, categoria, onConfirm) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span class="toast-msg">¿Agregar keyword a "<strong>${escHtml(categoria)}</strong>"?</span>
    <input id="t-inp" type="text" value="${escHtml(keyword)}" style="max-width:180px">
    <button class="btn btn-sm btn-primary" id="t-ok">Agregar</button>
    <button class="btn btn-sm" onclick="document.getElementById('toast').classList.remove('show')">No</button>`;
  el.className = "toast toast-info show";
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 12000);
  const inp = document.getElementById("t-inp");
  const ok  = () => { const v = inp.value.trim(); el.classList.remove("show"); if (v) onConfirm(v); };
  document.getElementById("t-ok").onclick = ok;
  inp.addEventListener("keydown", e => { if (e.key === "Enter") ok(); if (e.key === "Escape") el.classList.remove("show"); });
  setTimeout(() => { inp.focus(); inp.select(); }, 30);
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
    if (tab.dataset.tab === "graficos")    { loadCharts(); loadBudgetChart(); _monthlyChart?.resize(); }
    if (tab.dataset.tab === "cuotas")      { loadCuotas(); loadPagos(); }
    if (tab.dataset.tab === "presupuesto") { loadTcConfig(); loadPresupuesto(); loadPresupuestoUsuario(); }
    if (tab.dataset.tab === "config")      { _restoreCfgSections(); renderUsuarios(); renderUserRules(); loadCuentas(); loadImportaciones(); renderUiSettings(); renderPwaShortcuts(); loadCategoriasManaged(); loadDedupConfig(); loadPeriodoConfig(); loadVencMatchConfig(); loadCategorizacionConfig(); loadEspecialesConfig(); loadIconosConfig(); }
  });
});

// ── Gastos sub-tabs ────────────────────────────────────────────────────────────
document.querySelectorAll(".gtab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".gtab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".gtab-content").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`gtab-${tab.dataset.gtab}`).classList.add("active");
    if (tab.dataset.gtab === "transferencias") loadTransferWorkspace();
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
    if (tab.dataset.cfgtab === "log") loadLogs();
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
  localStorage.setItem(`cfg-section-${id}`, open ? "0" : "1");
}

function _restoreCfgSections() {
  ["pers-list", "pers-rules",
   "proc-categorizacion", "proc-importacion", "proc-periodo", "proc-vencimientos"].forEach(id => {
    if (localStorage.getItem(`cfg-section-${id}`) !== "1") return;
    const body  = document.getElementById(`cfg-body-${id}`);
    const arrow = document.getElementById(`cfg-arr-${id}`);
    if (body)  body.style.display = "";
    if (arrow) arrow.textContent  = "−";
  });
}

// ── Resumen home (saldos + tarjetas) colapsable ───────────────────────────────
function _setHomeSummary(collapsed) {
  const body = document.getElementById("home-summary-body");
  const btn  = document.getElementById("home-summary-toggle");
  if (!body || !btn) return;
  body.style.display = collapsed ? "none" : "";
  btn.setAttribute("aria-expanded", String(!collapsed));
  const arr = btn.querySelector(".hs-arrow");
  if (arr) arr.textContent = collapsed ? "▸" : "▾";
}
function toggleHomeSummary() {
  const collapsed = document.getElementById("home-summary-body")?.style.display !== "none";
  _setHomeSummary(collapsed);
  localStorage.setItem("home-summary-collapsed", collapsed ? "1" : "0");
}
_setHomeSummary(localStorage.getItem("home-summary-collapsed") === "1");

// ── UI settings (Interfaz tab) ────────────────────────────────────────────────
// ── Dedup config (Config → Importación) ──────────────────────────────────────

async function loadDedupConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/dedup`);
    if (!r.ok) return;
    const d = await r.json();
    const pEl = document.getElementById("dedup-prefijos");
    const eEl = document.getElementById("dedup-exactos");
    const cEl = document.getElementById("tarjeta-consumo-patrones");
    if (pEl) pEl.value = (d.dedup_prefijos || []).join("\n");
    if (eEl) eEl.value = (d.dedup_exactos  || []).join("\n");
    if (cEl) cEl.value = (d.tarjeta_consumo_pago_patrones || []).join("\n");
  } catch(e) { console.warn("loadDedupConfig:", e); }
}

async function saveDedupConfig() {
  const pEl = document.getElementById("dedup-prefijos");
  const eEl = document.getElementById("dedup-exactos");
  const cEl = document.getElementById("tarjeta-consumo-patrones");
  const msgEl = document.getElementById("dedup-save-msg");
  const prefijos = (pEl?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const exactos  = (eEl?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const patrones = (cEl?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  try {
    const r = await fetch(`${BASE}/api/config/dedup`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dedup_prefijos: prefijos, dedup_exactos: exactos,
                             tarjeta_consumo_pago_patrones: patrones }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.textContent = "Guardado ✓"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
    }
  } catch(e) { console.warn("saveDedupConfig:", e); }
}

// ── Período / Ciclo de cobro ───────────────────────────────────────────────
function renderPeriodoState() {
  const on = document.getElementById("periodo-activo")?.checked;
  const body = document.getElementById("periodo-body");
  if (body) {
    body.style.opacity = on ? "1" : ".5";
    body.style.pointerEvents = on ? "auto" : "none";
  }
  renderPeriodoPreview();
}

function renderPeriodoPreview() {
  const el = document.getElementById("periodo-preview");
  if (!el) return;
  const n = parseInt(document.getElementById("periodo-delta")?.value, 10);
  if (isNaN(n) || n < 0 || n > 28) { el.textContent = ""; return; }
  if (n === 0) {
    el.textContent = "Delta 0: equivale al mes calendario (sin desfasaje).";
    return;
  }
  el.textContent = `Los últimos ${n} día${n === 1 ? "" : "s"} de cada mes se imputan al período del mes siguiente, `
    + `de modo que el sueldo que cobrás a fin de mes (y los gastos posteriores) caen en el mes que financian.`;
}

async function loadPeriodoConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/periodo`);
    if (!r.ok) return;
    const d = await r.json();
    const act = document.getElementById("periodo-activo");
    const delta = document.getElementById("periodo-delta");
    const ovr = document.getElementById("periodo-overrides");
    if (act) act.checked = !!d.periodo_activo;
    if (delta) delta.value = (d.periodo_delta_dias ?? 2);
    if (ovr) {
      const lines = Object.entries(d.periodo_overrides || {})
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([k, v]) => `${k} = ${v}`);
      ovr.value = lines.join("\n");
    }
    renderPeriodoState();
  } catch (e) { console.warn("loadPeriodoConfig:", e); }
}

async function savePeriodoConfig() {
  const msgEl = document.getElementById("periodo-save-msg");
  const activo = !!document.getElementById("periodo-activo")?.checked;
  const deltaRaw = parseInt(document.getElementById("periodo-delta")?.value, 10);
  const delta = isNaN(deltaRaw) ? 2 : Math.max(0, Math.min(28, deltaRaw));
  const raw = (document.getElementById("periodo-overrides")?.value || "").split("\n");
  const overrides = {};
  for (const line of raw) {
    const t = line.trim();
    if (!t) continue;
    const m = t.match(/^(\d{4}-\d{2})\s*=\s*(\d{1,2})$/);
    if (!m) {
      if (msgEl) { msgEl.style.color = "#dc2626"; msgEl.textContent = `Línea inválida: "${t}"`; }
      return;
    }
    overrides[m[1]] = Math.max(0, Math.min(28, parseInt(m[2], 10)));
  }
  try {
    const r = await fetch(`${BASE}/api/config/periodo`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ periodo_activo: activo, periodo_delta_dias: delta, periodo_overrides: overrides }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.style.color = "#16a34a"; msgEl.textContent = "Guardado ✓ — recargá para ver los gráficos"; setTimeout(() => { msgEl.textContent = ""; }, 4000); }
      // Refrescar series y filtros con la nueva agrupación.
      if (typeof loadMonthlyChart === "function") loadMonthlyChart();
    } else if (msgEl) {
      msgEl.style.color = "#dc2626"; msgEl.textContent = "Error al guardar";
    }
  } catch (e) { console.warn("savePeriodoConfig:", e); }
}

// ── Vencimientos / Confirmación de pago ────────────────────────────────────
function renderVencMatchState() {
  const on = document.getElementById("venc-match-activo")?.checked;
  const body = document.getElementById("venc-match-body");
  if (body) {
    body.style.opacity = on ? "1" : ".5";
    body.style.pointerEvents = on ? "auto" : "none";
  }
}

async function loadVencMatchConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/venc-match`);
    const d = await r.json();
    const act = document.getElementById("venc-match-activo");
    const dias = document.getElementById("venc-match-dias");
    const ta  = document.getElementById("venc-match-tol-ars");
    const tu  = document.getElementById("venc-match-tol-usd");
    const cat = document.getElementById("venc-match-categorias");
    if (act)  act.checked = !!d.venc_pago_match_activo;
    if (dias) dias.value  = (d.venc_pago_match_dias ?? 8);
    if (ta)   ta.value    = (d.venc_pago_match_tol_ars ?? 5000);
    if (tu)   tu.value    = (d.venc_pago_match_tol_usd ?? 1);
    if (cat)  cat.value   = (d.venc_pago_match_categorias ?? ["Pago de Tarjeta"]).join("\n");
    renderVencMatchState();
  } catch (e) { console.warn("loadVencMatchConfig:", e); }
}

async function saveVencMatchConfig() {
  const msgEl  = document.getElementById("venc-match-save-msg");
  const activo = !!document.getElementById("venc-match-activo")?.checked;
  const diasRaw = parseInt(document.getElementById("venc-match-dias")?.value, 10);
  const dias    = isNaN(diasRaw) ? 8 : Math.max(0, Math.min(60, diasRaw));
  const tolArs  = Math.max(0, parseFloat(document.getElementById("venc-match-tol-ars")?.value) || 0);
  const tolUsd  = Math.max(0, parseFloat(document.getElementById("venc-match-tol-usd")?.value) || 0);
  const cats    = (document.getElementById("venc-match-categorias")?.value || "")
                    .split("\n").map(s => s.trim()).filter(Boolean);
  try {
    const r = await fetch(`${BASE}/api/config/venc-match`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        venc_pago_match_activo:  activo,
        venc_pago_match_dias:    dias,
        venc_pago_match_tol_ars: tolArs,
        venc_pago_match_tol_usd: tolUsd,
        venc_pago_match_categorias: cats,
      }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.style.color = "#16a34a"; msgEl.textContent = "Guardado ✓"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
      loadVencimientos();   // refrescar el widget con los nuevos badges
    } else if (msgEl) {
      msgEl.style.color = "#dc2626"; msgEl.textContent = "Error al guardar";
    }
  } catch (e) { console.warn("saveVencMatchConfig:", e); }
}

// ── Categorización por IA (prompt + categorías) ──────────────────────────────
async function loadCategorizacionConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/categorizacion`);
    if (!r.ok) return;
    const d = await r.json();
    const cEl = document.getElementById("cat-categorias");
    const pEl = document.getElementById("cat-prompt");
    const dEl = document.getElementById("cat-prompt-default");
    if (cEl) cEl.value = (d.categorizer_categorias || []).join("\n");
    if (pEl) pEl.value = d.categorizer_prompt || "";
    if (dEl && d.default_prompt) dEl.textContent = "Default: " + d.default_prompt;
  } catch (e) { console.warn("loadCategorizacionConfig:", e); }
}

async function saveCategorizacionConfig() {
  const msgEl  = document.getElementById("cat-save-msg");
  const cats   = (document.getElementById("cat-categorias")?.value || "")
                   .split("\n").map(s => s.trim()).filter(Boolean);
  const prompt = (document.getElementById("cat-prompt")?.value || "").trim();
  try {
    const r = await fetch(`${BASE}/api/config/categorizacion`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ categorizer_categorias: cats, categorizer_prompt: prompt }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.style.color = "#16a34a"; msgEl.textContent = "Guardado ✓"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
    } else {
      const e = await r.json().catch(() => ({}));
      if (msgEl) { msgEl.style.color = "#dc2626"; msgEl.textContent = e.detail || "Error al guardar"; }
    }
  } catch (e) { console.warn("saveCategorizacionConfig:", e); }
}

// ── Categorías especiales fijas ──────────────────────────────────────────────
async function loadEspecialesConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/especiales`);
    if (!r.ok) return;
    const d = await r.json();
    const el = document.getElementById("especiales-builtin");
    if (el) el.value = (d.categorias_especiales_builtin || []).join("\n");
  } catch (e) { console.warn("loadEspecialesConfig:", e); }
}

async function saveEspecialesConfig() {
  const msgEl = document.getElementById("especiales-save-msg");
  const names = (document.getElementById("especiales-builtin")?.value || "")
                  .split("\n").map(s => s.trim()).filter(Boolean);
  try {
    const r = await fetch(`${BASE}/api/config/especiales`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ categorias_especiales_builtin: names }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.style.color = "#16a34a"; msgEl.textContent = "Guardado ✓"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
      refreshAfterDataChange();   // los totales/gráficos cambian al excluir distinto
    }
  } catch (e) { console.warn("saveEspecialesConfig:", e); }
}

// ── Íconos PWA por fuente ────────────────────────────────────────────────────
let _iconStyles = {};

async function loadIconosConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/iconos`);
    if (!r.ok) return;
    const d = await r.json();
    // Mostrar siempre las fuentes default + las overrides guardadas.
    _iconStyles = { ...(d.defaults || {}), ...(d.fuente_icon_styles || {}) };
    _renderIconRows();
  } catch (e) { console.warn("loadIconosConfig:", e); }
}

function _renderIconRows() {
  const wrap = document.getElementById("iconos-list");
  if (!wrap) return;
  wrap.innerHTML = "";
  Object.keys(_iconStyles).sort().forEach(f => _appendIconRow(f, _iconStyles[f]));
}

function _appendIconRow(fuente, st) {
  const wrap = document.getElementById("iconos-list");
  if (!wrap) return;
  st = st || {};
  const lines = st.lines || [];
  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-bottom:.4rem;flex-wrap:wrap";

  const fIn = document.createElement("input");
  fIn.type = "text"; fIn.placeholder = "fuente"; fIn.value = fuente || "";
  fIn.className = "icon-fuente"; fIn.style.cssText = "width:130px;font-family:monospace;font-size:.85em";

  const bgIn = document.createElement("input");
  bgIn.type = "color"; bgIn.value = st.bg || "#16213e"; bgIn.className = "icon-bg"; bgIn.title = "Fondo";

  const fgIn = document.createElement("input");
  fgIn.type = "color"; fgIn.value = st.fg || "#ffffff"; fgIn.className = "icon-fg"; fgIn.title = "Texto";

  const l1 = document.createElement("input");
  l1.type = "text"; l1.placeholder = "Línea 1"; l1.value = lines[0] || ""; l1.className = "icon-l1"; l1.style.cssText = "width:90px";

  const l2 = document.createElement("input");
  l2.type = "text"; l2.placeholder = "Línea 2"; l2.value = lines[1] || ""; l2.className = "icon-l2"; l2.style.cssText = "width:90px";

  const del = document.createElement("button");
  del.className = "btn btn-sm"; del.textContent = "✕"; del.title = "Quitar";
  del.onclick = () => row.remove();

  row.append(fIn, bgIn, fgIn, l1, l2, del);
  wrap.appendChild(row);
}

function addIconRow() { _appendIconRow("", {}); }

async function saveIconosConfig() {
  const msgEl = document.getElementById("iconos-save-msg");
  const styles = {};
  document.querySelectorAll("#iconos-list > div").forEach(row => {
    const fuente = (row.querySelector(".icon-fuente")?.value || "").trim();
    if (!fuente) return;
    const lines = [row.querySelector(".icon-l1")?.value, row.querySelector(".icon-l2")?.value]
                    .map(s => (s || "").trim()).filter(Boolean);
    styles[fuente] = {
      bg:    row.querySelector(".icon-bg")?.value || "",
      fg:    row.querySelector(".icon-fg")?.value || "",
      lines: lines,
    };
  });
  try {
    const r = await fetch(`${BASE}/api/config/iconos`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fuente_icon_styles: styles }),
    });
    if (r.ok) {
      if (msgEl) { msgEl.style.color = "#16a34a"; msgEl.textContent = "Guardado ✓"; setTimeout(() => { msgEl.textContent = ""; }, 2500); }
    }
  } catch (e) { console.warn("saveIconosConfig:", e); }
}

function renderUiSettings() {
  // Colors
  const storedC = JSON.parse(localStorage.getItem("ui_colors") || "{}");
  const c = { ...UI_COLOR_DEFAULTS, ...storedC };
  ["ars","usd","rg","tog","accent","cat_parent","cat_child",
   "egreso","ingreso","presup","real","venc_urg","venc_pronto"].forEach(k => {
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
  setVal("ui-chart-home-mode",    p.chart_home_mode);
  setVal("ui-tab-icon-mode",      p.tab_icon_mode);
  setVal("ui-pago-btn-mode",      p.pago_btn_mode);
  setVal("ui-widget-refresh",     p.widget_refresh_mins);
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
  return { ars: get("ars"), usd: get("usd"), rg: get("rg"), tog: get("tog"), accent: get("accent"),
           cat_parent: get("cat_parent"), cat_child: get("cat_child"),
           egreso: get("egreso"), ingreso: get("ingreso"), presup: get("presup"), real: get("real"),
           venc_urg: get("venc_urg"), venc_pronto: get("venc_pronto") };
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
    chart_home_mode:    sel("ui-chart-home-mode",    UI_PREF_DEFAULTS.chart_home_mode),
    tab_icon_mode:         sel("ui-tab-icon-mode",      UI_PREF_DEFAULTS.tab_icon_mode),
    pago_btn_mode:         sel("ui-pago-btn-mode",      UI_PREF_DEFAULTS.pago_btn_mode),
    widget_refresh_mins:   sel("ui-widget-refresh",     UI_PREF_DEFAULTS.widget_refresh_mins),
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
  _applyChartMode(p.chart_home_mode);
  loadVencimientos();   // refresh widget with new thresholds & visibility prefs
  loadMonthlyChart();   // re-render con los colores nuevos (egreso/ingreso)
  loadBudgetChart();    // ídem (presupuesto/real)
  _restartBgRefresh();  // aplica el nuevo intervalo de refresco de widgets
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

// ── Web Push (notificaciones) ────────────────────────────────────────────────
const _pushSupported = () =>
  "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function _urlB64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

async function refreshPushState() {
  const val = document.getElementById("push-status-val");
  if (!val) return;
  if (!_pushSupported()) { val.textContent = "no soportado en este navegador"; return; }
  if (Notification.permission === "denied") { val.textContent = "permiso bloqueado por el navegador"; return; }
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    val.textContent = sub ? "activadas en este dispositivo ✓" : "desactivadas";
  } catch (_) { val.textContent = "desactivadas"; }
}

async function enablePush() {
  if (!_pushSupported()) return showToast("Este navegador no soporta notificaciones", "err");
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return showToast("Permiso de notificaciones denegado", "err");
    const reg = await navigator.serviceWorker.ready;
    const { public_key } = await (await fetch(`${BASE}/api/push/public-key`)).json();
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: _urlB64ToUint8Array(public_key),
    });
    const r = await fetch(`${BASE}/api/push/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    if (!r.ok) throw new Error("subscribe falló");
    showToast("Notificaciones activadas");
  } catch (e) {
    console.warn("enablePush:", e);
    const detail = e && (e.message || e.name) ? `${e.name || ""}: ${e.message || e}` : String(e);
    showToast("No se pudieron activar: " + detail, "err", 7000);
  }
  refreshPushState();
}

async function disablePush() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await fetch(`${BASE}/api/push/unsubscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
      await sub.unsubscribe();
    }
    showToast("Notificaciones desactivadas");
  } catch (e) { console.warn("disablePush:", e); }
  refreshPushState();
}

async function testPush() {
  try {
    const r = await fetch(`${BASE}/api/push/test`, { method: "POST" });
    showToast(r.ok ? "Push de prueba enviado" : "No hay suscripción activa en este dispositivo",
              r.ok ? "ok" : "err");
  } catch (_) { showToast("No se pudo enviar el push de prueba", "err"); }
}

async function resetPush() {
  if (!confirm("Borra TODAS tus suscripciones (todos los dispositivos) y reactiva ESTE. En los demás vas a tener que tocar Activar de nuevo. ¿Seguir?"))
    return;
  try {
    // Sacar la suscripción local del navegador antes de limpiar el server.
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && await reg.pushManager.getSubscription();
    if (sub) await sub.unsubscribe();
    await fetch(`${BASE}/api/push/clear`, { method: "POST" });
    showToast("Suscripciones reseteadas, reactivando este dispositivo…");
    await enablePush();   // crea UNA limpia para este device
  } catch (e) {
    console.warn("resetPush:", e);
    showToast("No se pudo resetear", "err");
  }
  refreshPushState();
}

document.getElementById("btn-push-enable")?.addEventListener("click", enablePush);
document.getElementById("btn-push-disable")?.addEventListener("click", disablePush);
document.getElementById("btn-push-test")?.addEventListener("click", testPush);
document.getElementById("btn-push-reset")?.addEventListener("click", resetPush);

// ── Config: aviso de vencimientos de tarjeta ─────────────────────────────────
async function loadVencNotifConfig() {
  try {
    const r = await fetch(`${BASE}/api/config/venc-notif`);
    if (!r.ok) return;
    const c = await r.json();
    const a = document.getElementById("venc-notif-activo");
    const d = document.getElementById("venc-notif-dias");
    const h = document.getElementById("venc-notif-hora");
    if (a) a.checked = !!c.venc_notif_activo;
    if (d) d.value = (c.venc_notif_dias_antes || []).join(",");
    if (h) h.value = (c.venc_notif_hora ?? 9);
  } catch (_) {}
}

async function saveVencNotifConfig() {
  const dias = (document.getElementById("venc-notif-dias")?.value || "")
    .split(",").map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n));
  const body = {
    venc_notif_activo:     document.getElementById("venc-notif-activo")?.checked || false,
    venc_notif_dias_antes: dias,
    venc_notif_hora:       parseInt(document.getElementById("venc-notif-hora")?.value, 10),
  };
  try {
    const r = await fetch(`${BASE}/api/config/venc-notif`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    showToast(r.ok ? "Aviso de vencimientos guardado" : "Error al guardar", r.ok ? "ok" : "err");
    if (r.ok) loadVencNotifConfig();
  } catch (_) { showToast("Error al guardar", "err"); }
}

async function testVencNotif() {
  try {
    const r = await fetch(`${BASE}/api/config/venc-notif/test`, { method: "POST" });
    if (!r.ok) return showToast("No se pudo probar", "err");
    const { sent } = await r.json();
    showToast(sent > 0
      ? `Enviados ${sent} aviso(s) de prueba`
      : "No hay tarjetas impagas ni pagos pendientes próximos (o no hay suscripción activa)",
      sent > 0 ? "ok" : "err", 6000);
  } catch (_) { showToast("No se pudo probar", "err"); }
}

document.getElementById("btn-save-venc-notif")?.addEventListener("click", saveVencNotifConfig);
document.getElementById("btn-test-venc-notif")?.addEventListener("click", testVencNotif);
document.querySelector('.cfg-tab[data-cfgtab="ui"]')?.addEventListener("click", () => {
  refreshPushState();
  loadVencNotifConfig();
});

// ── Pagos / vencimientos manuales (b2) ───────────────────────────────────────
let _editingPagoId = null;

function _fmtPagoMonto(p) {
  if (p.monto == null || p.monto === "") return "";
  const sym = p.moneda === "USD" ? "US$" : "$";
  return `${sym} ${Number(p.monto).toLocaleString("es-AR")}`;
}

function _pagoForm() {
  return {
    desc:   document.getElementById("pago-desc"),
    monto:  document.getElementById("pago-monto"),
    moneda: document.getElementById("pago-moneda"),
    fecha:  document.getElementById("pago-fecha"),
    recur:  document.getElementById("pago-recur"),
    fin:    document.getElementById("pago-fin"),
    cat:    document.getElementById("pago-cat"),
  };
}

function resetPagoForm() {
  _editingPagoId = null;
  const f = _pagoForm();
  f.desc.value = ""; f.monto.value = ""; f.fecha.value = ""; f.fin.value = "";
  f.recur.value = "unico"; f.moneda.value = "ARS"; f.cat.value = "";
  document.getElementById("btn-add-pago").textContent = "➕ Agregar";
  document.getElementById("btn-cancel-pago").style.display = "none";
}

function editPago(p) {
  _editingPagoId = p.id;
  const f = _pagoForm();
  f.desc.value   = p.descripcion || "";
  f.monto.value  = p.monto != null ? p.monto : "";
  f.moneda.value = p.moneda || "ARS";
  f.fecha.value  = String(p.fecha_vencimiento || "").slice(0, 10);
  f.recur.value  = p.recurrencia === "mensual" ? "mensual" : "unico";
  f.fin.value    = String(p.fecha_fin || "").slice(0, 10);
  f.cat.value    = p.categoria || "";
  document.getElementById("btn-add-pago").textContent = "💾 Guardar";
  document.getElementById("btn-cancel-pago").style.display = "";
  f.desc.focus();
}

async function loadPagos() {
  const tb = document.getElementById("pagos-tbody");
  if (!tb) return;
  let pagos = [];
  try { pagos = (await (await fetch(`${BASE}/api/pagos`)).json()).pagos || []; }
  catch (_) {}
  tb.replaceChildren();
  if (!pagos.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7; td.className = "empty"; td.textContent = "Sin pagos cargados.";
    tr.appendChild(td); tb.appendChild(tr); return;
  }
  const mkAction = (icon, label, cls, fn, title) => {
    const b = document.createElement("button");
    b.className = "btn pago-action" + (cls ? " " + cls : "");
    b.title = title || label; b.onclick = fn;
    const si = document.createElement("span"); si.className = "pa-icon"; si.textContent = icon;
    const st = document.createElement("span"); st.className = "pa-text"; st.textContent = " " + label;
    b.appendChild(si); b.appendChild(st);
    return b;
  };
  for (const p of pagos) {
    const matches   = p.matches || [];
    const detectado = p.estado === "pendiente" && matches.length > 0;

    const tr = document.createElement("tr");
    if (p.estado === "pagado") tr.style.opacity = ".5";
    let tipo = p.recurrencia === "mensual" ? "Mensual" : "Único";
    if (p.recurrencia === "mensual" && p.fecha_fin)
      tipo += ` (hasta ${String(p.fecha_fin).slice(0, 10)})`;

    const textCells = [
      String(p.fecha_vencimiento || "").slice(0, 10),
      p.descripcion,
      _fmtPagoMonto(p),
      tipo,
      p.categoria || "",
    ];
    for (const txt of textCells) {
      const td = document.createElement("td"); td.textContent = txt; tr.appendChild(td);
    }

    // Estado cell
    const tdEstado = document.createElement("td");
    if (detectado) {
      const chip = document.createElement("span");
      chip.className = "estado-detectado";
      chip.textContent = "🔍 Detectado" + (matches.length > 1 ? ` (${matches.length})` : "");
      tdEstado.appendChild(chip);
    } else {
      tdEstado.textContent = p.estado === "pagado" ? "Pagado" : "Pendiente";
    }
    tr.appendChild(tdEstado);

    // Actions cell
    const tdA = document.createElement("td");
    tdA.style.cssText = "display:flex;align-items:center;gap:.3rem;white-space:nowrap";

    // Build the match detail row before wiring the toggle button
    let trDet = null;
    if (detectado) {
      trDet = document.createElement("tr");
      trDet.className = "pago-match-row";
      trDet.style.display = "none";
      const tdDet = document.createElement("td");
      tdDet.colSpan = 7;

      const panel = document.createElement("div");
      panel.className = "pago-match-panel";

      const title = document.createElement("div");
      title.className = "pago-match-title";
      title.textContent = matches.length === 1
        ? "Posible pago detectado en tus movimientos:"
        : `${matches.length} posibles pagos detectados:`;
      panel.appendChild(title);

      for (const m of matches) {
        const item = document.createElement("div");
        item.className = "pago-match-item";

        const info = document.createElement("span");
        info.className = "pago-match-info";
        const sym = m.moneda === "USD" ? "US$" : "$";
        const cat = m.categoria ? `  ·  ${m.categoria}` : "";
        info.textContent = `${m.fecha}  ·  ${m.descripcion}  ·  ${sym} ${Number(m.monto).toLocaleString("es-AR")}${cat}  [${m.fuente}]`;
        item.appendChild(info);

        const btnConf = document.createElement("button");
        btnConf.className = "btn btn-pagado btn-sm";
        btnConf.style.whiteSpace = "nowrap";
        btnConf.textContent = "✓ Confirmar pagado";
        btnConf.onclick = () => markPagoPaid(p.id);
        item.appendChild(btnConf);

        panel.appendChild(item);
      }

      tdDet.appendChild(panel);
      trDet.appendChild(tdDet);

      // "+" toggle button — first in the actions cell
      const btnVer = mkAction("+", "Ver", "", () => {
        const open = trDet.style.display === "none";
        trDet.style.display = open ? "" : "none";
      }, "Ver movimiento detectado");
      tdA.appendChild(btnVer);
    }

    if (p.estado !== "pagado") {
      tdA.appendChild(mkAction("✓", "Pagado", "btn-pagado", () => markPagoPaid(p.id), "Marcar pagado"));
      if (p.recurrencia === "mensual")
        tdA.appendChild(mkAction("■", "Finalizar", "", () => finalizarPago(p.id, p.descripcion), "Finalizar serie"));
      tdA.appendChild(mkAction("✎", "Editar", "", () => editPago(p), "Editar"));
    } else {
      tdA.appendChild(mkAction("↺", "Reabrir", "", () => reabrirPago(p.id), "Reabrir (volver a pendiente)"));
    }
    tdA.appendChild(mkAction("🗑︎", "Borrar", "btn-danger", () => deletePago(p.id, p.descripcion), "Borrar"));
    tr.appendChild(tdA);
    tb.appendChild(tr);
    if (trDet) tb.appendChild(trDet);
  }
}

async function savePago() {
  const f = _pagoForm();
  const desc  = f.desc.value.trim();
  const fecha = f.fecha.value;
  if (!desc || !fecha) return showToast("Completá descripción y fecha", "err");
  const body = {
    descripcion:       desc,
    monto:             f.monto.value || null,
    moneda:            f.moneda.value,
    fecha_vencimiento: fecha,
    recurrencia:       f.recur.value,
    fecha_fin:         (f.recur.value === "mensual" ? f.fin.value : "") || "",
    categoria:         f.cat.value.trim() || "",
  };
  const editing = _editingPagoId != null;
  try {
    const r = await fetch(`${BASE}/api/pagos${editing ? "/" + _editingPagoId : ""}`, {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error();
    showToast(editing ? "Pago actualizado" : "Pago agregado");
    resetPagoForm();
    loadPagos();
  } catch (_) { showToast("Error al guardar el pago", "err"); }
}

async function markPagoPaid(id) {
  try {
    const r = await fetch(`${BASE}/api/pagos/${id}/pagar`, { method: "POST" });
    if (!r.ok) throw new Error();
    const { siguiente } = await r.json();
    showToast(siguiente
      ? `Pagado — próximo: ${siguiente.fecha_vencimiento}`
      : "Marcado como pagado");
    loadPagos();
  } catch (_) { showToast("Error", "err"); }
}

async function reabrirPago(id) {
  try {
    const r = await fetch(`${BASE}/api/pagos/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ estado: "pendiente" }),
    });
    if (!r.ok) throw new Error();
    showToast("Reabierto como pendiente"); loadPagos();
  } catch (_) { showToast("No se pudo reabrir", "err"); }
}

async function finalizarPago(id, desc) {
  if (!confirm(`¿Finalizar la serie de "${desc}"? No se vuelve a generar.`)) return;
  try {
    const r = await fetch(`${BASE}/api/pagos/${id}/finalizar`, { method: "POST" });
    if (!r.ok) throw new Error();
    showToast("Serie finalizada"); loadPagos();
  } catch (_) { showToast("Error", "err"); }
}

async function deletePago(id, desc) {
  if (!confirm(`¿Eliminar "${desc}"?`)) return;
  try {
    const r = await fetch(`${BASE}/api/pagos/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error();
    showToast("Pago eliminado");
    if (_editingPagoId === id) resetPagoForm();
    loadPagos();
  } catch (_) { showToast("Error al eliminar", "err"); }
}

document.getElementById("btn-add-pago")?.addEventListener("click", savePago);
document.getElementById("btn-cancel-pago")?.addEventListener("click", resetPagoForm);
document.getElementById("btn-reload-pagos")?.addEventListener("click", loadPagos);
_setupCatAC(document.getElementById("pago-cat"), "");

document.getElementById("pago-desc")?.addEventListener("blur", async () => {
  const catEl = document.getElementById("pago-cat");
  if (catEl.value.trim()) return;
  const desc = document.getElementById("pago-desc").value.trim();
  if (!desc) return;
  try {
    const res = await fetch(`${BASE}/api/rules/suggest?desc=${encodeURIComponent(desc)}`);
    if (!res.ok) return;
    const { categoria } = await res.json();
    if (categoria) catEl.value = categoria;
  } catch (_) {}
});

// ── User info ─────────────────────────────────────────────────────────────────
fetch(`${BASE}/auth/me`).then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
  if (u.is_admin) {
    const link = document.getElementById("admin-link");
    link.href = `${BASE}/admin`;
    link.style.display = "";
  }
});

// ── Logout: limpiar caché del cliente antes de navegar ────────────────────────
// El logout server-side revoca el token de sesión; acá además limpiamos restos
// del lado cliente (service worker caches + preferencias en localStorage) para
// que al cambiar de usuario no queden datos/UI del usuario anterior visibles.
const _logoutLink = document.getElementById("logout-link");
if (_logoutLink) {
  _logoutLink.addEventListener("click", async (e) => {
    e.preventDefault();
    const dest = _logoutLink.href;  // ya viene con el prefijo de ingress
    try {
      if (window.caches) {
        const keys = await caches.keys();
        await Promise.all(keys.map(k => caches.delete(k)));
      }
      if (navigator.serviceWorker) {
        // Antes de matar el SW (que destruye la suscripción push del navegador),
        // avisar al server para que borre ESTA suscripción. Si no, queda huérfana
        // en la DB del usuario y los próximos avisos se duplican (al re-loguear y
        // re-activar se crea otra con endpoint nuevo). Corre aún logueado.
        try {
          const reg = await navigator.serviceWorker.getRegistration();
          const sub = reg && await reg.pushManager.getSubscription();
          if (sub) {
            await fetch(`${BASE}/api/push/unsubscribe`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ endpoint: sub.endpoint }),
              keepalive: true,
            });
          }
        } catch (_) {}
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map(r => r.unregister()));
      }
      try { localStorage.clear(); } catch (_) {}
    } catch (_) {
      /* best-effort — igual navegamos al logout */
    }
    window.location.href = dest;
  });
}

// ── Monthly overview chart ────────────────────────────────────────────────────
let _monthlyChart = null;

async function loadMonthlyChart() {
  let data;
  try {
    const res = await fetch(`${BASE}/api/gastos/monthly`);
    const payload = await res.json();
    // Backward/forward compatible: el endpoint ahora devuelve {meses, actual}.
    data = Array.isArray(payload) ? payload : (payload.meses || []);
    _periodoActual = (payload && payload.actual) || _periodoActual;
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
  _populateMonthFilter(data.map(d => d.mes));   // dropdown del filtro: TODOS los meses

  // El gráfico muestra solo los últimos N meses (combo, persistido). data viene
  // ordenado de más viejo a más nuevo, así que slice(-N) toma los más recientes.
  const _n    = _monthlyMeses();
  const shown = _n > 0 ? data.slice(-_n) : data;
  const labels   = shown.map(d => _fmtMes(d.mes));
  const egresos  = shown.map(d => d.egresos);
  const ingresos = shown.map(d => d.ingresos);
  const ctx = document.getElementById("monthly-chart").getContext("2d");

  const _cEgr = _cssVar("--color-egreso", "#dc2626");
  const _cIng = _cssVar("--color-ingreso", "#16a34a");

  if (_monthlyChart) {
    _monthlyChart.data.labels = labels;
    _monthlyChart.data.datasets[0].data = egresos;
    _monthlyChart.data.datasets[0].backgroundColor = _cEgr;
    _monthlyChart.data.datasets[0].borderColor     = _cEgr;
    _monthlyChart.data.datasets[1].data = ingresos;
    _monthlyChart.data.datasets[1].backgroundColor = _cIng;
    _monthlyChart.data.datasets[1].borderColor     = _cIng;
    _monthlyChart.update();
    return;
  }
  _monthlyChart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [
      { label:"Egresos",  data:egresos,  backgroundColor:_cEgr, borderColor:_cEgr, borderWidth:1, borderRadius:3 },
      { label:"Ingresos", data:ingresos, backgroundColor:_cIng, borderColor:_cIng, borderWidth:1, borderRadius:3 },
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

// Cuántos meses hacia atrás muestra el gráfico mes a mes (combo, persistido).
function _monthlyMeses() {
  const v = parseInt(localStorage.getItem("monthly_meses") || "12", 10);
  return [3, 6, 12].includes(v) ? v : 12;
}
(function _initMonthlyMesesSel() {
  const sel = document.getElementById("monthly-meses");
  if (!sel) return;
  sel.value = String(_monthlyMeses());
  sel.addEventListener("change", function () {
    localStorage.setItem("monthly_meses", this.value);
    this.blur();
    loadMonthlyChart();
  });
})();
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
function _fmtTs(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("es-AR", {day:"numeric", month:"numeric", year:"numeric", hour:"2-digit", minute:"2-digit"});
}

// Timestamp del log unificado: el backend (app_log.py) guarda "YYYY-MM-DD HH:MM:SS"
// en UTC sin sufijo. Lo interpretamos como UTC y lo mostramos en la TZ del browser,
// manteniendo el mismo formato ordenable (con segundos).
function _fmtLogTs(ts) {
  if (!ts) return "";
  const norm = String(ts).trim().replace(" ", "T");
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(norm);
  const d = new Date(hasTz ? norm : norm + "Z");
  if (isNaN(d.getTime())) return ts;   // formato inesperado → mostrar tal cual
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

let _monthFilterReady = false;
// Período que contiene hoy. Con el ciclo de cobro activo puede diferir del mes
// calendario; lo setea loadMonthlyChart desde /api/gastos/monthly.
let _periodoActual = new Date().toISOString().slice(0, 7);

function _populateMonthFilter(meses) {
  const today = _periodoActual; // período corriente (mes calendario si el ciclo está inactivo)

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

  // Budget chart month selector: use saved pref on first load, else preserve current
  const budSel = document.getElementById("bud-mes");
  if (budSel) {
    const savedBudMes = (_getBudPrefs().mes) || "";
    const currentBud  = budSel.value;
    while (budSel.options.length > 1) budSel.remove(1);
    meses.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m; opt.textContent = _fmtMes(m);
      budSel.appendChild(opt);
    });
    if (_monthFilterReady)                               budSel.value = currentBud;
    else if (savedBudMes && meses.includes(savedBudMes)) budSel.value = savedBudMes;
    else                                                 budSel.value = defaultClosed;
  }

  // Trigger initial loads now that the month filters are set
  if (!_monthFilterReady) {
    _monthFilterReady = true;
    loadGastos();
    _filtersReadyForCharts = true;
    _checkInitialChartLoad();
    loadBudgetChart();
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
let _crossFilterCat  = null;
let _donutDrillCat  = null;  // drill-down visual sin llamada API
let _donutData      = [];    // cache de datos del donut para restaurar al salir

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
function _setDonutDrill(cat) {
  _donutDrillCat = cat;
  const badge = document.getElementById("cross-filter-badge");
  document.getElementById("cross-filter-label").textContent = "↳ " + cat;
  badge.style.display = "";
  _drawDonut(_donutData);   // re-dibuja solo el donut con datos ya cacheados
}

function clearCrossFilter() {
  if (_donutDrillCat) {                             // salir del drill-down visual
    _donutDrillCat = null;
    document.getElementById("cross-filter-badge").style.display = "none";
    _drawDonut(_donutData);
    return;
  }
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
        <label>Modo:
          <select id="cf-forecast-modo" onchange="this.blur();loadForecast()">
            <option value="regresion" selected>Regresión</option><option value="presupuesto">Presupuesto + Histórico</option>
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
  // Cachear los datos top-level (solo cuando no estamos ya en drill-down)
  if (!_donutDrillCat) _donutData = data;

  const drillChildren = _donutDrillCat ? (_catHierarchy[_donutDrillCat] || []) : [];
  const isDrillDown   = drillChildren.length > 0;
  const displayData   = isDrillDown
    ? data.filter(d => drillChildren.includes(d.categoria))
    : data;

  const total = displayData.reduce((s, d) => s + (d.total || 0), 0);
  const _tc = document.getElementById("total-category");
  if (_tc) _tc.textContent = total ? ` — ${_fmtNum2(total)}` : "";
  const top = (displayData.length ? displayData : data).slice(0, 12);
  top.forEach((d, i) => { _categoryColors[d.categoria] = PALETTE[i % PALETTE.length]; });
  _destroyAndCreate("chart-by-category", {
    type: "doughnut",
    data: {
      labels:   top.map(d => d.categoria),
      datasets: [{ data: top.map(d => d.total),
        backgroundColor: top.map(d =>
          !isDrillDown && _crossFilterCat && d.categoria !== _crossFilterCat
            ? "#d1d5db"
            : _categoryColors[d.categoria]),
        borderWidth: 2, borderColor: "#fff" }],
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      onClick: (_, elements) => {
        if (!elements.length) return;
        const cat = top[elements[0].index].categoria;
        if (_catHierarchy[cat]?.length) {
          _setDonutDrill(cat);   // padre → drill-down visual, sin llamada API
        } else {
          _donutDrillCat = null;
          setCrossFilter(cat);   // hoja → cross-filter normal
        }
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
let _catHierarchy = {};   // {parent_nombre: [child_nombre, ...]}
let _catParentOf  = {};   // {child_nombre: parent_nombre}

async function loadHierarchy() {
  try {
    const res = await fetch(`${BASE}/api/categorias/hierarchy`);
    _catHierarchy = res.ok ? await res.json() : {};
    _catParentOf  = {};
    for (const [parent, children] of Object.entries(_catHierarchy)) {
      for (const child of children) _catParentOf[child] = parent;
    }
  } catch { _catHierarchy = {}; _catParentOf = {}; }
}

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
  // Solo mostrar categorías raíz en el chip row; los hijos aparecen en sub-chips
  const _allChildren = new Set(Object.values(_catHierarchy).flat());
  cats.filter(cat => !_allChildren.has(cat)).forEach(cat => {
    const chip = document.createElement("span");
    chip.className = `cat-chip${_selectedCats.has(cat)?" active":""}`;
    chip.textContent = cat;
    chip.title = "Click para filtrar · Doble clic para renombrar";
    chip.onclick = () => toggleCat(cat);
    chip.ondblclick = (e) => { e.stopPropagation(); startRenameCat(chip, cat); };
    container.appendChild(chip);
  });
}

// Ordered category tree (roots first, children indented) for the gastos combo.
// Returns [{name, depth}] using the loaded hierarchy.
function _orderedCatTree() {
  const allChildren = new Set(Object.values(_catHierarchy).flat());
  const roots = _catList.filter(c => !allChildren.has(c))
                        .sort((a, b) => a.localeCompare(b, "es"));
  const out  = [];
  const seen = new Set();
  roots.forEach(r => {
    out.push({ name: r, depth: 0 }); seen.add(r);
    (_catHierarchy[r] || []).slice().sort((a, b) => a.localeCompare(b, "es"))
      .forEach(ch => { out.push({ name: ch, depth: 1 }); seen.add(ch); });
  });
  // Any category not reached via the hierarchy (orphans) appended as roots.
  _catList.forEach(c => { if (!seen.has(c)) { out.push({ name: c, depth: 0 }); seen.add(c); } });
  return out;
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

function _allDescendants(cat) {
  const result = new Set();
  const queue = [...(_catHierarchy[cat] || [])];
  while (queue.length) {
    const c = queue.shift();
    result.add(c);
    (_catHierarchy[c] || []).forEach(x => queue.push(x));
  }
  return result;
}

function _catFilterParam() {
  if (_selectedCats.size === 0) return null;
  const out = new Set(_selectedCats);
  for (const cat of _selectedCats) _allDescendants(cat).forEach(d => out.add(d));
  return [...out].join(",");
}

function _renderSubChips() {
  const row = document.getElementById("cat-subchips");
  if (!row) return;
  // Show sub-chips for: selected parents AND parents of selected children
  const parentsToShow = new Set();
  for (const cat of _selectedCats) {
    if (_catHierarchy[cat]?.length) parentsToShow.add(cat);
    const par = _catParentOf[cat];
    if (par) parentsToShow.add(par);
  }
  if (!parentsToShow.size) { row.style.display = "none"; row.innerHTML = ""; return; }
  const subCats = [];
  for (const par of parentsToShow)
    (_catHierarchy[par] || []).forEach(c => { if (!subCats.includes(c)) subCats.push(c); });
  row.style.display = "";
  row.innerHTML = subCats.map(child => {
    const active = _selectedCats.has(child) ? " active" : "";
    return `<span class="cat-chip cat-sub${active}" data-subchip="${escHtml(child)}"
                  style="font-size:.8rem;border-color:#7dd3fc">${escHtml(child)}</span>`;
  }).join("");
  row.querySelectorAll("[data-subchip]").forEach(chip => {
    chip.addEventListener("click", () => tapSubCat(chip.dataset.subchip));
  });
}

function tapSubCat(childCat) {
  _sinCat = false;
  _selectedCats.clear();
  _selectedCats.add(childCat);
  _syncChipUI();
  _renderSubChips();
  loadGastos();
}

function _syncChipUI() {
  document.querySelectorAll(".cat-chip:not(.cat-todos):not(.cat-sincat):not(.cat-sub)").forEach(c => {
    const direct = _selectedCats.has(c.textContent);
    const hasChild = (_catHierarchy[c.textContent] || []).some(ch => _selectedCats.has(ch));
    c.classList.toggle("active", direct || hasChild);
  });
  document.querySelector(".cat-sincat")?.classList.remove("active");
  document.querySelector(".cat-todos")?.classList.toggle("active", _selectedCats.size === 0);
}

function toggleCat(cat) {
  _sinCat = false;
  if (_selectedCats.has(cat)) {
    if (_selectedCats.size === 1) {
      _selectedCats.clear();              // último activo → volver a Todas
    } else {
      _selectedCats.clear();
      _selectedCats.add(cat);            // colapsar a solo este (exclusive focus)
    }
  } else {
    _selectedCats.add(cat);              // inactivo → ADD (multi-select)
  }
  _syncChipUI();
  _renderSubChips();
  loadGastos();
}

function toggleAllCats() {
  _sinCat = false;
  _selectedCats.clear();
  document.querySelectorAll(".cat-chip").forEach(c => c.classList.remove("active"));
  document.querySelector(".cat-todos")?.classList.add("active");
  const row = document.getElementById("cat-subchips");
  if (row) { row.style.display = "none"; row.innerHTML = ""; }
  loadGastos();
}

loadHierarchy().then(loadCategorias);

// ── Filter toggle ─────────────────────────────────────────────────────────────
// El botón "Filtros" muestra/oculta SOLO los filtros de detalle (fuente, persona,
// mes, etc.). El slicer de Categorías queda siempre visible (vive fuera del panel).
// El estado abierto/cerrado se recuerda en localStorage.
function _setGastosFilters(open) {
  const panel = document.getElementById("filter-panel");
  const btn   = document.getElementById("btn-toggle-filters");
  panel.style.display = open ? "" : "none";
  btn.textContent = open ? "Filtros −" : "Filtros +";
  btn.setAttribute("aria-expanded", String(open));
  // Al cerrar, también ocultar la sub-fila de filtro por importación
  if (!open) {
    const importRow = document.getElementById("import-filter-row");
    const importBtn = document.getElementById("btn-toggle-import-filter");
    if (importRow) importRow.style.display = "none";
    if (importBtn) { importBtn.textContent = "+"; importBtn.setAttribute("aria-expanded", "false"); }
  }
}

document.getElementById("btn-toggle-filters").addEventListener("click", function () {
  const open = document.getElementById("filter-panel").style.display === "none";
  _setGastosFilters(open);
  localStorage.setItem("gastos-filters-open", open ? "1" : "0");
});

// Aplicar el estado recordado al cargar (default: cerrado → aparece al hacer click).
_setGastosFilters(localStorage.getItem("gastos-filters-open") === "1");

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
    p.set("categorias", _catFilterParam());
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

// Refresco unificado tras un cambio de datos amplio (importación, corrida de
// scraper, ABM de categorías, alta/baja de movimientos, aplicar reglas, marcar
// transferencias). Cada load* es un fetch independiente; llamarlos todos juntos
// evita el clásico "me olvidé de refrescar X". loadHierarchy va antes de
// loadCategorias porque este último usa la jerarquía (_catHierarchy).
// OJO: no usar en la edición de UNA celda de la grilla (saveCategoria / fecha /
// usuario): loadGastos re-renderiza la tabla y perdería ediciones en curso de
// otras filas. Para esos casos refrescar solo los gráficos.
function refreshAfterDataChange() {
  loadGastos();
  loadMonthlyChart();
  loadCharts();
  loadBudgetChart();
  loadSaldos();
  loadHierarchy().then(loadCategorias);
  loadImportaciones();
  loadVencimientos?.();
  loadCuentas();
}

async function loadGastos() {
  const res  = await fetch(`${BASE}/api/gastos?${_gastosParams()}`);
  _gastosData = await res.json();
  _renderGastos();
}

function _renderGastos() {
  let gastos = _gastosData;

  // Filter by tipo (ingreso/egreso) client-side
  const tipo = document.getElementById("filter-tipo").value;
  if (tipo === "egreso")  gastos = gastos.filter(g => _isEgreso(g.monto));
  else if (tipo === "ingreso") gastos = gastos.filter(g => !_isEgreso(g.monto));

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

  // Update sort indicators (header on desktop)
  ["fecha","descripcion","monto","usuario","categoria"].forEach(c => {
    const el = document.getElementById(`gsort-${c}`);
    if (el) el.textContent = _gastosSort.col === c ? (_gastosSort.dir > 0 ? "▲" : "▼") : "";
  });
  // Keep the mobile sort bar in sync with current sort state
  const _gsSel = document.getElementById("gastos-sort-sel");
  const _gsDir = document.getElementById("gastos-sort-dir");
  if (_gsSel && _gastosSort.col) _gsSel.value = _gastosSort.col;
  if (_gsDir) _gsDir.textContent = _gastosSort.dir > 0 ? "▲" : "▼";

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
      <td class="col-fecha"><input class="fecha-input" data-id="${g.id}" type="date" value="${g.fecha}"></td>
      <td class="desc-cell" data-id="${g.id}" data-original="${escHtml(g.descripcion)}" data-edited="${escHtml(g.descripcion_editada||"")}">
        <span class="desc-display${g.descripcion_editada?" desc-overridden":""}" title="${g.descripcion_editada?"Original: "+escHtml(g.descripcion):"Click para editar descripción"}">${escHtml(g.descripcion_editada||g.descripcion)}</span>${g.descripcion_editada?'<span class="desc-edit-mark" title="Descripción editada — click para modificar">✏</span>':''}
      </td>
      <td class="monto ${g.moneda==="USD"?"usd":""} ${egreso?"egreso":"ingreso"}">${displayStr}</td>
      <td class="col-moneda">${g.moneda}</td>
      <td class="col-fuente">${_fuenteBadge(g.fuente)}</td>
      <td class="col-persona">
        <select class="usuario-select" onchange="saveUsuario(${g.id},this)">
          <option value="" ${!u?"selected":""}>—</option>
          ${(_usuariosConfig.usuarios||["Titular","Adicional"]).map(usr=>`<option value="${escHtml(usr)}" ${u===usr?"selected":""}>${escHtml(usr)}</option>`).join("")}
        </select>
      </td>
      <td class="col-cat">
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria||"")}"
          title="${g.categoria_fuente?"Fuente: "+g.categoria_fuente:""}"
          placeholder="Categoría"
          autocomplete="off" spellcheck="false" />
      </td>
      <td class="col-act" style="white-space:nowrap">
        <button class="btn btn-sm btn-action" onclick="saveCategoria(${g.id},this)">✓</button>
        <button class="btn btn-sm btn-action" title="Eliminar este gasto" style="opacity:.28" onmouseover="this.style.opacity=1;this.style.color='#b91c1c'" onmouseout="this.style.opacity=.28;this.style.color=''" onclick="deleteGasto(${g.id})">✕</button>
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

    const descCell = tr.querySelector(".desc-cell");
    descCell.onclick = () => _editDescripcion(descCell, g.id);

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
    const q    = (input.value || "").toLowerCase();
    const tree = _orderedCatTree();
    let matches;
    if (!q) {
      matches = tree;
    } else {
      // Coincide si el nombre matchea, O si el nombre del parent matchea: así al
      // tipear el parent (ej. "transporte") aparecen sus subcategorías aunque no
      // recuerdes el nombre exacto. Además se conserva el parent de cualquier hijo
      // mantenido para que el árbol siga legible.
      const keep = new Set();
      tree.forEach(t => {
        const par = _catParentOf[t.name];
        if (t.name.toLowerCase().includes(q) ||
            (par && par.toLowerCase().includes(q))) {
          keep.add(t.name);
        }
      });
      tree.forEach(t => {
        if (t.depth === 1 && keep.has(t.name)) {
          const par = _catParentOf[t.name];
          if (par) keep.add(par);
        }
      });
      matches = tree.filter(t => keep.has(t.name));
    }
    if (!matches.length) return;

    acEl = document.createElement("div");
    acEl.className = "cat-ac";
    acEl.innerHTML = matches.map((t, i) =>
      `<div class="cat-ac-item${t.depth ? " cat-ac-child" : ""}" data-i="${i}" data-val="${escHtml(t.name)}"${
        t.depth ? ' style="padding-left:1.6rem"' : ""
      }>${t.depth ? "└ " : ""}${escHtml(t.name)}</div>`
    ).join("");

    // Float below the input, wide enough to show full names
    const rect = input.getBoundingClientRect();
    acEl.style.top      = (rect.bottom + window.scrollY) + "px";
    acEl.style.left     = (rect.left   + window.scrollX) + "px";
    acEl.style.minWidth = Math.max(rect.width, 220) + "px";
    document.body.appendChild(acEl);
    acIdx = -1;

    // Clic en la scrollbar/borde del dropdown (target === contenedor, no un item):
    // evitar que el input pierda foco, si no el blur lo cierra al arrastrar la barra.
    acEl.addEventListener("mousedown", e => {
      if (e.target === acEl) e.preventDefault();
    });

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

async function _ensureRulesLoaded() {
  if (_rules.length > 0) return;
  const res  = await fetch(`${BASE}/api/rules`);
  const data = await res.json();
  _rules = (data.reglas || []).map(r => ({
    palabras:    Array.isArray(r.palabras) ? r.palabras.map(String) : _patternToWords(r.patron || ""),
    patron:      r.patron || null,
    categoria:   r.categoria || "",
    especial:    !!r.especial,
    solo_egresos: !!r.solo_egresos,
    fuentes:     Array.isArray(r.fuentes) ? r.fuentes : [],
  }));
}

async function _moveKeywordBetweenRules(keyword, fromCat, toCat) {
  const fromRule = _rules.find(r => r.categoria === fromCat);
  if (fromRule) {
    fromRule.palabras = fromRule.palabras.filter(p => p.toLowerCase() !== keyword.toLowerCase());
  }
  let toRule = _rules.find(r => r.categoria === toCat);
  if (!toRule) {
    toRule = {palabras: [], categoria: toCat, especial: false, solo_egresos: false, fuentes: []};
    _rules.push(toRule);
  }
  if (!toRule.palabras.some(p => p.toLowerCase() === keyword.toLowerCase())) {
    toRule.palabras.push(keyword);
  }
  const reglas = _rules
    .filter(r => r.palabras.length > 0 && r.categoria.trim())
    .map(r => ({palabras: r.palabras, categoria: r.categoria, especial: !!r.especial, solo_egresos: r.solo_egresos || null, fuentes: r.fuentes || []}));
  const res = await fetch(`${BASE}/api/rules`, {
    method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({reglas}),
  });
  if (res.ok) {
    showToast(`✓ "${keyword}" movido de "${fromCat}" a "${toCat}"`, "ok", 2500);
    _fetchRules();
  } else {
    showToast("Error al mover keyword", "err", 0);
  }
}

async function saveCategoria(id, btn) {
  const input = document.querySelector(`.cat-input[data-id="${id}"]`);
  const val   = input.value.trim();
  // No crear categorías nuevas desde la grilla: el valor debe estar vacío
  // (limpiar) o coincidir con una categoría existente.
  if (val && !_catList.includes(val)) {
    showToast(`La categoría "${val}" no existe. Elegila de la lista o creala en Config → Categorías.`, "err", 3500);
    input.focus();
    return;
  }
  const res   = await fetch(`${BASE}/api/gastos/${id}/categoria`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({categoria: input.value}),
  });
  if (res.ok) {
    input.classList.remove("dirty"); btn.classList.remove("btn-dirty");
    input.title = input.value.trim() ? "Fuente: manual" : "";
    // Solo gráficos: NO loadGastos (perdería ediciones en curso de otras filas).
    loadMonthlyChart(); loadCharts(); loadBudgetChart();
    const data = await res.json();
    if (data.sugerencia_keyword && data.categoria) {
      const kw      = data.sugerencia_keyword.split(/\s+/).slice(0, 3).join(" ").toLowerCase();
      const kwWords = kw.split(/\s+/);
      await _ensureRulesLoaded();

      // Check if any word in the suggestion matches a keyword in any existing rule
      let conflictKeyword = null, conflictRule = null, alreadyInTarget = false;
      for (const rule of _rules) {
        for (const p of rule.palabras) {
          if (kwWords.includes(p.toLowerCase())) {
            if (rule.categoria === data.categoria) { alreadyInTarget = true; }
            else if (!conflictRule)               { conflictKeyword = p; conflictRule = rule; }
          }
        }
      }

      if (alreadyInTarget) {
        showToast(`keyword ya registrado en "${escHtml(data.categoria)}"`, "ok", 2500);
      } else if (conflictRule) {
        showConfirm(
          `"${conflictKeyword}" ya está en la categoría "${conflictRule.categoria}". ¿Moverlo a "${data.categoria}"?`,
          () => _moveKeywordBetweenRules(conflictKeyword, conflictRule.categoria, data.categoria)
        );
      } else {
        showLearnPrompt(kw, data.categoria, async kw2 => {
          await fetch(`${BASE}/api/rules/learn`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({keyword: kw2, categoria: data.categoria}),
          });
          showToast(`✓ "${kw2}" agregado a ${data.categoria}`, "ok", 2500);
          _fetchRules();
        });
      }
    }
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

function _renderDescCell(cell, original, edited) {
  cell.dataset.edited = edited || "";
  const display  = edited || original;
  const hasEdit  = !!edited;
  cell.innerHTML = `<span class="desc-display${hasEdit?" desc-overridden":""}" title="${hasEdit?"Original: "+escHtml(original):"Click para editar descripción"}">${escHtml(display)}</span>${hasEdit?'<span class="desc-edit-mark" title="Descripción editada — click para modificar">✏</span>':""}`;
  cell.onclick   = () => _editDescripcion(cell, parseInt(cell.dataset.id));
}

function _editDescripcion(cell, gastoId) {
  cell.onclick = null;
  const original = cell.dataset.original;
  const edited   = cell.dataset.edited;
  const current  = edited || original;

  cell.innerHTML = "";

  const inp = document.createElement("input");
  inp.type        = "text";
  inp.className   = "desc-input";
  inp.value       = current;
  inp.placeholder = original;
  inp.title       = "Vaciar y confirmar restaura el texto original";

  const saveBtn   = document.createElement("button");
  saveBtn.className   = "btn btn-sm btn-action";
  saveBtn.textContent = "💾";

  const cancelBtn = document.createElement("button");
  cancelBtn.className   = "btn btn-sm btn-action";
  cancelBtn.textContent = "✕";
  cancelBtn.title       = "Cancelar (sin guardar)";

  cell.appendChild(inp);
  cell.appendChild(saveBtn);
  cell.appendChild(cancelBtn);
  inp.focus();
  inp.select();

  cancelBtn.onclick = e => { e.stopPropagation(); _renderDescCell(cell, original, edited); };
  saveBtn.onclick   = e => { e.stopPropagation(); _saveDescripcion(cell, gastoId, inp.value.trim(), original); };
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); _saveDescripcion(cell, gastoId, inp.value.trim(), original); }
    if (e.key === "Escape") { e.preventDefault(); _renderDescCell(cell, original, edited); }
  });
}

async function _saveDescripcion(cell, gastoId, newValue, original) {
  // Empty or identical to original → clear override (NULL in DB)
  const override = (newValue && newValue !== original) ? newValue : "";
  const res = await fetch(`${BASE}/api/gastos/${gastoId}/descripcion`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({descripcion_editada: override}),
  });
  if (res.ok) {
    _renderDescCell(cell, original, override);
    showToast(override ? "✓ Descripción editada" : "✓ Descripción restaurada al original", "ok", 1800);
  } else {
    showToast("Error al guardar descripción", "err");
    _renderDescCell(cell, original, cell.dataset.edited);
  }
}

["filter-fuente","filter-usuario","filter-mes","filter-moneda","filter-import"].forEach(id =>
  document.getElementById(id).addEventListener("change", function() { this.blur(); loadGastos(); }));
document.getElementById("filter-tipo").addEventListener("change", function() { this.blur(); _renderGastos(); });
document.getElementById("chk-excluir-especiales").addEventListener("change", loadGastos);
document.getElementById("chk-excluir-especiales-graf").addEventListener("change", loadCharts);
document.getElementById("btn-load").addEventListener("click", loadGastos);
// Export vive en Config → Datos: baja SIEMPRE todos los gastos (sin filtros).
document.getElementById("btn-export").addEventListener("click", () =>
  window.open(`${BASE}/api/gastos/export`, "_blank"));

// Mobile sort bar (the thead is hidden in card mode, so sorting lives here)
document.getElementById("gastos-sort-sel")?.addEventListener("change", function () {
  _gastosSort.col = this.value;
  _gastosSort.dir = this.value === "monto" ? -1 : 1;   // amounts default to descending
  _renderGastos();
});
document.getElementById("gastos-sort-dir")?.addEventListener("click", () => {
  if (!_gastosSort.col) _gastosSort.col = document.getElementById("gastos-sort-sel").value;
  _gastosSort.dir *= -1;
  _renderGastos();
});

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
    refreshAfterDataChange();
  } else {
    showToast("Error al guardar.", "err");
  }
});

// ── Transfer workspace ─────────────────────────────────────────────────────────
let _twData      = null;
let _twSelA      = null;          // selected egreso (full object), or null
let _twQueue     = [];            // [{out: {...}, in: {...}}]
let _twQueuedIds = new Set();     // IDs already in the queue
let _twSortField = 'monto';
let _twSortDir   = 'desc';

function _twSortItems(items) {
  return [...items].sort((a, b) => {
    let va, vb;
    if (_twSortField === 'monto') {
      va = Math.abs(parseFloat(a.monto));
      vb = Math.abs(parseFloat(b.monto));
    } else {
      va = (a[_twSortField] || '').toLowerCase();
      vb = (b[_twSortField] || '').toLowerCase();
    }
    if (va < vb) return _twSortDir === 'asc' ? -1 : 1;
    if (va > vb) return _twSortDir === 'asc' ?  1 : -1;
    return 0;
  });
}

function _twUpdateSortIndicators() {
  const labels = { fecha: 'Fecha', descripcion: 'Descripción', monto: 'Monto' };
  document.querySelectorAll('.tw-sh[data-twsort]').forEach(el => {
    const field    = el.dataset.twsort;
    const isActive = field === _twSortField;
    el.classList.toggle('active', isActive);
    el.textContent = labels[field] + (isActive ? (' ' + (_twSortDir === 'asc' ? '▲' : '▼')) : '');
  });
}

async function loadTransferWorkspace() {
  const res = await fetch(`${BASE}/api/gastos/transfer-workspace`);
  if (!res.ok) { showToast("Error al cargar workspace", "err"); return; }
  _twData = await res.json();
  _twSelA = null;
  _twQueue = [];
  _twQueuedIds = new Set();
  _twCardQueue = [];
  _twCardQueuedIds = new Set();
  document.getElementById("tw-selection-bar").style.display = "none";
  renderTwCardSuggestions();
  renderTwSuggestions();
  renderTwCandidates();
  renderTwQueue();
  renderTwExisting();
  renderTwIgnored();
}

// Card payment queue (separate from transfer queue — different category)
let _twCardQueue  = [];
let _twCardQueuedIds = new Set();

function _twFuenteLabel(f) {
  return _cuentaShortName(f);
}

function _twSugPairSide(g, amtSign, amtCls) {
  const amt = _fmtNum2(Math.abs(parseFloat(g.monto)));
  return `<div class="tw-pair-side">` +
    `<span class="tw-item-date">${g.fecha}</span>` +
    `${_fuenteBadge(g.fuente)}` +
    `<span class="tw-item-desc">${escHtml((g.descripcion || "").slice(0, 28))}</span>` +
    `<span class="tw-item-amount ${amtCls}">${amtSign}${amt}</span>` +
    `</div>`;
}

// ── Card payment suggestions ───────────────────────────────────────────────────
function renderTwCardSuggestions() {
  const sugs = (_twData.card_suggestions || []);
  const sec  = document.getElementById("tw-card-section");
  const list = document.getElementById("tw-card-list");
  document.getElementById("tw-card-count").textContent = sugs.length ? `(${sugs.length})` : "";
  if (!sugs.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  const eMap = Object.fromEntries((_twData.egresos || []).map(e => [e.id, e]));
  const iMap = Object.fromEntries((_twData.cc_ingresos || []).map(i => [i.id, i]));
  list.innerHTML = "";
  sugs.forEach(([outId, inId], idx) => {
    const out = eMap[outId], inp = iMap[inId];
    if (!out || !inp) return;
    const row = document.createElement("div");
    row.className = "tw-pair-row tw-sug-row tw-card-row";
    row.innerHTML =
      _twSugPairSide(out, "−", "tw-amt-egreso") +
      `<span class="tw-pair-arrow">→</span>` +
      _twSugPairSide(inp, "+", "tw-amt-ingreso");
    const btnPar = document.createElement("button");
    btnPar.className = "btn btn-sm tw-sug-btn-pair";
    btnPar.textContent = "Parear";
    btnPar.onclick = () => twPairCardSuggestion(idx);
    const btnIgn = document.createElement("button");
    btnIgn.className = "btn btn-sm tw-sug-btn-ign";
    btnIgn.textContent = "Ignorar";
    btnIgn.onclick = () => twIgnoreCardSuggestion(idx);
    row.appendChild(btnPar);
    row.appendChild(btnIgn);
    list.appendChild(row);
  });
}

function twPairCardSuggestion(idx) {
  const [outId, inId] = _twData.card_suggestions[idx];
  const out = (_twData.egresos || []).find(e => e.id === outId);
  const inp = (_twData.cc_ingresos || []).find(i => i.id === inId);
  if (!out || !inp || _twCardQueuedIds.has(outId) || _twCardQueuedIds.has(inId)) return;
  _twCardQueue.push({ out, in: inp });
  _twCardQueuedIds.add(outId);
  _twCardQueuedIds.add(inId);
  _twData.card_suggestions.splice(idx, 1);
  renderTwCardSuggestions();
  renderTwCardQueue();
}

async function twIgnoreCardSuggestion(idx) {
  const [outId, inId] = _twData.card_suggestions[idx];
  const res = await fetch(`${BASE}/api/gastos/ignore-transfer`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_out: outId, id_in: inId }),
  });
  if (!res.ok) { showToast("Error al ignorar", "err"); return; }
  _twData.card_suggestions.splice(idx, 1);
  renderTwCardSuggestions();
}

function twCardPairAll() {
  const eMap = Object.fromEntries((_twData.egresos || []).map(e => [e.id, e]));
  const iMap = Object.fromEntries((_twData.cc_ingresos || []).map(i => [i.id, i]));
  let added = 0;
  for (const [outId, inId] of [...(_twData.card_suggestions || [])]) {
    if (_twCardQueuedIds.has(outId) || _twCardQueuedIds.has(inId)) continue;
    const out = eMap[outId], inp = iMap[inId];
    if (!out || !inp) continue;
    _twCardQueue.push({ out, in: inp });
    _twCardQueuedIds.add(outId);
    _twCardQueuedIds.add(inId);
    added++;
  }
  if (!added) { showToast("Todas las sugerencias ya están en cola", "info"); return; }
  _twData.card_suggestions = [];
  renderTwCardSuggestions();
  renderTwCardQueue();
  showToast(`${added} pago${added !== 1 ? "s" : ""} agregado${added !== 1 ? "s" : ""} a la cola`, "ok");
}

function renderTwCardQueue() {
  // Re-use tw-queue-section but add a section for card payments if needed
  // For simplicity: fold card payments into the main queue section with a label
  // (both queues are confirmed together via their respective endpoints)
  // Show count in the confirm button
  const totalQ = _twQueue.length + _twCardQueue.length;
  const section = document.getElementById("tw-queue-section");
  if (!totalQ) { section.style.display = "none"; return; }
  section.style.display = "";
  document.getElementById("btn-tw-confirm").textContent =
    `Confirmar ${totalQ} par${totalQ !== 1 ? "es" : ""}` +
    (_twCardQueue.length ? ` (${_twCardQueue.length} pagos tarjeta)` : "");
}

async function twConfirmCardPayments() {
  if (!_twCardQueue.length) return;
  const pairs = _twCardQueue.map(p => [p.out.id, p.in.id]);
  const res = await fetch(`${BASE}/api/gastos/mark-card-payments`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pairs }),
  });
  if (!res.ok) { showToast("Error al guardar pagos", "err"); return; }
  return res.json();
}

// ── Transfer suggestions ───────────────────────────────────────────────────────
function renderTwSuggestions() {
  const sugs = _twData.suggestions;
  const sec  = document.getElementById("tw-sug-section");
  const list = document.getElementById("tw-sug-list");
  document.getElementById("tw-sug-count").textContent = sugs.length ? `(${sugs.length})` : "";

  if (!sugs.length) { sec.style.display = "none"; return; }
  sec.style.display = "";

  const eMap = Object.fromEntries(_twData.egresos.map(e => [e.id, e]));
  const iMap = Object.fromEntries(_twData.ingresos.map(i => [i.id, i]));

  list.innerHTML = "";
  sugs.forEach(([outId, inId], idx) => {
    const out = eMap[outId], inp = iMap[inId];
    if (!out || !inp) return;
    const row = document.createElement("div");
    row.className = "tw-pair-row tw-sug-row";
    row.innerHTML =
      _twSugPairSide(out, "−", "tw-amt-egreso") +
      `<span class="tw-pair-arrow">⇄</span>` +
      _twSugPairSide(inp, "+", "tw-amt-ingreso");
    const btnPar = document.createElement("button");
    btnPar.className = "btn btn-sm tw-sug-btn-pair";
    btnPar.textContent = "Parear";
    btnPar.onclick = () => twPairSuggestion(idx);
    const btnIgn = document.createElement("button");
    btnIgn.className = "btn btn-sm tw-sug-btn-ign";
    btnIgn.textContent = "Ignorar";
    btnIgn.onclick = () => twIgnoreSuggestion(idx);
    row.appendChild(btnPar);
    row.appendChild(btnIgn);
    list.appendChild(row);
  });
}

function twPairSuggestion(idx) {
  const [outId, inId] = _twData.suggestions[idx];
  const out = _twData.egresos.find(e => e.id === outId);
  const inp = _twData.ingresos.find(i => i.id === inId);
  if (!out || !inp || _twQueuedIds.has(outId) || _twQueuedIds.has(inId)) return;
  _twQueue.push({ out, in: inp });
  _twQueuedIds.add(outId);
  _twQueuedIds.add(inId);
  _twData.suggestions.splice(idx, 1);
  renderTwSuggestions();
  renderTwCandidates();
  renderTwQueue();
}

async function twIgnoreSuggestion(idx) {
  const [outId, inId] = _twData.suggestions[idx];
  const res = await fetch(`${BASE}/api/gastos/ignore-transfer`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_out: outId, id_in: inId }),
  });
  if (!res.ok) { showToast("Error al ignorar", "err"); return; }
  _twData.suggestions.splice(idx, 1);
  // Add to local ignored list for immediate UI update
  const eMap = Object.fromEntries(_twData.egresos.map(e => [e.id, e]));
  const iMap = Object.fromEntries(_twData.ingresos.map(i => [i.id, i]));
  const out = eMap[outId], inp = iMap[inId];
  if (out && inp) {
    _twData.ignored.push({
      id_out: outId, id_in: inId,
      fecha_out: out.fecha, desc_out: out.descripcion,
      monto_out: out.monto, fuente_out: out.fuente,
      fecha_in: inp.fecha,  desc_in: inp.descripcion,
      monto_in: inp.monto,  fuente_in: inp.fuente,
    });
  }
  renderTwSuggestions();
  renderTwCandidates();
  renderTwIgnored();
}

function twPairAll() {
  const eMap = Object.fromEntries(_twData.egresos.map(e => [e.id, e]));
  const iMap = Object.fromEntries(_twData.ingresos.map(i => [i.id, i]));
  let added = 0;
  for (const [outId, inId] of [..._twData.suggestions]) {
    if (_twQueuedIds.has(outId) || _twQueuedIds.has(inId)) continue;
    const out = eMap[outId], inp = iMap[inId];
    if (!out || !inp) continue;
    _twQueue.push({ out, in: inp });
    _twQueuedIds.add(outId);
    _twQueuedIds.add(inId);
    added++;
  }
  if (!added) { showToast("Todas las sugerencias ya están en cola", "info"); return; }
  _twData.suggestions = [];
  renderTwSuggestions();
  renderTwCandidates();
  renderTwQueue();
  showToast(`${added} par${added !== 1 ? "es" : ""} agregado${added !== 1 ? "s" : ""} a la cola`, "ok");
}

function _twMakeItem(g, side) {
  const div = document.createElement("div");
  div.className = "tw-item" + (_twData.suggestions.some(s => s[0] === g.id || s[1] === g.id) ? " suggested" : "");
  div.dataset.id = g.id;
  if (_twQueuedIds.has(g.id)) div.classList.add("queued");
  const amt  = Math.abs(parseFloat(g.monto));
  const sign = side === "egreso" ? "−" : "+";
  const cls  = side === "egreso" ? "tw-amt-egreso" : "tw-amt-ingreso";
  div.innerHTML =
    `<span class="tw-item-date">${g.fecha}</span>` +
    `${_fuenteBadge(g.fuente)}` +
    `<span class="tw-item-desc">${escHtml(g.descripcion || "")}</span>` +
    `<span class="tw-item-amount ${cls}">${sign}${_fmtNum2(amt)}</span>`;
  div.addEventListener("click", () => {
    if (_twQueuedIds.has(g.id)) return;
    if (side === "egreso") _twSelectEgreso(g);
    else _twSelectIngreso(g);
  });
  return div;
}

function renderTwCandidates() {
  const { egresos, ingresos, suggestions } = _twData;
  const showAll = document.getElementById("chk-tw-show-all")?.checked;

  let visibleEgresos, visibleIngresos;
  if (showAll) {
    visibleEgresos  = egresos;
    visibleIngresos = ingresos;
  } else {
    const sugOutIds = new Set(suggestions.map(s => s[0]));
    const sugInIds  = new Set(suggestions.map(s => s[1]));
    // Also keep anything already in the queue so it stays visible
    visibleEgresos  = egresos.filter(e  => sugOutIds.has(e.id)  || _twQueuedIds.has(e.id));
    visibleIngresos = ingresos.filter(i => sugInIds.has(i.id)   || _twQueuedIds.has(i.id));
  }

  const eEl = document.getElementById("tw-egresos");
  const iEl = document.getElementById("tw-ingresos");
  document.getElementById("tw-egreso-count").textContent  = visibleEgresos.length  ? `(${visibleEgresos.length})`  : "";
  document.getElementById("tw-ingreso-count").textContent = visibleIngresos.length ? `(${visibleIngresos.length})` : "";
  visibleEgresos  = _twSortItems(visibleEgresos);
  visibleIngresos = _twSortItems(visibleIngresos);

  eEl.innerHTML = "";
  if (!visibleEgresos.length)  eEl.innerHTML = `<p class="tw-empty">Sin egresos sin parear</p>`;
  else visibleEgresos.forEach(g => eEl.appendChild(_twMakeItem(g, "egreso")));
  iEl.innerHTML = "";
  if (!visibleIngresos.length) iEl.innerHTML = `<p class="tw-empty">Sin ingresos sin parear</p>`;
  else visibleIngresos.forEach(g => iEl.appendChild(_twMakeItem(g, "ingreso")));

  _twUpdateSortIndicators();
}

function _twSelectEgreso(g) {
  document.querySelectorAll(".tw-item.selected").forEach(el => el.classList.remove("selected"));
  if (_twSelA && _twSelA.id === g.id) {
    _twSelA = null;
    document.getElementById("tw-selection-bar").style.display = "none";
    return;
  }
  _twSelA = g;
  const el = document.querySelector(`.tw-item[data-id="${g.id}"]`);
  if (el) el.classList.add("selected");
  const amt = _fmtNum2(Math.abs(parseFloat(g.monto)));
  document.getElementById("tw-selection-label").textContent =
    `Seleccionado: ${(g.descripcion || "—").slice(0, 35)} −${amt}`;
  document.getElementById("tw-selection-bar").style.display = "flex";
}

function _twSelectIngreso(g) {
  if (!_twSelA) { showToast("Primero seleccioná un egreso (columna izquierda)", "info"); return; }
  const amtOut = Math.abs(parseFloat(_twSelA.monto));
  const amtIn  = Math.abs(parseFloat(g.monto));
  const pct    = Math.abs(amtOut - amtIn) / Math.max(amtOut, amtIn);
  if (pct > 0.02) {
    if (!confirm(`Los montos difieren (−${_fmtNum2(amtOut)} vs +${_fmtNum2(amtIn)}). ¿Confirmar igual?`)) return;
  }
  _twQueue.push({ out: _twSelA, in: g });
  _twQueuedIds.add(_twSelA.id);
  _twQueuedIds.add(g.id);
  const elOut = document.querySelector(`.tw-item[data-id="${_twSelA.id}"]`);
  const elIn  = document.querySelector(`.tw-item[data-id="${g.id}"]`);
  if (elOut) { elOut.classList.remove("selected"); elOut.classList.add("queued"); }
  if (elIn)  elIn.classList.add("queued");
  _twSelA = null;
  document.getElementById("tw-selection-bar").style.display = "none";
  renderTwQueue();
}

function twCancelSelect() {
  document.querySelectorAll(".tw-item.selected").forEach(el => el.classList.remove("selected"));
  _twSelA = null;
  document.getElementById("tw-selection-bar").style.display = "none";
}

async function twMarkSingle() {
  if (!_twSelA) return;
  if (!confirm(`¿Marcar "${(_twSelA.descripcion||"").slice(0,40)}" como transferencia sin par?`)) return;
  const res = await fetch(`${BASE}/api/gastos/mark-transfers`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pairs: [[_twSelA.id, _twSelA.id]] }),
  });
  if (!res.ok) { showToast("Error al marcar", "err"); return; }
  showToast("Marcado como transferencia (suelto)", "ok");
  await loadTransferWorkspace();
  refreshAfterDataChange();
}

function twRemoveFromQueue(idx) {
  const pair = _twQueue[idx];
  _twQueuedIds.delete(pair.out.id);
  _twQueuedIds.delete(pair.in.id);
  _twQueue.splice(idx, 1);
  [pair.out.id, pair.in.id].forEach(id => {
    const el = document.querySelector(`.tw-item[data-id="${id}"]`);
    if (el) el.classList.remove("queued");
  });
  renderTwQueue();
}

function renderTwQueue() {
  const section = document.getElementById("tw-queue-section");
  const list    = document.getElementById("tw-queue-list");
  const btn     = document.getElementById("btn-tw-confirm");
  const total   = _twQueue.length + _twCardQueue.length;
  if (!total) { section.style.display = "none"; return; }
  section.style.display = "";
  btn.textContent = `Confirmar ${total} par${total !== 1 ? "es" : ""}` +
    (_twCardQueue.length ? ` (${_twCardQueue.length} pago${_twCardQueue.length !== 1 ? "s" : ""} tarjeta)` : "");
  list.innerHTML = "";
  _twQueue.forEach((pair, i) => {
    const row = document.createElement("div");
    row.className = "tw-pair-row";
    const amtOut = _fmtNum2(Math.abs(parseFloat(pair.out.monto)));
    const amtIn  = _fmtNum2(Math.abs(parseFloat(pair.in.monto)));
    row.innerHTML =
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${pair.out.fecha}</span>` +
        `${_fuenteBadge(pair.out.fuente)}` +
        `<span class="tw-item-desc">${escHtml((pair.out.descripcion||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-egreso">−${amtOut}</span>` +
      `</div>` +
      `<span class="tw-pair-arrow">⇄</span>` +
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${pair.in.fecha}</span>` +
        `${_fuenteBadge(pair.in.fuente)}` +
        `<span class="tw-item-desc">${escHtml((pair.in.descripcion||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-ingreso">+${amtIn}</span>` +
      `</div>`;
    const rmBtn = document.createElement("button");
    rmBtn.className = "tw-remove-btn";
    rmBtn.textContent = "✕";
    rmBtn.onclick = () => twRemoveFromQueue(i);
    row.appendChild(rmBtn);
    list.appendChild(row);
  });
}

function twAutoSuggest() { if (_twData) twPairAll(); }

async function twConfirm() {
  if (!_twQueue.length && !_twCardQueue.length) return;
  let total = 0;
  if (_twQueue.length) {
    const res = await fetch(`${BASE}/api/gastos/mark-transfers`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pairs: _twQueue.map(p => [p.out.id, p.in.id]) }),
    });
    if (!res.ok) { showToast("Error al guardar transferencias", "err"); return; }
    total += (await res.json()).marcados;
  }
  if (_twCardQueue.length) {
    const res = await fetch(`${BASE}/api/gastos/mark-card-payments`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pairs: _twCardQueue.map(p => [p.out.id, p.in.id]) }),
    });
    if (!res.ok) { showToast("Error al guardar pagos de tarjeta", "err"); return; }
    total += (await res.json()).marcados;
  }
  showToast(`✓ ${total} movimientos marcados`, "ok");
  await loadTransferWorkspace();
  refreshAfterDataChange();
}

async function twUnmark(ids) {
  const res = await fetch(`${BASE}/api/gastos/unmark-transfers`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) { showToast("Error al desmarcar", "err"); return; }
  await loadTransferWorkspace();
  // If the unmarked IDs have no auto-match, they won't appear in the filtered
  // view — auto-enable "Mostrar todos" so the user can find them.
  const idSet = new Set(ids);
  const haveMatch = _twData.suggestions.some(s => idSet.has(s[0]) || idSet.has(s[1]));
  if (!haveMatch) {
    document.getElementById("chk-tw-show-all").checked = true;
    renderTwCandidates();
    showToast("Desmarcado — sin match automático, activé «Mostrar todos»", "ok");
  } else {
    showToast("Desmarcado", "ok");
  }
  refreshAfterDataChange();
}

function renderTwExisting() {
  const { pairs, singles } = _twData.existing;
  const count = pairs.length + singles.length;
  document.getElementById("tw-existing-count").textContent = count ? `(${count})` : "";
  const list = document.getElementById("tw-existing-list");
  if (!count) { list.innerHTML = `<p class="tw-empty">Sin transferencias marcadas aún</p>`; return; }
  list.innerHTML = "";
  for (const pair of pairs) {
    const isCardPayment = pair.categoria === "Pago de Tarjeta";
    const row = document.createElement("div");
    row.className = "tw-pair-row tw-existing-row" + (isCardPayment ? " tw-card-row" : "");
    const amtOut = _fmtNum2(Math.abs(parseFloat(pair.out.monto)));
    const amtIn  = _fmtNum2(Math.abs(parseFloat(pair.in.monto)));
    const arrow  = isCardPayment ? "→" : "⇄";
    const catBadge = isCardPayment
      ? `<span class="tw-single-badge" style="color:#0369a1;background:#e0f2fe">💳 pago</span>`
      : "";
    row.innerHTML =
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${pair.out.fecha}</span>` +
        `${_fuenteBadge(pair.out.fuente)}` +
        `<span class="tw-item-desc">${escHtml((pair.out.descripcion||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-egreso">−${amtOut}</span>` +
      `</div>` +
      `<span class="tw-pair-arrow">${arrow}</span>` +
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${pair.in.fecha}</span>` +
        `${_fuenteBadge(pair.in.fuente)}` +
        `<span class="tw-item-desc">${escHtml((pair.in.descripcion||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-ingreso">+${amtIn}</span>` +
      `</div>` + catBadge;
    const btn = document.createElement("button");
    btn.className = "btn btn-sm tw-unmark-btn";
    btn.textContent = "Deshacer";
    btn.onclick = () => twUnmark([pair.out.id, pair.in.id]);
    row.appendChild(btn);
    list.appendChild(row);
  }
  for (const g of singles) {
    const row = document.createElement("div");
    row.className = "tw-pair-row tw-existing-row";
    const amt  = _fmtNum2(Math.abs(parseFloat(g.monto)));
    const sign = parseFloat(g.monto) > 0 ? "−" : "+";
    const cls  = parseFloat(g.monto) > 0 ? "tw-amt-egreso" : "tw-amt-ingreso";
    row.innerHTML =
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${g.fecha}</span>` +
        `${_fuenteBadge(g.fuente)}` +
        `<span class="tw-item-desc">${escHtml((g.descripcion||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount ${cls}">${sign}${amt}</span>` +
      `</div>` +
      `<span class="tw-single-badge">suelto</span>` +
      `<div class="tw-pair-side"></div>`;
    const btn = document.createElement("button");
    btn.className = "btn btn-sm tw-unmark-btn";
    btn.textContent = "Deshacer";
    btn.onclick = () => twUnmark([g.id]);
    row.appendChild(btn);
    list.appendChild(row);
  }
}

function twToggleExisting() {
  const list  = document.getElementById("tw-existing-list");
  const arrow = document.getElementById("tw-existing-arrow");
  const open  = list.style.display === "none";
  list.style.display  = open ? "" : "none";
  arrow.textContent   = open ? "▾" : "▸";
}

function renderTwIgnored() {
  const ignored = _twData.ignored || [];
  const zone  = document.getElementById("tw-ignored-zone");
  const list  = document.getElementById("tw-ignored-list");
  document.getElementById("tw-ignored-count").textContent = ignored.length ? `(${ignored.length})` : "";
  if (!ignored.length) { zone.style.display = "none"; return; }
  zone.style.display = "";
  list.innerHTML = "";
  ignored.forEach(p => {
    const row = document.createElement("div");
    row.className = "tw-pair-row tw-existing-row";
    const amtOut = _fmtNum2(Math.abs(parseFloat(p.monto_out)));
    const amtIn  = _fmtNum2(Math.abs(parseFloat(p.monto_in)));
    row.innerHTML =
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${p.fecha_out}</span>` +
        `${_fuenteBadge(p.fuente_out)}` +
        `<span class="tw-item-desc">${escHtml((p.desc_out||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-egreso">−${amtOut}</span>` +
      `</div>` +
      `<span class="tw-pair-arrow">⇄</span>` +
      `<div class="tw-pair-side">` +
        `<span class="tw-item-date">${p.fecha_in}</span>` +
        `${_fuenteBadge(p.fuente_in)}` +
        `<span class="tw-item-desc">${escHtml((p.desc_in||"").slice(0,28))}</span>` +
        `<span class="tw-item-amount tw-amt-ingreso">+${amtIn}</span>` +
      `</div>`;
    const btn = document.createElement("button");
    btn.className = "btn btn-sm tw-unmark-btn";
    btn.textContent = "Restaurar";
    btn.onclick = () => twUnignore(p.id_out, p.id_in);
    row.appendChild(btn);
    list.appendChild(row);
  });
}

async function twUnignore(id_out, id_in) {
  const res = await fetch(`${BASE}/api/gastos/ignore-transfer`, {
    method: "DELETE", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_out, id_in }),
  });
  if (!res.ok) { showToast("Error al restaurar", "err"); return; }
  showToast("Sugerencia restaurada", "ok");
  await loadTransferWorkspace();
}

function twToggleIgnored() {
  const list  = document.getElementById("tw-ignored-list");
  const arrow = document.getElementById("tw-ignored-arrow");
  const open  = list.style.display === "none";
  list.style.display = open ? "" : "none";
  arrow.textContent  = open ? "▾" : "▸";
}

document.getElementById("btn-tw-autosugerir").addEventListener("click", twAutoSuggest);
document.getElementById("btn-tw-pair-all").addEventListener("click", twPairAll);
document.getElementById("btn-tw-card-all").addEventListener("click", twCardPairAll);
document.getElementById("btn-tw-refresh").addEventListener("click", loadTransferWorkspace);
document.getElementById("btn-tw-confirm").addEventListener("click", twConfirm);
document.getElementById("btn-tw-cancel-select").addEventListener("click", twCancelSelect);
document.getElementById("btn-tw-mark-single").addEventListener("click", twMarkSingle);
document.getElementById("chk-tw-show-all").addEventListener("change", renderTwCandidates);
document.querySelectorAll(".tw-sh[data-twsort]").forEach(el => {
  el.addEventListener("click", () => {
    const field = el.dataset.twsort;
    if (_twSortField === field) _twSortDir = _twSortDir === 'desc' ? 'asc' : 'desc';
    else { _twSortField = field; _twSortDir = 'desc'; }
    if (_twData) renderTwCandidates();
  });
});

// ── Import batches ────────────────────────────────────────────────────────────
const _FUENTE_LABEL = {
  amex:"AMEX", bbva_mc:"BBVA MC", bbva_visa:"BBVA Visa",
  bbva_cuenta:"BBVA Cuenta", galicia_mc:"Galicia MC", mercadopago:"MercadoPago",
};

let _lastImportByFuente = {};

async function loadImportaciones() {
  const res  = await fetch(`${BASE}/api/importaciones`);
  const data = await res.json();

  // Populate _lastImportByFuente for inline parser panels in Cuentas tab
  _lastImportByFuente = {};
  for (const imp of data) {
    if (!_lastImportByFuente[imp.fuente]) _lastImportByFuente[imp.fuente] = imp;
  }

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
      refreshAfterDataChange();
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


// ── Categorization rules ──────────────────────────────────────────────────────
let _rules = [];

async function loadRules() {
  const res  = await fetch(`${BASE}/api/rules`);
  const data = await res.json();
  _rules = (data.reglas||[]).map(r => ({
    palabras:    Array.isArray(r.palabras) ? r.palabras.map(String) : _patternToWords(r.patron||""),
    patron:      r.patron || null,
    categoria:   r.categoria || "",
    especial:    !!r.especial,
    solo_egresos: !!r.solo_egresos,
    fuentes:     Array.isArray(r.fuentes) ? r.fuentes : [],
  }));
  renderRules();
}

function _patternToWords(patron) {
  const m = patron.match(/^\(\?i\)\((.+)\)$/s);
  return m ? m[1].split("|").map(w=>w.trim()).filter(Boolean) : patron ? [patron] : [];
}

let _dragSrcIdx = null;

function _buildFuentesPickerHtml(i, selectedFuentes) {
  const src   = (_cuentasData && _cuentasData.length > 0) ? _cuentasData : _FUENTES_FALLBACK;
  const label = selectedFuentes.length === 0
    ? "Todas las fuentes"
    : `${selectedFuentes.length} fuente${selectedFuentes.length > 1 ? "s" : ""}`;
  const opts = src.map(c => {
    const chk = selectedFuentes.includes(c.fuente) ? "checked" : "";
    return `<label class="fuentes-opt"><input type="checkbox" class="fuente-chk" value="${escHtml(c.fuente)}" ${chk}> ${escHtml(c.nombre||c.fuente)}</label>`;
  }).join("");
  return `<details class="fuentes-picker" data-i="${i}">
    <summary class="fuentes-summary" title="Filtrar por fuente">${escHtml(label)}</summary>
    <div class="fuentes-opts">${opts}</div>
  </details>`;
}

function renderRules() {
  // Build duplicate-word map for all rules
  const wordMap = {};
  _rules.forEach((r, i) => r.palabras.forEach(w => {
    const k = w.toLowerCase();
    if (!wordMap[k]) wordMap[k] = [];
    wordMap[k].push(i);
  }));
  const dupes = new Set(Object.entries(wordMap).filter(([,v]) => v.length > 1).map(([k]) => k));

  const list = document.getElementById("rules-list");
  if (!list) return;
  list.innerHTML = "";
  _rules.forEach((rule, i) => {
    const card = document.createElement("div");
    card.className = "rule-card" + (rule.especial ? " rule-especial" : "");
    card.draggable = true;
    card.dataset.ruleIdx = i;

    const tagsHtml = rule.palabras.map((w, j) => {
      const isDup = dupes.has(w.toLowerCase());
      return `<span class="tag${isDup ? " tag-dup" : ""}" title="${isDup ? "Esta palabra ya está en otra regla" : ""}">
        <span class="tag-label" title="Doble clic para editar" ondblclick="editTag(${i},${j})">${escHtml(w)}</span>
        <button class="tag-x" type="button" onclick="removeTag(${i},${j})">×</button>
      </span>`;
    }).join("");

    card.innerHTML = `
      <div class="rule-header">
        <span class="drag-handle" title="Arrastrar para reordenar">⠿</span>
        <span class="rule-num">#${i + 1}</span>
        <input class="rule-cat" data-i="${i}" value="${escHtml(rule.categoria)}" placeholder="Nombre de categoría" list="cat-datalist" autocomplete="off">
        <label class="rule-especial-label" title="Categoría especial: se excluye de totales y gráficos">
          <input type="checkbox" class="rule-especial-chk" data-i="${i}" ${rule.especial ? "checked" : ""}> Especial
        </label>
        <label class="rule-especial-label" title="Solo aplica a egresos (monto positivo)">
          <input type="checkbox" class="rule-solo-egresos-chk" data-i="${i}" ${rule.solo_egresos ? "checked" : ""}> Solo egresos
        </label>
        ${_buildFuentesPickerHtml(i, rule.fuentes || [])}
        <button type="button" class="btn btn-sm" onclick="openRulePreview(${i})">▶ Probar</button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeRule(${i})">✕</button>
      </div>
      <div class="rule-tags" id="tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input" data-i="${i}" placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addTag(event,${i})">
      </div>`;
    list.appendChild(card);

    // Drag events
    card.addEventListener("dragstart", e => {
      _dragSrcIdx = i;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
    card.addEventListener("dragover", e => { e.preventDefault(); card.classList.add("drag-over"); });
    card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
    card.addEventListener("drop", e => {
      e.preventDefault();
      card.classList.remove("drag-over");
      if (_dragSrcIdx === null || _dragSrcIdx === i) return;
      _syncRules();
      const [moved] = _rules.splice(_dragSrcIdx, 1);
      _rules.splice(i, 0, moved);
      _dragSrcIdx = null;
      renderRules();
      clearTimeout(_saveRulesTimer); _doSaveRules();
    });

    // Checkboxes — save immediately (no debounce) so refreshing right after
    // clicking doesn't lose the change.
    card.querySelector(".rule-especial-chk").addEventListener("change", function() {
      _syncRules();
      _rules[parseInt(this.dataset.i)].especial = this.checked;
      this.closest(".rule-card").classList.toggle("rule-especial", this.checked);
      clearTimeout(_saveRulesTimer); _doSaveRules();
    });
    card.querySelector(".rule-solo-egresos-chk").addEventListener("change", function() {
      _syncRules();
      clearTimeout(_saveRulesTimer); _doSaveRules();
    });

    // Fuentes picker — update summary text on change
    const picker = card.querySelector(".fuentes-picker");
    picker.querySelectorAll(".fuente-chk").forEach(chk => {
      chk.addEventListener("change", () => {
        const checked = [...picker.querySelectorAll(".fuente-chk:checked")].map(c => c.value);
        picker.querySelector(".fuentes-summary").textContent =
          checked.length === 0 ? "Todas las fuentes" : `${checked.length} fuente${checked.length > 1 ? "s" : ""}`;
        _scheduleSaveRules();
      });
    });
  });
}

function _syncRules() {
  document.querySelectorAll(".rule-cat").forEach((inp, i) => { if (_rules[i]) _rules[i].categoria = inp.value; });
  document.querySelectorAll(".rule-especial-chk").forEach((chk, i) => { if (_rules[i]) _rules[i].especial = chk.checked; });
  document.querySelectorAll(".rule-solo-egresos-chk").forEach((chk, i) => { if (_rules[i]) _rules[i].solo_egresos = chk.checked; });
  document.querySelectorAll(".fuentes-picker").forEach((picker, i) => {
    if (!_rules[i]) return;
    _rules[i].fuentes = [...picker.querySelectorAll(".fuente-chk:checked")].map(c => c.value);
  });
}

// Auto-save with debounce
let _saveRulesTimer = null;
async function _doSaveRules() {
  _syncRules();
  const reglas = _rules
    .filter(r => r.categoria.trim() && (r.palabras.length > 0 || r.especial))
    .map(r => ({
      palabras:     r.palabras,
      categoria:    r.categoria,
      especial:     !!r.especial,
      solo_egresos: r.solo_egresos || null,
      fuentes:      r.fuentes || [],
    }));
  const res = await fetch(`${BASE}/api/rules`, {
    method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({reglas}),
  });
  showToast(res.ok ? "✓ Reglas guardadas" : "❌ Error al guardar reglas", res.ok ? "ok" : "err", res.ok ? 2000 : 0);
}
function _scheduleSaveRules() {
  clearTimeout(_saveRulesTimer);
  _saveRulesTimer = setTimeout(_doSaveRules, 800);
}
document.getElementById("rules-list")?.addEventListener("focusout", _scheduleSaveRules);

// ── Rule dry-run preview (shared modal for cat + user modes) ─────────────────
let _previewMode    = "cat"; // "cat" | "user"
let _previewRuleIdx = null;

function openCatPreview(nombre) {
  let idx = _rules.findIndex(r => r.categoria === nombre);
  if (idx === -1) {
    _rules.push({palabras: [], categoria: nombre, especial: false, solo_egresos: false, fuentes: [], patron: null});
    idx = _rules.length - 1;
  }
  openRulePreview(idx);
}

function openRulePreview(i) {
  _syncRules();
  _previewMode    = "cat";
  _previewRuleIdx = i;
  const rule = _rules[i];
  document.getElementById("rp-title").textContent   = `Probar regla: "${rule.categoria || "sin nombre"}"`;
  document.getElementById("rp-col-actual").textContent = "Categoría actual";
  document.getElementById("rp-col-nueva").textContent  = "Nueva";
  document.getElementById("rp-manuales-row").style.display = "";
  document.getElementById("rp-results").innerHTML    = "";
  document.getElementById("rp-footer").style.display = "none";
  document.getElementById("rule-preview-modal").style.display = "flex";
}

function openUserRulePreview(i) {
  _syncUserRules();
  _previewMode    = "user";
  _previewRuleIdx = i;
  const rule = _userRules[i];
  document.getElementById("rp-title").textContent   = `Probar regla persona: "${rule.usuario || "sin nombre"}"`;
  document.getElementById("rp-col-actual").textContent = "Persona actual";
  document.getElementById("rp-col-nueva").textContent  = "Nueva";
  document.getElementById("rp-manuales-row").style.display = "none";
  document.getElementById("rp-results").innerHTML    = "";
  document.getElementById("rp-footer").style.display = "none";
  document.getElementById("rule-preview-modal").style.display = "flex";
}

function closeRulePreview() {
  document.getElementById("rule-preview-modal").style.display = "none";
}

async function runRulePreview() {
  if (_previewRuleIdx === null) return;
  const isCat  = _previewMode === "cat";
  const rule   = isCat ? _rules[_previewRuleIdx] : _userRules[_previewRuleIdx];
  const desde    = document.getElementById("rp-desde").value;
  const hasta    = document.getElementById("rp-hasta").value;
  const manuales = document.getElementById("rp-manuales").checked;
  const btn      = document.getElementById("btn-rp-run");
  btn.disabled = true; btn.textContent = "Buscando…";
  try {
    let url, payload;
    if (isCat) {
      url     = `${BASE}/api/rules/preview`;
      payload = {regla: {palabras: rule.palabras, categoria: rule.categoria, fuentes: rule.fuentes || [], solo_egresos: !!rule.solo_egresos}, fecha_desde: desde, fecha_hasta: hasta, incluir_manuales: manuales};
    } else {
      url     = `${BASE}/api/config/usuarios/preview`;
      payload = {regla: {palabras: rule.palabras, usuario: rule.usuario, fuentes: rule.fuentes || []}, fecha_desde: desde, fecha_hasta: hasta};
    }
    const res    = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data   = await res.json();
    const gastos = data.gastos || [];
    const results = document.getElementById("rp-results");
    const footer  = document.getElementById("rp-footer");
    if (!gastos.length) {
      results.innerHTML = '<p class="rp-empty">No se encontraron movimientos que coincidan con esta regla en el período indicado.</p>';
      footer.style.display = "none";
      return;
    }
    results.innerHTML = `<table class="rp-table">
      <thead><tr>
        <th><input type="checkbox" id="rp-select-all" checked onchange="toggleSelectAllPreview(this.checked)"></th>
        <th>Fecha</th><th>Descripción</th><th>Monto</th>
        <th id="rp-col-actual-th">${escHtml(document.getElementById("rp-col-actual").textContent)}</th>
        <th id="rp-col-nueva-th">${escHtml(document.getElementById("rp-col-nueva").textContent)}</th>
      </tr></thead>
      <tbody>${gastos.map(g => `
        <tr data-id="${g.id}">
          <td><input type="checkbox" class="rp-chk" checked onchange="updateRpCount()"></td>
          <td>${escHtml(g.fecha)}</td>
          <td class="rp-desc">${escHtml(g.descripcion)}</td>
          <td class="rp-monto ${g.monto > 0 ? "monto-egreso" : "monto-ingreso"}">${g.monto > 0 ? "" : "+"}${Math.abs(g.monto).toFixed(2)}</td>
          <td class="rp-cat-actual">${escHtml(g.categoria_actual || "—")}</td>
          <td class="rp-cat-new">${escHtml(g.categoria_nueva)}</td>
        </tr>`).join("")}
      </tbody></table>`;
    footer.style.display = "flex";
    updateRpCount();
  } finally {
    btn.disabled = false; btn.textContent = "🔍 Buscar";
  }
}

function updateRpCount() {
  document.getElementById("rp-count").textContent = document.querySelectorAll(".rp-chk:checked").length;
}

function toggleSelectAllPreview(checked) {
  document.querySelectorAll(".rp-chk").forEach(c => c.checked = checked);
  updateRpCount();
}

async function applySelectedPreview() {
  if (_previewRuleIdx === null) return;
  const isCat = _previewMode === "cat";
  const rule  = isCat ? _rules[_previewRuleIdx] : _userRules[_previewRuleIdx];
  const ids   = [...document.querySelectorAll(".rp-chk:checked")]
    .map(c => parseInt(c.closest("tr").dataset.id)).filter(Boolean);
  if (!ids.length) { showToast("No hay movimientos seleccionados", "err"); return; }
  let res;
  if (isCat) {
    res = await fetch(`${BASE}/api/rules/apply-selected`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ids, categoria: rule.categoria}),
    });
  } else {
    res = await fetch(`${BASE}/api/config/usuarios/apply-selected`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ids, usuario: rule.usuario}),
    });
  }
  const data = await res.json();
  const n    = data.aplicados ?? data.asignados ?? ids.length;
  showToast(`✓ ${n} movimientos ${isCat ? "categorizados" : "asignados"}`, "ok", 2500);
  closeRulePreview();
  loadGastos();
  if (isCat) loadCategorias();
}

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
  if (!list) return;
  list.innerHTML = "";
  _matchRules.forEach((r, i) => {
    const card = document.createElement("div");
    card.className = "match-rule-card";
    card.innerHTML = `
      <div class="match-rule-header">
        <input class="match-nombre" data-i="${i}" value="${escHtml(r.nombre)}" placeholder="Nombre de la regla">
        <div style="display:flex;gap:.4rem;align-items:center">
          <button class="btn btn-sm" onclick="applyOneMatchRule(${i})">✓ Aplicar</button>
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
document.getElementById("match-rules-list")?.addEventListener("focusout", _scheduleSaveMatchRules);

function removeMatchRule(i) { _syncMatchRules(); _matchRules.splice(i,1); renderMatchRules(); _scheduleSaveMatchRules(); }

// ── Saldos widget ─────────────────────────────────────────────────────────────
let _widgetCuentas = [];

async function loadSaldos() {
  const res    = await fetch(`${BASE}/api/cuentas`);
  _widgetCuentas = await res.json();
  // Reuse the same fetch to keep fuente dropdowns up-to-date
  _cuentasData = _widgetCuentas;
  _populateFuenteSelects();
  renderSaldos(_widgetCuentas.filter(c => c.activa));
  // Ya tenemos las cuentas-tarjeta (con su consumo y nombre custom) → render del
  // widget de tarjetas. Se llama siempre, aunque no haya vencimientos PDF: cada
  // tarjeta muestra su consumo scrappeado del período abierto.
  renderVencimientos(_vencData);
}

function _saldoChipMonto(saldo, moneda) {
  const cls = moneda === "USD" ? "usd-val" : "ars-val";
  const sym = moneda === "USD" ? "U$S" : "$";
  return `<span class="${cls}">${sym} ${_fmtSaldo(saldo)}</span>`;
}

// Horas entre corridas según el schedule de la instancia.
// "every:Nh" → N ; "HH:MM" (legacy diario) → 24.
function _scheduleIntervalHours(schedule) {
  const m = /^every:(\d+)h$/.exec(schedule || "");
  return m ? parseInt(m[1], 10) : 24;
}

// Estado del último scrape de una cuenta, para la barrita de la home.
//   "err"  (rojo)     → el último run falló (o sesión expirada)
//   "warn" (amarillo) → no corrió a horario (sin OK reciente / nunca corrió)
//   "ok"   (verde)    → corrió OK dentro de la ventana esperada
//   null              → la cuenta no tiene scraper (manual) o está deshabilitado
function _scraperStatusColor(c) {
  if (!c || !c.scraper_instance_id || !c.scraper_enabled) return null;
  if (c.scraper_estado === "running") return "run";   // azul — corriendo ahora mismo
  if (c.scraper_estado === "error" || c.scraper_estado === "session_expired") return "err";
  const last = c.scraper_ultimo_ok || c.scraper_ultimo_run;
  if (!last) return "warn";  // nunca tuvo un run exitoso
  const iso  = last.endsWith("Z") ? last : last + "Z";  // timestamps guardados en UTC
  const ageH = (Date.now() - new Date(iso).getTime()) / 3600000;
  const interval = _scheduleIntervalHours(c.scraper_schedule);
  // Amarillo si pasaron más de 2 intervalos sin un run exitoso.
  if (ageH > interval * 2) return "warn";
  return "ok";
}

// Tooltip explicativo para la barrita de estado.
function _scraperStatusTitle(c) {
  const st = _scraperStatusColor(c);
  if (!st) return "";
  if (st === "run")  return "Scrape en curso… (se actualiza solo al terminar)";
  const last = c.scraper_ultimo_ok || c.scraper_ultimo_run;
  const when = last ? _fmtTs(last) : "nunca";
  if (st === "err")  return `Último scrape: FALLÓ — ${when}${c.scraper_error_msg ? ` (${c.scraper_error_msg})` : ""}`;
  if (st === "warn") return `Scrape atrasado — último OK: ${when}`;
  return `Último scrape OK — ${when}`;
}

// Mientras alguna cuenta esté con scrape corriendo (chip azul), refrescar solo
// hasta que termine, para que el chip cambie de color sin recargar la página.
let _scrapeRunningTimer = null;
function _scheduleScrapeAutorefresh(cuentas) {
  const anyRunning = (cuentas || []).some(c => _scraperStatusColor(c) === "run");
  if (anyRunning && !_scrapeRunningTimer) {
    _scrapeRunningTimer = setInterval(() => { loadSaldos(); loadVencimientos?.(); }, 8000);
  } else if (!anyRunning && _scrapeRunningTimer) {
    clearInterval(_scrapeRunningTimer);
    _scrapeRunningTimer = null;
  }
}

// Devuelve la cuenta (con campos scraper_*) por fuente, desde el cache del widget.
function _cuentaByFuente(fuente) {
  return (_widgetCuentas || []).find(c => c.fuente === fuente);
}

// Selector de frecuencia del scraper. Valores "every:Nh" (mín 2h, default 4h).
// Si la instancia trae un schedule legacy "HH:MM", lo conserva como opción extra
// para no perderlo hasta que el usuario elija un intervalo.
const SCHEDULE_INTERVALS = [
  ["every:2h",  "Cada 2 horas"],
  ["every:3h",  "Cada 3 horas"],
  ["every:4h",  "Cada 4 horas"],
  ["every:6h",  "Cada 6 horas"],
  ["every:8h",  "Cada 8 horas"],
  ["every:12h", "Cada 12 horas"],
  ["every:24h", "1 vez al día"],
];
function _scheduleSelect(id, current) {
  const cur = current || "every:4h";
  const isLegacy = !/^every:\d+h$/.test(cur);
  let opts = SCHEDULE_INTERVALS.map(([val, lbl]) =>
    `<option value="${val}"${val === cur ? " selected" : ""}>${lbl}</option>`
  ).join("");
  if (isLegacy) {
    opts = `<option value="${escHtml(cur)}" selected>Diario ${escHtml(cur)} (legacy)</option>` + opts;
  }
  return `<select id="${id}">${opts}</select>`;
}

function renderSaldos(cuentas) {
  const widget = document.getElementById("saldos-widget");
  if (!cuentas.length) { widget.style.display = "none"; return; }
  _scheduleScrapeAutorefresh(cuentas);   // poll mientras haya scrapes corriendo
  widget.style.display = "grid";
  widget.innerHTML = cuentas.map(c => {
    const moneda  = c.moneda || "ARS";
    const isMulti = moneda === "MULTI";
    const isUsd   = moneda === "USD";
    const sArs    = c.saldo     || 0;
    const sUsd    = c.saldo_usd || 0;

    const montoHtml = isMulti
      ? `${_saldoChipMonto(sArs, "ARS")} · ${_saldoChipMonto(sUsd, "USD")}`
      : isUsd ? _saldoChipMonto(sUsd, "USD") : _saldoChipMonto(sArs, "ARS");

    const editInputs = isMulti ? `
      <div style="display:flex;flex-direction:column;gap:.2rem">
        <div style="display:flex;gap:.3rem;align-items:center">
          <span style="font-size:.72rem;color:#999;width:26px">ARS</span>
          <input type="text" inputmode="decimal" id="saldo-input-ars-${c.fuente}" value="${_fmtNum2(sArs)}" style="width:80px"
                 onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')">
        </div>
        <div style="display:flex;gap:.3rem;align-items:center">
          <span style="font-size:.72rem;color:#999;width:26px">USD</span>
          <input type="text" inputmode="decimal" id="saldo-input-usd-${c.fuente}" value="${_fmtNum2(sUsd)}" style="width:80px"
                 onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')">
        </div>
      </div>` : `
      <input type="text" inputmode="decimal" id="saldo-input-${c.fuente}" value="${_fmtNum2(isUsd ? sUsd : sArs)}"
             onkeydown="if(event.key==='Enter')saveSaldo('${c.fuente}')" style="width:90px">`;

    const fechaTitle = c.fecha_actualizacion ? `Actualizado ${c.fecha_actualizacion}` : "Sin datos";
    const scrape     = _scraperStatusColor(c);
    const scrapeCls  = scrape ? ` scrape-${scrape}` : "";
    const scrapeTtl  = scrape ? ` · ${_scraperStatusTitle(c)}` : "";
    return `
      <div class="saldo-chip" id="saldo-card-${c.fuente}">
        <button class="saldo-chip-btn${scrapeCls}" onclick="toggleSaldoEdit('${c.fuente}')" title="${escHtml(fechaTitle)} — tap para editar${escHtml(scrapeTtl)}">
          <span class="saldo-chip-name">${escHtml(c.nombre)}</span>
          <span class="saldo-chip-monto">${montoHtml}</span>
        </button>
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

// Refresco automático de widgets en background (configurable en UI → Interfaz).
// Solo actúa cuando no hay un scrape corriendo (ese caso ya usa _scrapeRunningTimer a 8s).
let _bgRefreshTimer = null;
function _restartBgRefresh() {
  if (_bgRefreshTimer) { clearInterval(_bgRefreshTimer); _bgRefreshTimer = null; }
  const mins = parseInt(getUiPref("widget_refresh_mins"), 10);
  if (!mins) return;
  _bgRefreshTimer = setInterval(() => {
    const anyRunning = (_widgetCuentas || []).some(c => _scraperStatusColor(c) === "run");
    if (!anyRunning) { loadSaldos(); loadVencimientos?.(); }
  }, mins * 60 * 1000);
}
_restartBgRefresh();

// Al volver al tab tras estar oculto, refresca de golpe.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) { loadSaldos(); loadVencimientos?.(); }
});

// ── Vencimientos widget ───────────────────────────────────────────────────────

const _FUENTE_LABELS = {
  amex: "AMEX", bbva_mc: "BBVA Mastercard", bbva_visa: "BBVA Visa",
  galicia_mc: "Galicia MC", bbva_cuenta: "BBVA Cuenta",
  mercadopago: "MercadoPago",
};

// Nombre custom de la cuenta (el que edita el usuario en Config → Cuentas).
// Cae al label fijo de la fuente si todavía no se cargaron las cuentas.
function _cuentaNombre(fuente) {
  const c = (_widgetCuentas || []).find(x => x.fuente === fuente);
  return (c && c.nombre) || _FUENTE_LABELS[fuente] || fuente;
}
function _cuentaShortName(fuente) {
  const c = (_widgetCuentas || []).find(x => x.fuente === fuente);
  return (c && (c.short_name || c.nombre)) || _FUENTE_LABELS[fuente] || fuente.replace(/_/g, " ");
}
function _cuentaColor(fuente) {
  const c = (_widgetCuentas || []).find(x => x.fuente === fuente);
  return (c && c.color) || null;
}
function _fuenteBadge(fuente) {
  const color = _cuentaColor(fuente);
  const label = _cuentaShortName(fuente);
  const style = color ? ` style="background:${escHtml(color)};color:#fff"` : "";
  return `<span class="badge badge-${escHtml(fuente)}"${style}>${escHtml(label)}</span>`;
}

let _vencData = [];  // último payload de vencimientos (para re-render al cargar cuentas)

async function loadVencimientos() {
  try {
    // Necesitamos las cuentas (con estado de scrape) para pintar la barrita de
    // cada chip de tarjeta. Si todavía no están cacheadas, cargarlas primero.
    if (!_widgetCuentas || !_widgetCuentas.length) {
      try { await loadSaldos(); } catch(_) {}
    }
    const res  = await fetch(`${BASE}/api/stats/vencimientos`);
    const data = await res.json();
    _vencData = data.vencimientos || [];
    renderVencimientos(_vencData);
  } catch(e) {
    console.error("loadVencimientos error:", e);
  }
}

function renderVencimientos(items) {
  const widget = document.getElementById("vencimientos-widget");
  items = items || [];

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

  // Info de vencimiento por fuente (se cruza después con las cuentas-tarjeta).
  const vencByFuente = {};

  deduped.forEach(v => {
    const vencDate = new Date(v.fecha_venc + "T00:00:00");
    const diffMs   = vencDate - today;
    const dias     = Math.round(diffMs / 86400000);

    let cls, diasTxt, diasShort;
    if (dias < 0) {
      cls = "vencido";
      diasTxt = `Vencido hace ${-dias} día${-dias === 1 ? "" : "s"}`;
      diasShort = "vencido";
    } else if (dias === 0) {
      cls = "urgente";
      diasTxt = "Vence hoy";
      diasShort = "hoy";
    } else if (dias <= _tUrgente) {
      cls = "urgente";
      diasTxt = `Vence en ${dias} día${dias === 1 ? "" : "s"}`;
      diasShort = `${dias}d`;
    } else if (dias <= _tPronto) {
      cls = "pronto";
      diasTxt = `En ${dias} días`;
      diasShort = `${dias}d`;
    } else {
      cls = "ok";
      diasTxt = `En ${dias} días`;
      diasShort = `${dias}d`;
    }

    const label  = _cuentaNombre(v.fuente);

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

    // Badge de pago: verde = emparejado confirmado; amarillo = "probable"
    // (hay un Pago de Tarjeta por monto cerca del vencimiento, sin emparejar).
    let pagoHtml = "";
    if (v.pago_confirmado) {
      pagoHtml = `<span class="venc-pago-ok" title="Pago confirmado — emparejado con la transferencia">✓</span>`;
    } else if (v.pago_probable) {
      pagoHtml = `<span class="venc-pago-probable" title="Pago probable — hay un Pago de Tarjeta por el mismo monto cerca del vencimiento, pero no está emparejado. Revisá.">✓</span>`;
    }

    const fullCard = `<div class="venc-card ${cls}">
      <div class="${fuenteCls}">${escHtml(label)}${pagoHtml}</div>
      <div class="venc-fecha">${fechaStr}</div>
      <div class="venc-dias">${diasTxt}</div>
      ${montoHtml}
      ${rg5617Html}
      ${pdfHtml}
      ${proxHtml}
    </div>`;

    // Pagada (✓ verde/amarillo): se usa para el badge del chip.
    const pagada    = !!(v.pago_confirmado || v.pago_probable);
    const chipMonto = arsSum > 0 ? `$ ${_fmtNum(arsSum)}`
                    : usdSum > 0 ? `U$S ${_fmtNum2(usdSum)}` : "";
    vencByFuente[v.fuente] = { label, cls, diasTxt, diasShort, pagada, chipMonto, fullCard };
  });

  // ── Render: una tarjeta por cuenta CC, mostrando SIEMPRE el consumo en vivo ──
  // (suma de egresos del período abierto scrappeada, guardada en cuentas.saldo/
  // saldo_usd). El detalle del último resumen PDF (fecha de cierre/vencimiento)
  // sigue apareciendo al tocar, cuando existe.
  const tarjetas = (_widgetCuentas || []).filter(c => c.cuenta_tipo === "credit_card");
  const order    = tarjetas.map(c => c.fuente);
  // Fallback: fuentes con vencimiento que no tengan cuenta-tarjeta cacheada.
  deduped.forEach(v => { if (!order.includes(v.fuente)) order.push(v.fuente); });

  if (!order.length) { widget.style.display = "none"; return; }
  widget.style.display = "grid";

  widget.innerHTML = order.map(fuente => {
    const cuenta = _cuentaByFuente(fuente);
    const v      = vencByFuente[fuente];
    const nombre = cuenta ? cuenta.nombre : (v ? v.label : fuente);
    const ars    = cuenta ? (cuenta.saldo     || 0) : 0;
    const usd    = cuenta ? (cuenta.saldo_usd || 0) : 0;

    // Monto principal = consumo scrappeado del período abierto.
    let montoHtml;
    if (ars > 0 || usd > 0) {
      const parts = [_saldoChipMonto(ars, "ARS")];
      if (usd > 0) parts.push(_saldoChipMonto(usd, "USD"));
      montoHtml = parts.join(" · ");
    } else if (v && v.chipMonto) {
      // Sin consumo scrappeado todavía → caer al total del resumen PDF (tenue).
      montoHtml = `<span class="venc-chip-pdf">${v.chipMonto}</span>`;
    } else {
      montoHtml = `<span class="venc-chip-empty">—</span>`;
    }

    // Badge de estado del vencimiento (si hay resumen importado).
    let badge = "";
    if (v && v.pagada) {
      badge = `<span class="venc-chip-badge paid">✓ pagada</span>`;
    } else if (v && v.diasShort) {
      badge = `<span class="venc-chip-badge ${v.cls}" title="${escHtml(v.diasTxt)}">${v.diasShort}</span>`;
    }

    const scrape    = _scraperStatusColor(cuenta);
    const scrapeCls = scrape ? ` scrape-${scrape}` : "";
    const stateCls  = v ? (v.pagada ? "paid" : v.cls) : "";
    const detail    = v ? v.fullCard
      : `<div class="venc-card"><div class="venc-fuente">${escHtml(nombre)}</div>
           <div class="venc-dias">Sin resumen PDF importado todavía.</div></div>`;
    const ttl = `Consumo scrappeado del período abierto`
      + (scrape ? ` · ${_scraperStatusTitle(cuenta)}` : "")
      + ` — tap para ver el resumen`;

    return `
    <div class="venc-chipwrap">
      <button class="venc-chip ${stateCls}${scrapeCls}" onclick="toggleVencDetail('${fuente}')"
              title="${escHtml(ttl)}">
        <span class="venc-chip-head">
          <span class="venc-chip-name">💳 ${escHtml(nombre)}</span>${badge}
        </span>
        <span class="venc-chip-monto">${montoHtml}</span>
      </button>
      <div class="venc-detail" id="venc-detail-${fuente}" style="display:none">${detail}</div>
    </div>`;
  }).join("");
}

function toggleVencDetail(fuente) {
  const d = document.getElementById(`venc-detail-${fuente}`);
  if (!d) return;
  d.style.display = d.style.display === "none" ? "" : "none";
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
let _presupTcActual = null;   // TC USD actual (del servidor)
let _presupTcTipo   = "tarjeta";

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
  if (data.tc_actual != null) _presupTcActual = data.tc_actual;
  renderPresupuesto();
  _renderPresupTcRow();
}

function _renderPresupTcRow() {
  const hasUsd = _presupItems.some(it => (it.moneda || "ARS") === "USD");
  const row = document.getElementById("presup-tc-row");
  if (!row) return;
  row.style.display = hasUsd ? "" : "none";
  const valEl = document.getElementById("presup-tc-val");
  if (valEl) valEl.textContent = _presupTcActual ? `$ ${_fmtNum2(_presupTcActual)}` : "—";
  const tipoEl = document.getElementById("presup-tc-tipo");
  if (tipoEl && _presupTcTipo) tipoEl.value = _presupTcTipo;
}

async function loadTcConfig() {
  try {
    const res  = await fetch(`${BASE}/api/config/tc-dolar`);
    const data = await res.json();
    _presupTcTipo   = data.tipo   || "tarjeta";
    _presupTcActual = data.tc     || _presupTcActual;
    _renderPresupTcRow();
  } catch(e) { console.warn("loadTcConfig:", e); }
}

async function saveTcConfig() {
  const tipoEl = document.getElementById("presup-tc-tipo");
  const tipo = tipoEl?.value || "tarjeta";
  const res = await fetch(`${BASE}/api/config/tc-dolar`, {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({tipo}),
  });
  if (res.ok) {
    _presupTcTipo = tipo;
    _presupTcActual = null; // force refetch
    await loadPresupuesto();
    showToast("✓ Tipo de cambio guardado", "ok");
  } else {
    showToast("Error al guardar TC", "err");
  }
}

function renderPresupuesto() {
  const vsActual = _presupVsActual;
  const wrap = document.getElementById("presup-table-wrap");
  if (!vsActual.length && !_presupItems.length) {
    wrap.innerHTML = `<p style="color:#aaa;padding:1rem 0">No hay categorías con gastos ni presupuesto definido. Importá movimientos primero.</p>`;
    return;
  }

  const budgetMap    = {};
  const budgetMoneda = {};
  _presupItems.forEach(it => {
    budgetMap[it.categoria]    = it.monto_mensual;
    budgetMoneda[it.categoria] = it.moneda || "ARS";
  });

  const rawRows = vsActual.length ? vsActual.slice() : _presupItems.map(it => {
    const isUsdItem = (it.moneda || "ARS") === "USD";
    return {
      categoria: it.categoria, presupuesto: it.monto_mensual, gastado: 0,
      diferencia: it.monto_mensual, pct: null,
      parent: _catParentOf[it.categoria] || null,
      tiene_hijos: (_catHierarchy[it.categoria] || []).length > 0,
      ...(isUsdItem ? {moneda_presup: "USD", monto_usd: it.monto_mensual, gastado_usd: 0} : {}),
    };
  });

  // Merge: categorías agregadas al presupuesto que todavía no tienen gasto (no
  // están en vs_actual) deben aparecer igual, anidadas bajo su padre si son
  // subcategoría. Sin esto, agregar una categoría/subcategoría sin gasto no se ve.
  const _present = new Set(rawRows.map(r => r.categoria));
  _presupItems.forEach(it => {
    if (_present.has(it.categoria)) return;
    const _isUsd = (it.moneda || "ARS") === "USD";
    rawRows.push({
      categoria: it.categoria, presupuesto: it.monto_mensual, gastado: 0,
      diferencia: it.monto_mensual, pct: null,
      parent: _catParentOf[it.categoria] || null,
      tiene_hijos: (_catHierarchy[it.categoria] || []).length > 0,
      ...(_isUsd ? {moneda_presup: "USD", monto_usd: it.monto_mensual, gastado_usd: 0} : {}),
    });
    _present.add(it.categoria);
  });
  // Asegurar la fila del padre de toda subcategoría mostrada, para que anide
  // (aunque el padre no tenga gasto ni presupuesto propio).
  rawRows.slice().forEach(r => {
    const par = r.parent;
    if (par && !_present.has(par)) {
      rawRows.push({
        categoria: par, presupuesto: 0, gastado: 0, diferencia: 0, pct: null,
        parent: _catParentOf[par] || null, tiene_hijos: true,
      });
      _present.add(par);
    }
  });

  // Build tree: group children under their parents
  const byParent = {};
  rawRows.forEach(r => {
    if (r.parent) (byParent[r.parent] = byParent[r.parent] || []).push(r);
  });

  // Sort top-level rows by user-chosen column
  const sc = _presupSort.col, sd = _presupSort.dir;
  const topLevel = rawRows.filter(r => !r.parent);
  topLevel.sort((a, b) => {
    if (sc === "categoria") return sd * (a.categoria||"").localeCompare(b.categoria||"", "es");
    return sd * ((a[sc]||0) - (b[sc]||0));
  });

  // Flatten: each top-level row followed by its children (always sorted by gastado desc)
  const rows = [];
  topLevel.forEach(r => {
    rows.push({...r, _indent: false});
    const kids = (byParent[r.categoria] || []).slice().sort((a, b) => (b.gastado||0) - (a.gastado||0));
    kids.forEach(c => rows.push({...c, _indent: true}));
  });
  // Orphans: have a parent but parent not in this result — show flat
  const seen = new Set(rows.map(r => r.categoria));
  rawRows.filter(r => !seen.has(r.categoria))
         .sort((a, b) => (b.gastado||0) - (a.gastado||0))
         .forEach(r => rows.push({...r, _indent: false}));

  // Totals: skip indented (child) rows to avoid double-counting
  // presupuesto y gastado ya están en ARS (las filas USD tienen su equivalente convertido)
  let totalPresup = 0, totalGastado = 0;
  let totalPresupUsd = 0, totalGastadoUsd = 0;
  const hasUsdRows = rows.some(r => r.moneda_presup === "USD");
  rows.filter(r => !r._indent).forEach(r => {
    totalPresup  += r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.categoria] || 0);
    totalGastado += r.gastado || 0;
    if (r.moneda_presup === "USD") {
      totalPresupUsd  += r.monto_usd   || 0;
      totalGastadoUsd += r.gastado_usd || 0;
    }
  });
  const totalDiff   = totalPresup - totalGastado;
  const totalPct    = totalPresup > 0 ? Math.round(totalGastado / totalPresup * 100) : 0;
  const totalBarCls = totalPct >= 100 ? "over" : totalPct >= 80 ? "warn" : "";

  const tcNote = hasUsdRows && _presupTcActual
    ? `<span style="color:#888;font-size:.8rem">TC ${_presupTcTipo}: $${_fmtNum2(_presupTcActual)} · USD presup: U$D ${_fmtNum2(totalPresupUsd)} · USD real: U$D ${_fmtNum2(totalGastadoUsd)}</span>`
    : "";
  const summaryHtml = vsActual.length ? `
    <div class="presup-summary">
      <span>Presupuestado: <strong>${_fmtNum2(totalPresup)}</strong></span>
      <span>Gastado: <strong>${_fmtNum2(totalGastado)}</strong></span>
      <span class="${totalDiff >= 0 ? "presup-diff-pos" : "presup-diff-neg"}">
        Diferencia: <strong>${totalDiff >= 0 ? "+" : ""}${_fmtNum2(totalDiff)}</strong>
      </span>
      ${totalPresup > 0 ? `<span style="color:#888">${totalPct}% utilizado</span>` : ""}
      ${tcNote}
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
          const isUsd   = r.moneda_presup === "USD";
          const budget  = r.presupuesto > 0 ? r.presupuesto : (budgetMap[r.categoria] || 0);
          const pct     = budget > 0 ? Math.round(r.gastado / budget * 100) : 0;
          const barW    = Math.min(pct, 100);
          const barCls  = pct >= 100 ? "over" : pct >= 80 ? "warn" : "";
          const diffCls = r.diferencia >= 0 ? "presup-diff-pos" : "presup-diff-neg";
          const nameCss = r._indent
            ? "style=\"padding-left:1.6rem;color:var(--color-cat-child)\""
            : "";
          const catCaret = r.tiene_hijos
            ? `<span class="cat-caret" style="color:#999;font-size:.75rem;margin-right:.25rem">▸</span>`
            : `<span style="display:inline-block;width:.9rem"></span>`;
          const catName = r.tiene_hijos
            ? `<strong style="color:var(--color-cat-parent)">${escHtml(r.categoria)}</strong>`
            : escHtml(r.categoria);
          const prefix  = r._indent ? "└ " : "";
          const usdBadge = isUsd
            ? `<span class="presup-usd-badge">USD</span>`
            : "";
          // Moneda dropdown para categorías hoja (permite cambiar ARS↔USD)
          const _monedaItem = _presupItems.find(it => it.categoria === r.categoria);
          const _monedaCur  = _monedaItem ? (_monedaItem.moneda || "ARS") : (isUsd ? "USD" : "ARS");
          const monedaSel   = !r.tiene_hijos
            ? `<select class="presup-moneda-sel" title="Moneda del presupuesto"
                 onchange="updatePresupMoneda('${escHtml(r.categoria)}',this.value)">
                 <option value="ARS"${_monedaCur==="ARS"?" selected":""}>ARS</option>
                 <option value="USD"${_monedaCur==="USD"?" selected":""}>USD</option>
               </select>`
            : "";
          // Budget cell: for USD rows show USD amount + ARS equiv hint
          let budgetCell;
          if (r.tiene_hijos) {
            budgetCell = `<span class="presup-auto-val">${budget > 0 ? _fmtNum2(budget) : "—"}</span><span class="presup-auto-badge">Σ hijos</span>${usdBadge}`;
          } else if (isUsd) {
            const usdVal = r.monto_usd || 0;
            budgetCell = `<span style="display:flex;align-items:center;gap:.3rem;flex-wrap:wrap">
              <input type="text" inputmode="decimal" class="presup-input" data-cat="${escHtml(r.categoria)}"
                     value="${_fmtNum2(usdVal)}"
                     onfocus="this.select()"
                     onchange="updatePresupItem('${escHtml(r.categoria)}',this.value)" />
              ${monedaSel}
              ${budget > 0 && _presupTcActual ? `<span class="presup-usd-hint">≈ $${_fmtNum2(budget)}</span>` : ""}
            </span>`;
          } else {
            budgetCell = `<span style="display:flex;align-items:center;gap:.3rem">
              <input type="text" inputmode="decimal" class="presup-input" data-cat="${escHtml(r.categoria)}"
                     value="${_fmtNum2(budget)}"
                     onfocus="this.select()"
                     onchange="updatePresupItem('${escHtml(r.categoria)}',this.value)" />
              ${monedaSel}
            </span>`;
          }
          // Gastado cell: for USD rows show ARS equiv + raw USD
          const gastadoCell = isUsd && r.gastado_usd
            ? `<span style="font-variant-numeric:tabular-nums">${_fmtNum2(r.gastado)}</span>
               <span class="presup-usd-hint">U$D ${_fmtNum2(r.gastado_usd)}</span>`
            : `<span style="font-variant-numeric:tabular-nums">${_fmtNum2(r.gastado)}</span>`;
          return `<tr${r._indent ? " class=\"presup-child-row\"" : ""}>
            <td ${nameCss}>${prefix}${catCaret}${catName}</td>
            <td>${budgetCell}</td>
            <td>${gastadoCell}</td>
            <td class="${budget > 0 ? diffCls : ""}">
              ${budget > 0 ? (r.diferencia >= 0 ? "+" : "") + _fmtNum2(r.diferencia) : "—"}
            </td>
            <td>
              ${budget > 0 ? `
                <div class="progress-bar-wrap"><div class="progress-bar ${barCls}" style="width:${barW}%"></div></div>
                <span class="presup-pct">${pct}%</span>
              ` : "—"}
            </td>
            <td style="white-space:nowrap">
              ${r.gastado ? `<button class="btn btn-sm presup-jump-btn" title="Ver gastos de esta categoría en la tab Gastos"
                      data-presup-jump="${escHtml(r.categoria)}">🔍</button>` : ""}
              ${!r.tiene_hijos ? `<button class="btn btn-sm btn-danger"
                      onclick="removePresupItem('${escHtml(r.categoria)}')">✕</button>` : ""}
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

  // Wire "↗ ver gastos" buttons (data-attr + .onclick: robusto ante apóstrofos en la categoría)
  wrap.querySelectorAll("[data-presup-jump]").forEach(b => {
    b.onclick = () => jumpToGastosFromPresup(b.dataset.presupJump);
  });
}

// Salta a la tab Gastos filtrando por una categoría del presupuesto + el mes seleccionado.
function jumpToGastosFromPresup(categoria) {
  const presupMes = document.getElementById("presup-mes")?.value || "";
  const mesSel    = document.getElementById("filter-mes");
  if (mesSel && presupMes && [...mesSel.options].some(o => o.value === presupMes)) {
    mesSel.value = presupMes;
  }
  // Filtrar por esta única categoría (sus descendientes se incluyen vía _catFilterParam)
  _sinCat = false;
  _selectedCats.clear();
  _selectedCats.add(categoria);

  // Activar la tab principal Gastos
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
  document.querySelector('.tab[data-tab="gastos"]')?.classList.add("active");
  document.getElementById("tab-gastos")?.classList.add("active");

  // Reflejar la selección en los chips y recargar
  renderCatChips(_catList);
  _syncChipUI();
  _renderSubChips();
  loadGastos();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updatePresupItem(categoria, rawValue) {
  if ((_catHierarchy[categoria] || []).length > 0) return; // parent with children — auto-derived
  const val = parseFloat(rawValue.replace(/\./g,"").replace(",",".")) || 0;
  const existing = _presupItems.find(it => it.categoria === categoria);
  if (existing) existing.monto_mensual = val;
  // Sólo agregar al presupuesto si el usuario escribió un monto > 0. Las
  // categorías que se muestran por tener gastos (input en 0, sin tocar) NO se
  // persisten al presupuesto. Las agregadas con el "+" entran vía addPresupRow.
  else if (val > 0) _presupItems.push({categoria, monto_mensual: val, moneda: "ARS"});
}

function updatePresupMoneda(categoria, moneda) {
  if ((_catHierarchy[categoria] || []).length > 0) return;
  const existing = _presupItems.find(it => it.categoria === categoria);
  if (existing) {
    existing.moneda = moneda;
  } else {
    _presupItems.push({categoria, monto_mensual: 0, moneda});
  }
  renderPresupuesto();
  _renderPresupTcRow();
  _scheduleSavePresup();
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
  // Persistir sólo categorías sin hijos: las que tienen hijos derivan su
  // presupuesto automáticamente de los hijos y no se almacenan en la tabla.
  const items = _presupItems.filter(it => !(_catHierarchy[it.categoria] || []).length);
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
  // Solo categorías/subcategorías EXISTENTES (no texto libre), excluyendo las
  // que ya están en la tabla (con gasto o ya agregadas al presupuesto).
  const shown = new Set([
    ..._presupVsActual.map(r => r.categoria),
    ..._presupItems.map(it => it.categoria),
  ]);
  const opts = [];
  const roots = _catList.filter(c => !_catParentOf[c]).sort((a, b) => a.localeCompare(b, "es"));
  roots.forEach(root => {
    if (!shown.has(root)) opts.push({ value: root, label: root });
    (_catHierarchy[root] || []).slice().sort((a, b) => a.localeCompare(b, "es")).forEach(child => {
      if (!shown.has(child)) opts.push({ value: child, label: `${root} › ${child}` });
    });
  });
  // Categorías que no cuelgan de ninguna raíz conocida (por las dudas).
  _catList.forEach(c => {
    if (!shown.has(c) && !opts.some(o => o.value === c)) opts.push({ value: c, label: c });
  });
  if (!opts.length) { showToast("Todas las categorías ya están en el presupuesto.", "ok"); return; }
  showSelectPrompt("Agregar al presupuesto:", opts, name => {
    if (name && !_presupItems.find(it => it.categoria === name))
      _presupItems.push({ categoria: name, monto_mensual: 0, moneda: "ARS" });
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
              <input type="text" inputmode="decimal" class="presup-u-input" data-usr="${escHtml(r.usuario)}"
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
  const modo      = document.getElementById("cf-forecast-modo")?.value || "regresion";
  const params    = new URLSearchParams({meses, historico, modo});
  if (_forecastExcludes.length > 0) params.set("exclude_cats", _forecastExcludes.join(","));
  const res  = await fetch(`${BASE}/api/stats/forecast?${params}`);
  const data = await res.json();
  _drawForecast(data, modo);
}

function _drawForecast(data, modo) {
  const historical = data.historical || [];
  const forecast   = data.forecast   || [];
  if (!historical.length) return;

  const allMonths = [...historical.map(d => d.mes), ...forecast.map(d => d.mes)];
  const labels    = allMonths.map(_fmtMes);
  const nH        = historical.length;

  const egH  = [...historical.map(d => d.egresos),  ...Array(forecast.length).fill(null)];
  const inH  = [...historical.map(d => d.ingresos), ...Array(forecast.length).fill(null)];
  const egF  = [...Array(nH - 1).fill(null), historical.at(-1).egresos,  ...forecast.map(d => d.egresos)];
  const inF  = [...Array(nH - 1).fill(null), historical.at(-1).ingresos, ...forecast.map(d => d.ingresos)];

  // Breakdown tooltip for presupuesto mode
  const breakdownMap = {};
  if (modo === "presupuesto") {
    forecast.forEach(d => { if (d.breakdown) breakdownMap[d.mes] = d.breakdown; });
  }

  _destroyAndCreate("chart-forecast", {
    type: "line",
    data: { labels, datasets: [
      { label:"Egresos",          data:egH, borderColor:"rgba(220,80,60,1)",   backgroundColor:"rgba(220,80,60,.08)",  borderWidth:2, pointRadius:3, tension:.3, fill:false },
      { label:"Ingresos",         data:inH, borderColor:"rgba(34,180,120,1)",  backgroundColor:"rgba(34,180,120,.08)", borderWidth:2, pointRadius:3, tension:.3, fill:false },
      { label:"Egresos (proy.)",  data:egF, borderColor:"rgba(220,80,60,.55)", backgroundColor:"transparent",          borderWidth:2, pointRadius:3, tension:.3, fill:false, borderDash:[6,4] },
      { label:"Ingresos (proy.)", data:inF, borderColor:"rgba(34,180,120,.55)",backgroundColor:"transparent",          borderWidth:2, pointRadius:3, tension:.3, fill:false, borderDash:[6,4] },
    ]},
    options: {
      responsive:true, maintainAspectRatio:true,
      spanGaps: false,
      plugins:{
        legend:{ position:"top", labels:{ boxWidth:12, font:{size:11} } },
        tooltip:{
          callbacks:{
            label: c => c.raw != null ? ` ${c.dataset.label}: ${_fmtNum(c.raw)}` : null,
            afterBody: items => {
              if (modo !== "presupuesto") return [];
              const mes = allMonths[items[0]?.dataIndex];
              const bd  = breakdownMap[mes];
              if (!bd) return [];
              return [
                `  · Presupuesto: ${_fmtNum(bd.presupuesto)}`,
                `  · Sin presupuesto (hist.): ${_fmtNum(bd.historico_sin_presupuesto)}`,
              ];
            },
          },
        },
      },
      scales:{ y:{ ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v } } },
    },
  });
}

// forecast controls use inline onchange="loadForecast()" — no module-level binding needed

// ── Cuentas tab ───────────────────────────────────────────────────────────────
let _cuentasData = [];

async function loadCuentas() {
  // Cuentas + datos de scrapers + parsers en paralelo
  const [cuentasRes, instRes, typesRes, jobsRes, statusRes, parsersRes] = await Promise.all([
    fetch(`${BASE}/api/cuentas`),
    fetch(`${BASE}/api/scraper-instances`),
    fetch(`${BASE}/api/scraper-types`),
    fetch(`${BASE}/api/scrapers/jobs`),
    fetch(`${BASE}/api/scrapers/status`),
    fetch(`${BASE}/api/parsers`),
  ]);
  _cuentasData     = await cuentasRes.json();
  _scraperInstances = instRes.ok  ? await instRes.json()  : [];
  _scraperTypes     = typesRes.ok ? await typesRes.json() : [];
  window._parsersList = parsersRes.ok ? await parsersRes.json() : [];
  const jobs        = jobsRes.ok  ? await jobsRes.json()  : [];
  // job.id = "scraper_inst_<id>_<dir>" → guardamos next_run por instance_id
  _instanceJobs = {};
  for (const j of jobs) {
    const m = (j.id || "").match(/^scraper_inst_(\d+)_/);
    if (m) _instanceJobs[m[1]] = j.next_run;
  }
  // Statuses para back-compat (instancia default).  Keyed por banco (legacy).
  const statuses    = statusRes.ok ? await statusRes.json() : [];
  _scraperStatuses  = Object.fromEntries(statuses.map(s => [s.fuente, s]));
  _populateFuenteSelects();
  renderCuentas();
}

// Globals nuevos para v0.4.1
let _scraperInstances = [];
let _scraperTypes     = [];
let _instanceJobs     = {};

function _getInstanceById(id) {
  return _scraperInstances.find(i => i.id === id || i.id === Number(id));
}

function renderCuentas() {
  const list = document.getElementById("cuentas-list");
  if (!_cuentasData.length) {
    list.innerHTML = `<p style="color:#aaa;padding:1rem 0">Sin cuentas.</p>`;
    return;
  }
  list.innerHTML = _cuentasData.map((c, i) => _renderCuentaCard(c, i)).join("");
  // Auto-load movements for manual accounts
  _cuentasData.filter(c => c.tipo === "manual").forEach(c => loadMovimientos(c.fuente));
}

function _renderCuentaCard(c, idx = 0) {
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
    ? `<button class="btn btn-sm" title="Ocultar del widget de saldos" onclick="toggleCuentaActiva('${c.fuente}',0)">👁 Widget</button>`
    : `<button class="btn btn-sm" title="Mostrar en el widget de saldos" onclick="toggleCuentaActiva('${c.fuente}',1)">🚫 Widget</button>`;

  const cuentaTipo = c.cuenta_tipo || "bank";
  const tipoSel = `<select class="moneda-sel" title="Tipo de cuenta (afecta matching de transferencias y pagos)"
    onchange="saveCuentaTipo('${c.fuente}',this.value);this.blur()">
    <option value="bank"${cuentaTipo==="bank"?" selected":""}>🏦 Banco</option>
    <option value="credit_card"${cuentaTipo==="credit_card"?" selected":""}>💳 Tarjeta</option>
  </select>`;

  // Saldo edit row (auto only — manual recalculated from movements)
  let editSaldoRow;
  if (isManual) {
    editSaldoRow = `<p class="cuenta-meta" style="padding:.1rem 1rem .5rem;color:#aaa;font-size:.75rem">
      Saldo calculado automáticamente de los movimientos.</p>`;
  } else if (isMulti) {
    editSaldoRow = `
    <div class="saldo-edit-row" id="ce-edit-${c.fuente}" style="display:none;padding:0 1rem .75rem;flex-wrap:wrap">
      <label style="font-size:.8rem;align-self:center">ARS</label>
      <input id="ce-inp-ars-${c.fuente}" type="text" inputmode="decimal" value="${_fmtNum2(c.saldo||0)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <label style="font-size:.8rem;align-self:center">USD</label>
      <input id="ce-inp-usd-${c.fuente}" type="text" inputmode="decimal" value="${_fmtNum2(c.saldo_usd||0)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <button class="btn btn-sm btn-primary" onclick="saveCuentaSaldo('${c.fuente}')">✓</button>
      <button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">❌ Cancelar</button>
    </div>`;
  } else {
    const curVal = isUsd ? (c.saldo_usd||0) : (c.saldo||0);
    editSaldoRow = `
    <div class="saldo-edit-row" id="ce-edit-${c.fuente}" style="display:none;padding:0 1rem .75rem">
      <input id="ce-inp-${c.fuente}" type="text" inputmode="decimal" value="${_fmtNum2(curVal)}" style="width:110px"
             onkeydown="if(event.key==='Enter')saveCuentaSaldo('${c.fuente}')">
      <button class="btn btn-sm btn-primary" onclick="saveCuentaSaldo('${c.fuente}')">✓</button>
      <button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">❌ Cancelar</button>
    </div>`;
  }

  // Acciones — siempre incluye "Eliminar cuenta" (con confirmación que cuenta gastos)
  const actions = isManual
    ? `${widgetBtn}
       <button class="btn btn-sm btn-danger" onclick="deleteCuenta('${c.fuente}')">🗑 Eliminar cuenta</button>`
    : `<button class="btn btn-sm" onclick="toggleCuentaEdit('${c.fuente}')">✏ Editar saldo</button>
       ${widgetBtn}
       <button class="btn btn-sm btn-danger" onclick="deleteCuenta('${c.fuente}')">🗑 Eliminar cuenta</button>`;

  // Movements section (manual accounts only)
  const movsSection = isManual ? `
    <div class="cuenta-movs">
      <div class="cuenta-movs-title">Movimientos</div>
      <div id="movs-list-${c.fuente}"></div>
    </div>` : "";

  // PDF parser inline panel (auto accounts only) — v0.4.4+
  const parserSection = !isManual ? _renderCuentaParserInline(c) : "";

  // Scraper inline panel (auto accounts only) — v0.4.1+
  const scraperSection = !isManual
    ? `<div class="cuenta-scraper-panel" id="cuenta-scraper-${c.fuente}">
         ${_renderCuentaScraperInline(c)}
       </div>`
    : "";

  // Collapsible: defaultea cerrado.  Recordamos preferencia por cuenta en localStorage.
  const stored = localStorage.getItem(`cuenta-expanded-${c.fuente}`);
  const expanded = stored === "1";
  const toggleSym = expanded ? "−" : "+";

  return `
  <div class="cuenta-card${expanded ? ' cuenta-card-expanded' : ''}" id="cuenta-card-${c.fuente}">
    <div class="cuenta-header cuenta-header-clickable" onclick="toggleCuentaExpand('${c.fuente}')">
      <span class="cuenta-reorder" onclick="event.stopPropagation()">
        <button class="cuenta-move-btn" title="Subir" onclick="moveCuenta('${c.fuente}',-1)" ${idx === 0 ? 'disabled' : ''}>▲</button>
        <button class="cuenta-move-btn" title="Bajar" onclick="moveCuenta('${c.fuente}',1)" ${idx === _cuentasData.length - 1 ? 'disabled' : ''}>▼</button>
      </span>
      <button class="cuenta-collapse-btn" id="cuenta-toggle-${c.fuente}"
              title="${expanded ? 'Colapsar' : 'Expandir'}">${toggleSym}</button>
      <span class="cuenta-nombre" title="Click para renombrar"
            onclick="event.stopPropagation();startRenameCuenta('${c.fuente}')">${escHtml(c.nombre)}</span>
      ${badge}
      <span onclick="event.stopPropagation()">${monedaSel}</span>
      <span onclick="event.stopPropagation()" title="Tipo de cuenta (banco o tarjeta de crédito)">${tipoSel}</span>
      ${saldoDisplay}
    </div>
    <div class="cuenta-body" id="cuenta-body-${c.fuente}" style="display:${expanded ? 'block' : 'none'}">
      <div class="cuenta-meta">
        ${c.fecha_actualizacion ? `Actualizado: ${c.fecha_actualizacion}` : "Sin datos"}${!isManual ? ` · <code style="font-size:.75rem">${c.fuente}</code>` : ""}
      </div>
      <div class="cuenta-actions">${actions}</div>
      ${editSaldoRow}
      <div class="cuenta-display-row">
        <label class="cuenta-display-label">🎨 Color badge</label>
        <input type="color" id="cd-col-${c.fuente}" value="${c.color || '#64748b'}"
               oninput="document.getElementById('cd-hex-${c.fuente}').value=this.value">
        <input type="text" id="cd-hex-${c.fuente}" class="ui-hex-input" maxlength="7"
               value="${c.color || ''}" placeholder="#64748b"
               oninput="if(/^#[0-9a-fA-F]{6}$/.test(this.value))document.getElementById('cd-col-${c.fuente}').value=this.value">
        <label class="cuenta-display-label" style="margin-left:.5rem">📛 Nombre corto</label>
        <input type="text" id="cd-sn-${c.fuente}" class="ui-hex-input" maxlength="12"
               value="${escHtml(c.short_name||'')}" placeholder="${escHtml(c.nombre||c.fuente)}">
        <button class="btn btn-sm btn-primary" onclick="saveCuentaDisplay('${c.fuente}')">✓</button>
      </div>
      ${movsSection}
      ${parserSection}
      ${scraperSection}
    </div>
  </div>`;
}

// ── PDF parser inline (cada cuenta auto puede tener un parser asignado) ─────

function _renderCuentaParserInline(c) {
  // Lista de parsers conocidos (cacheo en _parsersList)
  const parsers = window._parsersList || [];
  const cur     = c.parser_type || "";

  const opts = [`<option value="">(sin parser asignado)</option>`];
  for (const p of parsers) {
    const sel = p.key === cur ? " selected" : "";
    opts.push(`<option value="${p.key}"${sel}>${escHtml(p.label)} (${escHtml(p.sub)})</option>`);
  }

  const curParser  = parsers.find(p => p.key === cur);
  const acceptStr  = curParser?.accept || ".pdf";
  const uploadBtn  = cur
    ? `<button class="btn btn-sm" onclick="triggerCuentaUpload('${c.fuente}')">⬆ Subir ${escHtml(curParser?.sub || 'PDF')}</button>`
    : `<span style="font-size:.78rem;color:#94a3b8">Asigná un parser para habilitar el upload</span>`;

  const lastImp  = _lastImportByFuente[c.fuente];
  const lastLine = lastImp
    ? `<span class="parser-card-last" style="font-size:.76rem;color:#64748b">
         Último: ${lastImp.mes_resumen ? _fmtMes(lastImp.mes_resumen) : (lastImp.fecha_import||"").slice(0,10)} · ${lastImp.cantidad} mov.
       </span>`
    : `<span class="parser-card-last parser-card-last-none" style="font-size:.76rem;color:#94a3b8">Sin imports</span>`;

  return `
    <details class="cuenta-parser-details">
      <summary>📄 PDF parser ${cur ? `<span class="parser-current">→ ${escHtml(curParser?.label || cur)}</span>` : `<span style="color:#94a3b8">(no asignado)</span>`} ${lastLine}</summary>
      <div class="cuenta-parser-row">
        <label for="cp-sel-${c.fuente}">Parser:</label>
        <select id="cp-sel-${c.fuente}" onchange="saveCuentaParser('${c.fuente}', this.value)">
          ${opts.join("")}
        </select>
        ${uploadBtn}
        <input type="file" id="cp-file-${c.fuente}" accept="${acceptStr}" style="display:none"
               onchange="onCuentaFileChange('${c.fuente}', this)">
      </div>
      <p class="field-hint" style="margin-top:.4rem">
        Subí el resumen oficial (PDF) o el export (XLSX para MercadoPago) de esta cuenta.
        El parser elegido procesa el archivo y los gastos se guardan con la fuente <code>${escHtml(c.fuente)}</code>.
      </p>
      <span id="cp-msg-${c.fuente}" class="cp-msg"></span>
    </details>`;
}

async function saveCuentaParser(fuente, parserType) {
  try {
    const res = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}/parser`, {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ parser_type: parserType || null }),
    });
    if (!res.ok) throw new Error(await res.text());
    showToast(parserType ? "Parser asignado" : "Parser desasignado", "ok");
    loadCuentas();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
}

function triggerCuentaUpload(fuente) {
  document.getElementById(`cp-file-${fuente}`)?.click();
}

async function onCuentaFileChange(fuente, inputEl) {
  const file = inputEl.files[0];
  inputEl.value = "";
  if (!file) return;

  const msgEl = document.getElementById(`cp-msg-${fuente}`);
  if (msgEl) { msgEl.textContent = "Analizando…"; msgEl.className = "cp-msg"; }

  // Preview reconciliation dry-run before inserting
  try {
    const pvFd = new FormData();
    pvFd.append("file", file);
    const chk = document.getElementById("chk-include-rg5617");
    pvFd.append("include_rg5617_credits", chk && chk.checked ? "true" : "false");
    const pvRes = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}/upload/preview`, {
      method: "POST", body: pvFd,
    });
    if (pvRes.ok) {
      const pvData = await pvRes.json();
      if (!pvData.summary?.skip_modal) {
        showUploadReconciliationModal(pvData, fuente, file, msgEl);
        if (msgEl) { msgEl.textContent = ""; msgEl.className = "cp-msg"; }
        return;
      }
    }
  } catch (_) { /* preview failed — fall through to direct upload */ }

  await _doActualUpload(fuente, file, msgEl);
}

async function _doActualUpload(fuente, file, msgEl) {
  if (msgEl) { msgEl.textContent = "Procesando…"; msgEl.className = "cp-msg"; }
  const fd = new FormData();
  fd.append("file", file);
  const chk = document.getElementById("chk-include-rg5617");
  fd.append("include_rg5617_credits", chk && chk.checked ? "true" : "false");
  try {
    const res = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}/upload`, {
      method: "POST", body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    if (msgEl) {
      msgEl.textContent = `✓ ${data.importados} importados (${data.total_parseados} parseados)`;
      msgEl.className = "cp-msg ok";
    }
    refreshAfterDataChange();
  } catch (e) {
    if (msgEl) { msgEl.textContent = "✗ " + e.message; msgEl.className = "cp-msg err"; }
  }
}

// ── Upload Reconciliation Modal ───────────────────────────────────────────────

let _rcnPending = null;

function showUploadReconciliationModal(data, fuente, file, msgEl) {
  document.getElementById("rcn-modal")?.remove();
  _rcnPending = { fuente, file, msgEl };
  const modal = document.createElement("div");
  modal.id = "rcn-modal";
  modal.className = "modal-backdrop";
  modal.onclick = (ev) => { if (ev.target === modal) closeRcnModal(); };
  modal.innerHTML = _rcnBuildModal(data);
  document.body.appendChild(modal);
}

function closeRcnModal() {
  document.getElementById("rcn-modal")?.remove();
  _rcnPending = null;
}

async function confirmRcnImport() {
  if (!_rcnPending) return;
  const { fuente, file, msgEl } = _rcnPending;
  const orphanIds = [...document.querySelectorAll(".rcn-orphan-chk:checked")]
    .map(c => parseInt(c.value)).filter(Boolean);
  closeRcnModal();
  await _doActualUpload(fuente, file, msgEl);
  if (orphanIds.length > 0) {
    try {
      const dr = await fetch(`${BASE}/api/gastos/scraper-orphans`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: orphanIds }),
      });
      const dd = await dr.json();
      if (msgEl && dr.ok && dd.eliminados > 0) {
        msgEl.textContent += ` · ${dd.eliminados} eliminados`;
      }
      loadGastos();
    } catch (_) { /* orphan delete failed silently */ }
  }
}

function _rcnFmtAmt(monto, moneda) {
  return (moneda === "USD" ? "U$S " : "$") + _fmtNum(Math.abs(+monto || 0));
}

function _rcnBuildModal(data) {
  const { fuente, periodo, pdf_records, scraper_orphans, summary } = data;
  const label = periodo ? `${periodo.desde} – ${periodo.hasta}` : "—";
  const fLabel = _FUENTE_LABEL[fuente] || fuente;

  const highRecs     = pdf_records.filter(r => r.status === "raw_match_high");
  const lowRecs      = pdf_records.filter(r => r.status === "raw_match_low");
  const newRecs      = pdf_records.filter(r => r.status === "new");
  const importedRecs = pdf_records.filter(r => r.status === "already_imported");

  const rowHigh = r => `
    <div class="rcn-row">
      <span class="rcn-col-date">${r.fecha}</span>
      <span class="rcn-col-desc">${escHtml(r.descripcion)}</span>
      <span class="rcn-col-amt">${_rcnFmtAmt(r.monto, r.moneda)}</span>
      <span class="rcn-col-conf">${Math.round((r.match_raw?.confianza||0)*100)}%</span>
    </div>`;

  const rowLow = r => `
    <div class="rcn-pair">
      <div class="rcn-row rcn-row-src">
        <span class="rcn-tag rcn-tag-pdf">PDF</span>
        <span class="rcn-col-date">${r.fecha}</span>
        <span class="rcn-col-desc">${escHtml(r.descripcion)}</span>
        <span class="rcn-col-amt">${_rcnFmtAmt(r.monto, r.moneda)}</span>
      </div>
      <div class="rcn-row rcn-row-scr">
        <span class="rcn-tag rcn-tag-scr">SCR</span>
        <span class="rcn-col-date">${r.match_raw?.fecha||"—"}</span>
        <span class="rcn-col-desc">${escHtml(r.match_raw?.descripcion||"—")}</span>
        <span class="rcn-col-amt">${_rcnFmtAmt(r.match_raw?.monto||0, r.moneda)}</span>
        <span class="rcn-col-conf">${Math.round((r.match_raw?.confianza||0)*100)}%</span>
      </div>
    </div>`;

  const rowNew = r => `
    <div class="rcn-row">
      <span class="rcn-col-date">${r.fecha}</span>
      <span class="rcn-col-desc">${escHtml(r.descripcion)}</span>
      <span class="rcn-col-amt">${_rcnFmtAmt(r.monto, r.moneda)}</span>
    </div>`;

  const rowImported = r => `
    <div class="rcn-row">
      <span class="rcn-col-date">${r.fecha}</span>
      <span class="rcn-col-desc">${escHtml(r.descripcion)}</span>
      <span class="rcn-col-amt">${_rcnFmtAmt(r.monto, r.moneda)}</span>
      <span class="rcn-col-conf" style="color:#dc2626">dup</span>
    </div>`;

  const rowOrphan = g => `
    <div class="rcn-row">
      <input type="checkbox" class="rcn-orphan-chk" value="${g.id}" checked>
      <span class="rcn-col-date">${g.fecha}</span>
      <span class="rcn-col-desc">${escHtml(g.descripcion)}</span>
      <span class="rcn-col-amt">${_rcnFmtAmt(g.monto, g.moneda)}</span>
      ${g.categoria ? `<span class="rcn-col-cat">${escHtml(g.categoria)}</span>` : ""}
    </div>`;

  const sHigh = highRecs.length ? `
    <details class="rcn-section">
      <summary class="rcn-sum rcn-sum-green">
        <span>● Match en scraper</span><span class="rcn-badge">${highRecs.length}</span>
      </summary>
      <div class="rcn-list">${highRecs.map(rowHigh).join("")}</div>
    </details>` : "";

  const sLow = lowRecs.length ? `
    <details class="rcn-section" open>
      <summary class="rcn-sum rcn-sum-yellow">
        <span>⚠ Match bajo — revisar</span><span class="rcn-badge rcn-badge-warn">${lowRecs.length}</span>
      </summary>
      <div class="rcn-list">${lowRecs.map(rowLow).join("")}</div>
    </details>` : "";

  const sNew = newRecs.length ? `
    <details class="rcn-section" open>
      <summary class="rcn-sum rcn-sum-blue">
        <span>◆ Sin match en scraper</span><span class="rcn-badge rcn-badge-new">${newRecs.length}</span>
      </summary>
      <div class="rcn-list">${newRecs.map(rowNew).join("")}</div>
    </details>` : "";

  const sImported = importedRecs.length ? `
    <details class="rcn-section" open>
      <summary class="rcn-sum rcn-sum-red">
        <span>⛔ Ya importados previamente</span><span class="rcn-badge rcn-badge-err">${importedRecs.length}</span>
      </summary>
      <div class="rcn-list">${importedRecs.map(rowImported).join("")}</div>
    </details>` : "";

  const sOrphans = scraper_orphans.length ? `
    <details class="rcn-section" open>
      <summary class="rcn-sum rcn-sum-gray">
        <span>🗑 En scraper sin match en resumen</span><span class="rcn-badge">${scraper_orphans.length}</span>
      </summary>
      <p class="rcn-hint">Auto-importados por el scraper pero no aparecen en el resumen oficial. Los marcados se eliminan al confirmar.</p>
      <div class="rcn-list">${scraper_orphans.map(rowOrphan).join("")}</div>
    </details>` : "";

  return `
    <div class="modal" style="max-width:720px">
      <h3>Conciliación — ${escHtml(fLabel)} · ${escHtml(label)}</h3>
      <p class="modal-hint">${summary.total_pdf} registros en el archivo.</p>
      ${sHigh}${sLow}${sNew}${sImported}${sOrphans}
      <div class="modal-footer">
        <button class="btn" onclick="closeRcnModal()">❌ Cancelar</button>
        <button class="btn btn-primary" onclick="confirmRcnImport()">Confirmar e importar →</button>
      </div>
    </div>`;
}

// ── Toggle collapse/expand de cada cuenta ────────────────────────────────────

function toggleCuentaExpand(fuente) {
  const body  = document.getElementById(`cuenta-body-${fuente}`);
  const card  = document.getElementById(`cuenta-card-${fuente}`);
  const tog   = document.getElementById(`cuenta-toggle-${fuente}`);
  if (!body || !tog) return;
  const isOpen = body.style.display !== "none";
  if (isOpen) {
    body.style.display = "none";
    tog.textContent = "+";
    tog.title = "Expandir";
    card?.classList.remove("cuenta-card-expanded");
    localStorage.setItem(`cuenta-expanded-${fuente}`, "0");
  } else {
    body.style.display = "block";
    tog.textContent = "−";
    tog.title = "Colapsar";
    card?.classList.add("cuenta-card-expanded");
    localStorage.setItem(`cuenta-expanded-${fuente}`, "1");
  }
}

// ── Scraper inline panel en cada cuenta auto (v0.4.1+) ───────────────────────

function _renderCuentaScraperInline(c) {
  // Detalle del scraper para la cuenta `c`.  Si la cuenta tiene scraper_instance_id,
  // mostramos su config inline.  Si no, mostramos solo el combo para asignar.
  const instId = c.scraper_instance_id;
  const inst   = instId ? _getInstanceById(instId) : null;

  // ── Combo de selección de scraper ──────────────────────────────────────────
  const opts = [`<option value="">(sin scraper)</option>`];
  for (const i of _scraperInstances) {
    const sel = (inst && i.id === inst.id) ? " selected" : "";
    opts.push(`<option value="${i.id}"${sel}>${escHtml(i.banco)} — ${escHtml(i.nombre)}</option>`);
  }
  // Opciones "+ Nueva instancia" — una por banco-type disponible
  opts.push(`<option disabled>──────</option>`);
  for (const t of _scraperTypes) {
    opts.push(`<option value="__new__:${t.banco}">+ Nueva instancia ${escHtml(t.nombre)}</option>`);
  }

  const combo = `
    <div class="cuenta-scraper-combo-row">
      <label for="cs-sel-${c.fuente}">Scraper que la alimenta:</label>
      <select id="cs-sel-${c.fuente}" onchange="onCuentaScraperChange('${c.fuente}', this.value)">
        ${opts.join("")}
      </select>
    </div>`;

  if (!inst) {
    return `
      <details class="cuenta-scraper-details">
        <summary>🤖 Scraper</summary>
        ${combo}
        <p style="font-size:.8rem;color:#94a3b8;margin:.5rem 0">
          Esta cuenta no tiene un scraper asignado. Elegí uno del combo, o creá uno nuevo.
        </p>
      </details>`;
  }

  // ── Instancia asignada: render full panel ─────────────────────────────────
  return `
    <details class="cuenta-scraper-details" open>
      <summary>🤖 Scraper — ${escHtml(inst.banco)}: ${escHtml(inst.nombre)} ${_instanceStatusBadge(inst)}</summary>
      ${combo}
      ${_renderInstanceFullPanel(c, inst)}
    </details>`;
}

function _instanceStatusBadge(inst) {
  const map = {
    ok:              { cls: "scraper-status-ok",      txt: "✓ OK" },
    error:           { cls: "scraper-status-error",   txt: "✗ Error" },
    running:         { cls: "scraper-status-running", txt: "⟳ Corriendo" },
    session_expired: { cls: "scraper-status-error",   txt: "⚠ Sesión expirada" },
    idle:            { cls: "scraper-status-idle",    txt: "Sin correr" },
  };
  const b = map[inst.estado] || map.idle;
  return `<span class="scraper-status-badge ${b.cls}">${b.txt}</span>`;
}

function _renderInstanceFullPanel(c, inst) {
  // Type def (campos definitions) for this banco
  const tdef   = _scraperTypes.find(t => t.banco === inst.banco) || { campos: [] };
  const cfg    = inst.config || {};

  // Build fields (similar to scraper-tab card)
  const fieldsHtml = (tdef.campos || []).map(campo => {
    const val    = (cfg[campo.key] || "");
    const hasPwd = campo.type === "password" && cfg[`has_${campo.key}`];
    const hintHtml = campo.hint ? `<span class="field-hint">${escHtml(campo.hint)}</span>` : "";

    if (campo.type === "checkbox") {
      const _defVal = campo.default !== undefined ? campo.default : false;
      const checked = (cfg[campo.key] !== undefined ? cfg[campo.key] : _defVal) ? "checked" : "";
      return `
        <div class="scraper-field scraper-field-checkbox">
          <label>
            <input id="ci-${inst.id}-${campo.key}" type="checkbox" ${checked}>
            ${escHtml(campo.label)}
          </label>
          ${hintHtml}
        </div>`;
    }

    const placeholder = campo.type === "password"
      ? (hasPwd ? "••••••••  (guardada — dejá vacío para no cambiar)" : "Nueva contraseña")
      : (campo.placeholder || "");
    const hasPwdHtml = hasPwd ? `<span class="has-pwd-note">✓ Contraseña guardada</span>` : "";
    const hintShown  = campo.type !== "password" ? hintHtml : "";
    return `
      <div class="scraper-field">
        <label for="ci-${inst.id}-${campo.key}">${escHtml(campo.label)}</label>
        <input id="ci-${inst.id}-${campo.key}"
               type="${campo.type === 'password' ? 'password' : 'text'}"
               value="${campo.type === 'password' ? '' : escHtml(val)}"
               placeholder="${escHtml(placeholder)}"
               autocomplete="${campo.type === 'password' ? 'new-password' : 'off'}">
        ${hintShown}${hasPwdHtml}
      </div>`;
  }).join("");

  // Schedule + nombre + enabled toggle
  const headerRow = `
    <div class="scraper-field-row">
      <div class="scraper-field" style="flex:2 1 200px">
        <label for="ci-${inst.id}-nombre">Nombre</label>
        <input id="ci-${inst.id}-nombre" type="text" value="${escHtml(inst.nombre)}">
      </div>
      <div class="scraper-field" style="flex:1 1 150px">
        <label for="ci-${inst.id}-schedule">Frecuencia</label>
        ${_scheduleSelect(`ci-${inst.id}-schedule`, inst.schedule || tdef.schedule_default)}
      </div>
      <div class="scraper-field scraper-field-checkbox" style="flex:0 0 auto;align-self:end">
        <label>
          <input id="ci-${inst.id}-enabled" type="checkbox" ${inst.enabled ? "checked" : ""}>
          Activa
        </label>
      </div>
    </div>`;

  // Status info (next_run, ultimo_run, last_log)
  const nextRun = _instanceJobs[String(inst.id)];
  const statusInfo = `
    <div class="scraper-status-info">
      ${inst.ultimo_run ? `<span title="Cuándo arrancó el último run">▶ Último intento: ${escHtml(_fmtTs(inst.ultimo_run))}</span>` : ""}
      ${inst.ultimo_ok  ? `<span style="color:#16a34a">✓ Último OK: ${escHtml(_fmtTs(inst.ultimo_ok))}</span>` : ""}
      ${nextRun ? `<span style="color:#2563eb">⏱ Próximo: ${escHtml(new Date(nextRun).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}))}</span>` : ""}
    </div>
    ${inst.error_msg ? `<p style="font-size:.8rem;color:#b91c1c;margin-top:.4rem">Último error: ${escHtml(inst.error_msg)}</p>` : ""}`;

  const logSection = inst.last_log ? `
    <details class="scraper-log-details">
      <summary>
        <span>📋 Detalle del último run</span>
        <button class="btn-copy-log" id="copy-log-btn-inst-${inst.id}"
                onclick="event.stopPropagation();copyScraperLog('inst-${inst.id}')"
                title="Copiar al portapapeles">⎘ Copiar</button>
      </summary>
      <pre class="scraper-log-pre" id="scraper-log-pre-inst-${inst.id}">${escHtml(inst.last_log)}</pre>
    </details>` : "";

  // Movimientos guardados (reusa el endpoint legacy filtrado por la fuente de esta cuenta)
  const movsSection = `
    <details class="scraper-movs-details" id="movs-details-${c.fuente}">
      <summary onclick="loadScraperMovimientos('${c.fuente}')">
        <span>📦 Registros ingresados</span>
        <button class="btn-refresh-movs" id="btn-refresh-movs-${c.fuente}"
                onclick="event.stopPropagation();refreshScraperMovimientos('${c.fuente}')"
                title="Actualizar">↻</button>
      </summary>
      <div id="movs-list-${c.fuente}" class="scraper-movs-list">
        <span style="font-size:.78rem;color:#94a3b8">Abrí para ver los registros.</span>
      </div>
    </details>`;

  const totpBtns = tdef.totp ? `
    <button class="btn btn-sm" onclick="startTotpSetupInst('${inst.banco}', ${inst.id})"
            id="btn-totp-inst-${inst.id}">🔑 Iniciar sesión TOTP</button>` : "";

  const totpArea = tdef.totp ? `
    <div class="scraper-totp-area" id="totp-area-inst-${inst.id}" style="display:none">
      <label>Código de verificación (TOTP / email)</label>
      <p style="font-size:.82rem;color:#92400e;margin-bottom:.5rem">
        Hacé click en "Iniciar sesión TOTP" — el servidor abrirá el browser,
        completará usuario y contraseña y te pedirá el código aquí.
      </p>
      <div class="scraper-totp-row">
        <input id="totp-input-inst-${inst.id}" type="text" maxlength="8"
               placeholder="123456" inputmode="numeric">
        <button class="btn btn-sm btn-primary"
                onclick="submitTotpCodeInst('${inst.banco}', ${inst.id})">Enviar código</button>
      </div>
      <p id="totp-msg-inst-${inst.id}" style="font-size:.8rem;margin-top:.4rem"></p>
    </div>` : "";

  return `
    <div class="scraper-instance-panel" id="cuenta-inst-${c.fuente}">
      ${headerRow}
      <div class="scraper-fields">${fieldsHtml}</div>
      <div class="scraper-actions">
        <button class="btn btn-primary btn-sm" onclick="saveCuentaInstance('${c.fuente}', ${inst.id})">💾 Guardar</button>
        <button class="btn btn-sm" onclick="runCuentaInstance('${c.fuente}', ${inst.id})" id="btn-cuenta-run-${c.fuente}">▶ Ejecutar ahora</button>
        <button class="btn btn-sm" onclick="importUnmatchedInst('${inst.banco}', ${inst.id})"
                id="btn-import-inst-${inst.id}"
                title="Importar a Gastos los registros sin match con PDF">⬆ Importar pendientes</button>
        ${totpBtns}
        <button class="btn btn-sm" style="color:#b91c1c" onclick="deleteScraperSession('${inst.banco}')">🗑 Borrar sesión</button>
        <button class="btn btn-sm" style="color:#b91c1c" onclick="deleteCuentaInstance('${c.fuente}', ${inst.id})">🗑 Eliminar instancia</button>
        <span class="scraper-save-msg" id="cuenta-save-msg-${c.fuente}"></span>
      </div>
      ${totpArea}
      ${statusInfo}
      ${logSection}
      ${movsSection}
    </div>`;
}

// ── Handlers ─────────────────────────────────────────────────────────────────

async function onCuentaScraperChange(fuente, value) {
  // value puede ser: "" (sin scraper), "<id>" (asignar instancia existente),
  //                  "__new__:<banco>" (crear nueva instancia)
  if (value && value.startsWith("__new__:")) {
    const banco = value.split(":")[1];
    await _createInstanceForCuenta(fuente, banco);
    return;
  }
  // Asignar/desasignar instancia existente
  const cuenta = _cuentasData.find(c => c.fuente === fuente);
  let product_key = "main";
  if (value) {
    const inst = _getInstanceById(value);
    if (inst && inst.banco === "bbva") {
      // BBVA: product_key por moneda. Si la cuenta es ARS/USD/EUR, usamos eso.
      const mon = (cuenta?.moneda || "ARS").toUpperCase();
      product_key = ["ARS","USD","EUR"].includes(mon) ? mon : "ARS";
    }
  }
  try {
    const res = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}/scraper`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instance_id: value || null, product_key }),
    });
    if (!res.ok) throw new Error(await res.text());
    showToast(value ? "Scraper asignado" : "Scraper desasignado", "ok");
    loadCuentas();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
}

async function _createInstanceForCuenta(fuente, banco) {
  const cuenta = _cuentasData.find(c => c.fuente === fuente);
  const tdef   = _scraperTypes.find(t => t.banco === banco);
  if (!tdef) { showToast("Banco desconocido", "err"); return; }

  const nombre = prompt(`Nombre para esta instancia de ${tdef.nombre}:\n(ej. "${tdef.nombre} Personal" o "${tdef.nombre} ${cuenta?.nombre || ''}")`,
                        `${tdef.nombre} ${cuenta?.nombre || ''}`.trim());
  if (!nombre) { loadCuentas(); return; }

  // product_key: para BBVA ARS/USD/EUR según moneda de la cuenta; resto "main"
  let product_key = "main";
  if (banco === "bbva") {
    const mon = (cuenta?.moneda || "ARS").toUpperCase();
    product_key = ["ARS","USD","EUR"].includes(mon) ? mon : "ARS";
  }
  try {
    const res = await fetch(`${BASE}/api/scraper-instances`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        banco, nombre,
        config: { enabled: false },   // crear deshabilitada, usuario completa credenciales después
        schedule: tdef.schedule_default || "every:4h",
        enabled: false,
        cuenta_fuente: fuente,
        product_key,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    showToast(`Instancia "${nombre}" creada — completá las credenciales abajo`, "ok");
    await loadCuentas();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
}

async function saveCuentaInstance(fuente, instanceId) {
  const inst = _getInstanceById(instanceId);
  if (!inst) return;
  const tdef = _scraperTypes.find(t => t.banco === inst.banco) || { campos: [] };

  // Recolectar valores del form
  const config = {};
  for (const campo of (tdef.campos || [])) {
    const el = document.getElementById(`ci-${instanceId}-${campo.key}`);
    if (!el) continue;
    config[campo.key] = campo.type === "checkbox" ? el.checked : el.value;
  }
  // enabled toggle (separado de config)
  const enabledEl = document.getElementById(`ci-${instanceId}-enabled`);
  const nombreEl  = document.getElementById(`ci-${instanceId}-nombre`);
  const schedEl   = document.getElementById(`ci-${instanceId}-schedule`);

  const body = {
    nombre: nombreEl?.value || inst.nombre,
    config,
    schedule: schedEl?.value || inst.schedule,
    enabled: enabledEl ? enabledEl.checked : !!inst.enabled,
  };

  const msgEl = document.getElementById(`cuenta-save-msg-${fuente}`);
  if (msgEl) { msgEl.className = "scraper-save-msg"; msgEl.textContent = ""; }
  try {
    const res = await fetch(`${BASE}/api/scraper-instances/${instanceId}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    if (msgEl) { msgEl.className = "scraper-save-msg ok"; msgEl.textContent = "✓ Guardado"; }
    setTimeout(loadCuentas, 600);
  } catch (e) {
    if (msgEl) { msgEl.className = "scraper-save-msg error"; msgEl.textContent = "✗ " + e.message; }
  }
}

async function runCuentaInstance(fuente, instanceId) {
  const btn = document.getElementById(`btn-cuenta-run-${fuente}`);
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Corriendo…"; }
  try {
    const res = await fetch(`${BASE}/api/scraper-instances/${instanceId}/run`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!data.ok) throw new Error(data.error || "Error");
    const imp = data.auto_imported ?? 0;
    showToast(`✓ ${data.movimientos || 0} movimientos · ${imp} importados a Gastos`, "ok");
  } catch (e) {
    showToast("✗ " + e.message, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "▶ Ejecutar ahora"; }
    refreshAfterDataChange();
  }
}

async function deleteCuentaInstance(fuente, instanceId) {
  if (!confirm("¿Eliminar esta instancia de scraper?\nLas cuentas que la usaban quedan sin scraper asignado (no se borra ningún gasto).")) return;
  try {
    const res = await fetch(`${BASE}/api/scraper-instances/${instanceId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    showToast("Instancia eliminada", "ok");
    loadCuentas();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
}

async function importUnmatchedInst(banco, instId) {
  const btn = document.getElementById(`btn-import-inst-${instId}`);
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Importando…"; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/importar-pendientes`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(
        data.imported > 0
          ? `✓ ${data.imported} movimientos importados a Gastos`
          : "Sin movimientos pendientes",
        "ok"
      );
      if (data.imported > 0) loadCuentas();
    } else {
      showToast(`✗ ${data.detail || "Error"}`, "err");
    }
  } catch(e) {
    showToast(`✗ ${e.message}`, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "⬆ Importar pendientes"; }
  }
}

let _totpRequestIdInst = {};

async function startTotpSetupInst(banco, instId) {
  const btn  = document.getElementById(`btn-totp-inst-${instId}`);
  const area = document.getElementById(`totp-area-inst-${instId}`);
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Iniciando…"; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/session-setup`, { method: "POST" });
    const data = await res.json();
    _totpRequestIdInst[instId] = data.request_id;
    if (area) area.style.display = "";
    document.getElementById(`totp-input-inst-${instId}`)?.focus();
  } catch(e) {
    showToast(`✗ ${e.message}`, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🔑 Iniciar sesión TOTP"; }
  }
}

async function submitTotpCodeInst(banco, instId) {
  const code      = document.getElementById(`totp-input-inst-${instId}`)?.value?.trim();
  const requestId = _totpRequestIdInst[instId];
  const msgEl     = document.getElementById(`totp-msg-inst-${instId}`);
  if (!code || !requestId) { if (msgEl) msgEl.textContent = "Ingresá el código primero."; return; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/totp`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ code, request_id: requestId }),
    });
    const data = await res.json();
    if (res.ok) {
      if (msgEl) msgEl.textContent = "✓ Sesión iniciada";
      const area = document.getElementById(`totp-area-inst-${instId}`);
      if (area) area.style.display = "none";
      delete _totpRequestIdInst[instId];
      loadCuentas();
    } else {
      if (msgEl) msgEl.textContent = `✗ ${data.detail || "Error"}`;
    }
  } catch(e) {
    if (msgEl) msgEl.textContent = `✗ ${e.message}`;
  }
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

async function saveCuentaTipo(fuente, cuenta_tipo) {
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({cuenta_tipo}),
  });
  loadCuentas();
  showToast(`Tipo actualizado: ${cuenta_tipo === "credit_card" ? "💳 Tarjeta" : "🏦 Banco"}`, "ok");
}

async function saveCuentaDisplay(fuente) {
  const colorEl = document.getElementById(`cd-col-${fuente}`);
  const hexEl   = document.getElementById(`cd-hex-${fuente}`);
  const snEl    = document.getElementById(`cd-sn-${fuente}`);
  const color     = (hexEl && /^#[0-9a-fA-F]{6}$/.test(hexEl.value)) ? hexEl.value
                  : (colorEl ? colorEl.value : null);
  const short_name = snEl ? snEl.value.trim() : null;
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ color: color || null, short_name: short_name || null }),
  });
  // loadSaldos actualiza _widgetCuentas (caché que usan los badges); debe
  // completar ANTES de loadGastos para que los badges vean el color nuevo.
  await loadSaldos();
  renderCuentas();
  await loadGastos();
  showToast("Apariencia guardada", "ok");
}

async function moveCuenta(fuente, dir) {
  const idx = _cuentasData.findIndex(c => c.fuente === fuente);
  if (idx < 0) return;
  const j = idx + dir;
  if (j < 0 || j >= _cuentasData.length) return;
  // Swap optimista para feedback inmediato
  const arr = _cuentasData.slice();
  [arr[idx], arr[j]] = [arr[j], arr[idx]];
  _cuentasData = arr;
  renderCuentas();
  _populateFuenteSelects();
  try {
    const res = await fetch(`${BASE}/api/cuentas/reorder`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ fuentes: _cuentasData.map(c => c.fuente) }),
    });
    if (!res.ok) throw new Error("reorder falló");
    loadSaldos();   // refleja el nuevo orden en los chips de la home
  } catch (e) {
    showToast("✗ No se pudo guardar el orden", "err");
    loadCuentas();  // resync desde backend
  }
}

async function toggleCuentaActiva(fuente, activa) {
  await fetch(`${BASE}/api/cuentas/${fuente}`, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({activa}),
  });
  loadCuentas(); loadSaldos();
}

async function deleteCuenta(fuente) {
  // Contar gastos para mostrar warning preciso
  let gastosCount = 0;
  try {
    const r = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}/gastos-count`);
    if (r.ok) gastosCount = (await r.json()).gastos || 0;
  } catch (_) {}

  const msg = gastosCount > 0
    ? `¿Eliminar la cuenta "${fuente}" y sus ${gastosCount} gastos asociados?\n\n` +
      `⚠ Esto es irreversible. Los gastos vinculados (y movimientos del scraper si los hay) se borran.\n` +
      `Si la cuenta usa un scraper, la instancia NO se borra (otras cuentas podrían usarla).`
    : `¿Eliminar la cuenta "${fuente}"?\n\nNo tiene gastos asociados.`;
  if (!confirm(msg)) return;

  try {
    const res = await fetch(`${BASE}/api/cuentas/${encodeURIComponent(fuente)}`, {method:"DELETE"});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Error al borrar");
    showToast(`Cuenta eliminada${data.gastos_deleted ? ` (${data.gastos_deleted} gastos)` : ""}`, "ok");
    loadCuentas(); loadSaldos();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
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
  showConfirm("¿Eliminar este gasto? Se elimina junto con su movimiento. Si es un duplicado no vuelve; si es un movimiento real, el scraper podría re-importarlo en la próxima corrida.", async () => {
    const res = await fetch(`${BASE}/api/gastos/${id}`, {method:"DELETE"});
    if (res.ok) { refreshAfterDataChange(); }
    else showToast("No se pudo eliminar el gasto.", "err");
  });
}

document.getElementById("btn-add-cuenta").addEventListener("click", () => openCreateCuentaModal());

function openCreateCuentaModal() {
  // Estado del modal — cerramos cualquier instancia previa
  document.getElementById("create-cuenta-modal")?.remove();

  // Lista de scrapers disponibles (instancias actuales + tipos para crear nuevas)
  const instOpts = (_scraperInstances || []).map(i =>
    `<option value="${i.id}">${escHtml(i.banco)} — ${escHtml(i.nombre)}</option>`
  ).join("");
  const typeOpts = (_scraperTypes || []).map(t =>
    `<option value="__new__:${t.banco}">+ Nueva instancia ${escHtml(t.nombre)}</option>`
  ).join("");

  const modal = document.createElement("div");
  modal.id = "create-cuenta-modal";
  modal.className = "modal-backdrop";
  modal.onclick = (ev) => { if (ev.target === modal) closeCreateCuentaModal(); };
  modal.innerHTML = `
    <div class="modal" style="max-width:480px">
      <h3>Crear nueva cuenta</h3>
      <div class="scraper-field">
        <label for="cc-nombre">Nombre</label>
        <input id="cc-nombre" type="text" placeholder="ej: Efectivo, Cuenta Nación, BBVA Pesos…">
      </div>
      <div class="scraper-field">
        <label>Tipo</label>
        <div style="display:flex;flex-direction:column;gap:.4rem;font-size:.9rem">
          <label style="cursor:pointer">
            <input type="radio" name="cc-tipo" value="manual" checked
                   onchange="_onCuentaTipoChange()">
            <strong>Manual</strong> <span style="color:#94a3b8">— cargo movimientos a mano</span>
          </label>
          <label style="cursor:pointer">
            <input type="radio" name="cc-tipo" value="pdf"
                   onchange="_onCuentaTipoChange()">
            <strong>PDF parser</strong> <span style="color:#94a3b8">— alimentada por PDFs de resumen importados</span>
          </label>
          <label style="cursor:pointer">
            <input type="radio" name="cc-tipo" value="scraper"
                   onchange="_onCuentaTipoChange()">
            <strong>Scraper</strong> <span style="color:#94a3b8">— alimentada por un scraper (login automático)</span>
          </label>
        </div>
      </div>
      <div class="scraper-field">
        <label for="cc-moneda">Moneda</label>
        <select id="cc-moneda">
          <option value="ARS">ARS – pesos</option>
          <option value="USD">USD – dólares</option>
        </select>
      </div>
      <div class="scraper-field" id="cc-scraper-row" style="display:none">
        <label for="cc-scraper">Scraper (opcional)</label>
        <select id="cc-scraper">
          <option value="">(sin scraper — solo PDFs / API)</option>
          ${instOpts ? `<optgroup label="Instancias existentes">${instOpts}</optgroup>` : ""}
          ${typeOpts ? `<optgroup label="Crear nueva instancia">${typeOpts}</optgroup>` : ""}
        </select>
        <span class="field-hint">
          Para BBVA e InvertirOnline el "producto" se asigna por moneda (ARS → Pesos, USD → Dolares):
          podés linkear una cuenta USD a la misma instancia que ya tenés para separar pesos y dólares.
          Si elegís "Nueva instancia", la creo deshabilitada y luego completás credenciales en el panel inline de la cuenta.
        </span>
      </div>
      <div class="modal-footer">
        <button class="btn" onclick="closeCreateCuentaModal()">❌ Cancelar</button>
        <button class="btn btn-primary" onclick="submitCreateCuenta()">Crear cuenta</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  setTimeout(() => document.getElementById("cc-nombre")?.focus(), 50);
}

function closeCreateCuentaModal() {
  document.getElementById("create-cuenta-modal")?.remove();
}

function _onCuentaTipoChange() {
  const tipo = document.querySelector('input[name="cc-tipo"]:checked')?.value;
  const row  = document.getElementById('cc-scraper-row');
  if (row) row.style.display = (tipo === "scraper") ? "block" : "none";
}

async function submitCreateCuenta() {
  const nombre   = (document.getElementById("cc-nombre")?.value || "").trim();
  const tipoSel  = document.querySelector('input[name="cc-tipo"]:checked')?.value || "manual";
  const moneda   = document.getElementById("cc-moneda")?.value || "ARS";
  const scrSel   = document.getElementById("cc-scraper")?.value || "";

  if (!nombre) { showToast("Ingresá un nombre", "err"); return; }

  // Mapeo UI tipo → backend
  //   manual  → tipo=manual
  //   pdf     → tipo=auto, sin scraper
  //   scraper → tipo=auto, con scraper_instance_id
  const backendTipo = (tipoSel === "manual") ? "manual" : "auto";

  let instanceId = null;
  let productKey = "main";

  if (tipoSel === "scraper" && scrSel) {
    if (scrSel.startsWith("__new__:")) {
      // Crear nueva instancia primero
      const banco = scrSel.split(":")[1];
      const tdef  = _scraperTypes.find(t => t.banco === banco);
      const sugg  = `${tdef?.nombre || banco} ${nombre}`.trim();
      const instNombre = prompt(`Nombre para la nueva instancia de ${tdef?.nombre || banco}:`, sugg);
      if (!instNombre) return;   // canceló → abortar todo
      if (banco === "bbva" || banco === "invertironline") {
        productKey = (moneda || "ARS").toUpperCase();
      }
      try {
        const r = await fetch(`${BASE}/api/scraper-instances`, {
          method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({
            banco, nombre: instNombre,
            config: { enabled: false },
            schedule: tdef?.schedule_default || "every:4h",
            enabled: false,
          }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || "Error creando instancia");
        instanceId = data.instance_id;
      } catch (e) {
        showToast("✗ " + e.message, "err");
        return;
      }
    } else {
      // Instancia existente
      instanceId = parseInt(scrSel, 10);
      const inst = _getInstanceById(instanceId);
      if (inst?.banco === "bbva" || inst?.banco === "invertironline") {
        productKey = (moneda || "ARS").toUpperCase();
      }
    }
  }

  const body = { nombre, moneda, tipo: backendTipo };
  if (tipoSel === "scraper" && instanceId) {
    body.scraper_instance_id = instanceId;
    body.scraper_product_key = productKey;
  }

  try {
    const res = await fetch(`${BASE}/api/cuentas`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Error al crear la cuenta");
    const label = (tipoSel === "manual") ? "manual"
                : (tipoSel === "pdf") ? "PDF parser" : "scraper";
    showToast(`Cuenta "${nombre}" (${moneda}, ${label}) creada.`, "ok");
    closeCreateCuentaModal();
    loadCuentas();
    loadSaldos();
  } catch (e) {
    showToast("✗ " + e.message, "err");
  }
}

// ── Personas (Config tab) ─────────────────────────────────────────────────────
let _usuariosConfig = {usuarios: ["Titular","Adicional"], fuente_usuario: {}, reglas_usuario: [], cardholder_usuario: {}};
let _userRules = [];

async function loadUsuarios() {
  const res = await fetch(`${BASE}/api/config/usuarios`);
  _usuariosConfig = await res.json();
  _userRules = (_usuariosConfig.reglas_usuario || []).map(r => ({
    palabras: Array.isArray(r.palabras) ? r.palabras.map(String) : [],
    usuario:  r.usuario || "",
    fuentes:  Array.isArray(r.fuentes) ? r.fuentes : [],
  }));
  _populateUsuarioDropdowns();
  renderUsuarios();
  renderUserRules();
}

function _populateUsuarioDropdowns() {
  // TODO: agregar opción "Sin usuario" (value="__none__") para filtrar gastos
  // sin persona asignada y poder categorizarlos fácilmente desde la tabla.
  ["filter-usuario","cf-usuario","cq-filter-usuario"].forEach(id => {
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

  renderCardholderMap();
}

// Titulares de tarjeta vistos (cacheados tras la 1ra carga de la sección).
let _cardholdersSeen = null;

async function renderCardholderMap() {
  const box = document.getElementById("cardholder-usuario-map");
  if (!box) return;
  const users = _usuariosConfig.usuarios || [];
  const chMap = _usuariosConfig.cardholder_usuario || {};

  // Cargar titulares vistos del backend una sola vez.
  if (_cardholdersSeen === null) {
    try {
      const res = await fetch(`${BASE}/api/config/cardholders`);
      _cardholdersSeen = (await res.json()).cardholders || [];
    } catch { _cardholdersSeen = []; }
  }

  // Unión de titulares vistos + los ya mapeados (por si dejaron de aparecer).
  const titulares = [...new Set([..._cardholdersSeen, ...Object.keys(chMap)])].sort();

  if (titulares.length === 0) {
    box.innerHTML = `<p class="rules-hint" style="margin:0;opacity:.7">
      Todavía no se detectaron titulares. Corré el scraper al menos una vez.</p>`;
    return;
  }

  box.innerHTML = `
    <table class="presup-table" style="max-width:520px">
      <thead><tr><th>Titular</th><th>Persona</th></tr></thead>
      <tbody>
        ${titulares.map(ch => `<tr>
          <td style="font-family:monospace;font-size:.82rem">${escHtml(ch)}</td>
          <td>
            <select class="cardholder-usuario-sel" data-ch="${escHtml(ch)}"
                    onchange="saveCardholderUsuario(this.dataset.ch,this.value)">
              <option value="">— Sin asignar —</option>
              ${users.map(u =>
                `<option value="${escHtml(u)}" ${chMap[ch]===u?"selected":""}>${escHtml(u)}</option>`
              ).join("")}
            </select>
          </td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

async function saveCardholderUsuario(cardholder, usuario) {
  _usuariosConfig.cardholder_usuario = _usuariosConfig.cardholder_usuario || {};
  if (usuario) _usuariosConfig.cardholder_usuario[cardholder] = usuario;
  else         delete _usuariosConfig.cardholder_usuario[cardholder];
  await _saveUsuariosConfig();
  showToast("✓ Guardado", "ok", 1500);
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
  // Propagate rename into cardholder_usuario map
  Object.keys(_usuariosConfig.cardholder_usuario || {}).forEach(ch => {
    if (_usuariosConfig.cardholder_usuario[ch] === oldName)
      _usuariosConfig.cardholder_usuario[ch] = newName;
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

let _dragUserSrcIdx = null;

function renderUserRules() {
  const list = document.getElementById("user-rules-list");
  if (!list) return;
  const users = _usuariosConfig.usuarios || ["Titular", "Adicional"];

  // Duplicate-word map
  const wordMap = {};
  _userRules.forEach((r, i) => r.palabras.forEach(w => {
    const k = w.toLowerCase();
    if (!wordMap[k]) wordMap[k] = [];
    wordMap[k].push(i);
  }));
  const dupes = new Set(Object.entries(wordMap).filter(([, v]) => v.length > 1).map(([k]) => k));

  list.innerHTML = "";
  _userRules.forEach((rule, i) => {
    const card = document.createElement("div");
    card.className = "rule-card";
    card.draggable = true;

    const tagsHtml = rule.palabras.map((w, j) => {
      const isDup = dupes.has(w.toLowerCase());
      return `<span class="tag${isDup ? " tag-dup" : ""}" title="${isDup ? "Esta palabra ya está en otra regla" : ""}">
        <span class="tag-label" title="Doble clic para editar" ondblclick="editUserTag(${i},${j})">${escHtml(w)}</span>
        <button class="tag-x" type="button" onclick="removeUserTag(${i},${j})">×</button>
      </span>`;
    }).join("");

    const userOpts = users.map(u =>
      `<option value="${escHtml(u)}" ${rule.usuario === u ? "selected" : ""}>${escHtml(u)}</option>`
    ).join("");

    card.innerHTML = `
      <div class="rule-header">
        <span class="drag-handle" title="Arrastrar para reordenar">⠿</span>
        <span class="rule-num">#${i + 1}</span>
        <select class="user-rule-sel" data-i="${i}" style="min-width:140px">
          <option value="">— Persona —</option>
          ${userOpts}
        </select>
        ${_buildFuentesPickerHtml(i, rule.fuentes || []).replace(/class="fuentes-picker"/g, 'class="fuentes-picker user-fuentes-picker"')}
        <button type="button" class="btn btn-sm" onclick="openUserRulePreview(${i})">▶ Probar</button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeUserRule(${i})">✕</button>
      </div>
      <div class="rule-tags" id="user-tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input user-tag-input" data-i="${i}"
               placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addUserTag(event,${i})">
      </div>`;
    list.appendChild(card);

    // Drag events
    card.addEventListener("dragstart", e => { _dragUserSrcIdx = i; card.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
    card.addEventListener("dragend",   () => card.classList.remove("dragging"));
    card.addEventListener("dragover",  e => { e.preventDefault(); card.classList.add("drag-over"); });
    card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
    card.addEventListener("drop", e => {
      e.preventDefault(); card.classList.remove("drag-over");
      if (_dragUserSrcIdx === null || _dragUserSrcIdx === i) return;
      _syncUserRules();
      const [moved] = _userRules.splice(_dragUserSrcIdx, 1);
      _userRules.splice(i, 0, moved);
      _dragUserSrcIdx = null;
      renderUserRules(); _scheduleSaveUserRules();
    });

    // Fuentes picker — update summary on change
    const picker = card.querySelector(".user-fuentes-picker");
    if (picker) {
      picker.querySelectorAll(".fuente-chk").forEach(chk => {
        chk.addEventListener("change", () => {
          const checked = [...picker.querySelectorAll(".fuente-chk:checked")].map(c => c.value);
          picker.querySelector(".fuentes-summary").textContent =
            checked.length === 0 ? "Todas las fuentes" : `${checked.length} fuente${checked.length > 1 ? "s" : ""}`;
          _scheduleSaveUserRules();
        });
      });
    }
  });
}

function _syncUserRules() {
  document.querySelectorAll(".user-rule-sel").forEach((sel, i) => {
    if (_userRules[i]) _userRules[i].usuario = sel.value;
  });
  document.querySelectorAll(".user-fuentes-picker").forEach((picker, i) => {
    if (!_userRules[i]) return;
    _userRules[i].fuentes = [...picker.querySelectorAll(".fuente-chk:checked")].map(c => c.value);
  });
}

let _saveUserRulesTimer = null;
function _scheduleSaveUserRules() {
  clearTimeout(_saveUserRulesTimer);
  _saveUserRulesTimer = setTimeout(async () => {
    _syncUserRules();
    const reglas = _userRules
      .filter(r => r.palabras.length > 0 && r.usuario)
      .map(r => ({palabras: r.palabras, usuario: r.usuario, fuentes: r.fuentes || []}));
    const res = await fetch(`${BASE}/api/config/usuarios`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
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
  _userRules.push({palabras: [], usuario: "", fuentes: []});
  renderUserRules();
  const el = document.querySelectorAll(".user-rule-sel").at(-1);
  el?.focus();
  el?.scrollIntoView({behavior: "smooth", block: "nearest"});
});

document.getElementById("btn-export-user-rules")?.addEventListener("click", () => {
  window.location.href = `${BASE}/api/config/usuarios/rules/export`;
});

document.getElementById("btn-export-db")?.addEventListener("click", () => {
  window.location.href = `${BASE}/api/config/export-db`;
});

document.getElementById("btn-export-backup")?.addEventListener("click", () => {
  window.location.href = `${BASE}/api/config/export-backup`;
});

document.getElementById("inp-import-backup")?.addEventListener("change", e => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  showConfirm(
    "⚠️ Restaurar REEMPLAZA todos tus datos actuales por los del backup. No se puede deshacer.",
    async () => {
      const fd = new FormData();
      fd.append("file", file);
      const res  = await fetch(`${BASE}/api/config/import-backup`, {method: "POST", body: fd});
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        showToast(`✓ Backup restaurado (${(data.restaurados || []).join(", ")}). Recargando…`, "ok", 2500);
        setTimeout(() => window.location.reload(), 1800);
      } else {
        showToast(`❌ ${data.detail || "Error al restaurar"}`, "err", 0);
      }
    }
  );
});

document.getElementById("inp-import-user-rules")?.addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res  = await fetch(`${BASE}/api/config/usuarios/rules/import`, {method: "POST", body: fd});
  const data = await res.json();
  if (res.ok) {
    showToast(`✓ ${data.reglas} reglas importadas`, "ok", 3000);
    loadUsuarios();
  } else {
    showToast(`❌ ${data.detail || "Error al importar"}`, "err", 0);
  }
  e.target.value = "";
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
  } finally { btn.disabled = false; btn.textContent = "🔄 Reaplicar a todos"; }
});

// ── Scrapers config ───────────────────────────────────────────────────────────
// Estado local de las credenciales (se carga desde la API, nunca incluye passwords reales)
let _scraperCreds = {};
let _scraperStatuses = {};

let _scraperJobs = {};   // banco → next_run ISO string

async function renderScrapersConfig() {
  const container = document.getElementById("scrapers-config-list");
  if (!container) return;

  // Cargar credenciales, estado y jobs del scheduler en paralelo
  try {
    const [credsRes, statusRes, jobsRes] = await Promise.all([
      fetch(`${BASE}/api/scrapers/credentials`),
      fetch(`${BASE}/api/scrapers/status`),
      fetch(`${BASE}/api/scrapers/jobs`),
    ]);
    _scraperCreds    = credsRes.ok    ? await credsRes.json()    : {};
    const statuses   = statusRes.ok   ? await statusRes.json()   : [];
    _scraperStatuses = Object.fromEntries(statuses.map(s => [s.fuente, s]));
    const jobs       = jobsRes.ok     ? await jobsRes.json()     : [];
    // job.name = "Scraper mercadopago" → clave = "mercadopago"
    _scraperJobs = Object.fromEntries(
      jobs.map(j => [j.name.replace(/^Scraper\s+/i, ""), j.next_run])
    );
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
    const hintHtml = campo.hint
      ? `<span class="field-hint">${escHtml(campo.hint)}</span>` : "";

    if (campo.type === "checkbox") {
      const _defVal = campo.default !== undefined ? campo.default : false;
      const checked = (data[campo.key] !== undefined ? data[campo.key] : _defVal) ? "checked" : "";
      return `
        <div class="scraper-field scraper-field-checkbox">
          <label>
            <input id="scr-${banco}-${campo.key}" type="checkbox" ${checked}>
            ${escHtml(campo.label)}
          </label>
          ${hintHtml}
        </div>`;
    }

    const placeholder = campo.type === "password"
      ? (hasPwd ? "••••••••  (guardada — dejá vacío para no cambiar)" : "Nueva contraseña")
      : (campo.placeholder || "");
    const hasPwdHtml = hasPwd
      ? `<span class="has-pwd-note">✓ Contraseña guardada</span>` : "";
    const hintHtmlFiltered = campo.type !== "password" ? hintHtml : "";
    return `
      <div class="scraper-field">
        <label for="scr-${banco}-${campo.key}">${escHtml(campo.label)}</label>
        <input id="scr-${banco}-${campo.key}"
               type="${campo.type === 'password' ? 'password' : 'text'}"
               value="${campo.type === 'password' ? '' : escHtml(val)}"
               placeholder="${escHtml(placeholder)}"
               autocomplete="${campo.type === 'password' ? 'new-password' : 'off'}">
        ${hintHtmlFiltered}${hasPwdHtml}
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
          <label for="scr-${banco}-schedule">Frecuencia de ejecución</label>
          ${_scheduleSelect(`scr-${banco}-schedule`, data.schedule)}
        </div>
      </div>
      ${totpHtml}
      <div class="scraper-actions">
        <button class="btn btn-primary btn-sm" onclick="saveScraperConfig('${banco}')">
          💾 Guardar
        </button>
        <button class="btn btn-sm" onclick="runScraperNow('${banco}')" id="btn-run-${banco}">
          ▶ Ejecutar ahora
        </button>
        ${data.totp ? `<button class="btn btn-sm" onclick="startTotpSetup('${banco}')" id="btn-totp-${banco}">
          🔑 Iniciar sesión TOTP
        </button>` : ""}
        <button class="btn btn-sm" onclick="importUnmatched('${banco}')" id="btn-import-${banco}"
                title="Importar a Gastos todos los movimientos que no matchearon con PDFs">
          ⬆ Importar pendientes
        </button>
        <button class="btn btn-sm" style="color:#b91c1c" onclick="deleteScraperSession('${banco}')">
          🗑 Borrar sesión
        </button>
        <span class="scraper-save-msg" id="save-msg-${banco}"></span>
      </div>
      ${st.error_msg ? `<p style="font-size:.8rem;color:#b91c1c;margin-top:.5rem">
        Último error: ${escHtml(st.error_msg)}</p>` : ""}
      <div style="font-size:.78rem;color:#888;margin-top:.4rem;display:flex;flex-wrap:wrap;gap:.75rem">
        ${st.ultimo_run ? `<span title="Cuándo arrancó el último run (puede haber sido exitoso o fallido)">▶ Último intento: ${escHtml(_fmtTs(st.ultimo_run))}</span>` : ""}
        ${st.ultimo_ok  ? `<span title="Cuándo finalizó el último run exitoso" style="color:#16a34a">✓ Último OK: ${escHtml(_fmtTs(st.ultimo_ok))}</span>` : ""}
        ${_scraperJobs[banco] ? `<span title="Próximo run programado por el scheduler" style="color:#2563eb">⏱ Próximo run: ${escHtml(new Date(_scraperJobs[banco]).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}))}</span>` : (st.estado !== 'idle' ? "" : `<span style="color:#f59e0b" title="El scheduler no tiene este banco programado — verificá las credenciales">⚠ No programado</span>`)}
      </div>
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
    if (el) body[campo.key] = campo.type === "checkbox" ? el.checked : el.value;
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
      const mov = data.movimientos ?? 0;
      const imp = data.auto_imported ?? 0;
      const msg = imp > 0
        ? `✓ ${banco}: ${mov} scrapeados, ${imp} importados a Gastos`
        : `✓ ${banco}: ${mov} movimientos (${imp} importados)`;
      showToast(msg, "ok");
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

async function importUnmatched(banco) {
  const btn = document.getElementById(`btn-import-${banco}`);
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Importando…"; }
  try {
    const res  = await fetch(`${BASE}/api/scrapers/${banco}/importar-pendientes`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(
        data.imported > 0
          ? `✓ ${data.imported} movimientos importados a Gastos`
          : "Sin movimientos pendientes",
        "ok"
      );
      if (data.imported > 0) {
        // Refrescar la lista de registros y recargar tabla principal si está visible
        const details = document.getElementById(`movs-details-${banco}`);
        if (details) { details.dataset.loaded = "0"; }
        if (typeof loadData === "function") loadData();
      }
    } else {
      showToast(`✗ ${data.detail || "Error"}`, "err");
    }
  } catch(e) {
    showToast(`✗ ${e.message}`, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "⬆ Importar pendientes"; }
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
    const allRows = res.ok ? await res.json() : [];
    // Mostrar todos los estados, incluyendo 'ignored' (sentinel anti-reimport).
    // El usuario puede borrarlos definitivamente desde acá si necesita limpiar la DB.
    const rows = allRows;
    if (!rows.length) {
      el.innerHTML = '<span style="font-size:.78rem;color:#94a3b8">Sin registros guardados.</span>';
      return;
    }
    // Detectar el scraped_at más reciente para marcar entradas "nuevas"
    const latestScrapedAt = rows.reduce((max, r) => r.scraped_at > max ? r.scraped_at : max, "");
    const nowMs = Date.now();

    el.innerHTML = rows.map(r => {
      const b      = _ESTADO_MOV[r.estado] || { cls: "", txt: r.estado };
      const monto  = Math.abs(r.monto).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const prefix = r.moneda === "USD" ? "U$S " : "$ ";
      const neg    = r.monto < 0;

      // Nuevo = mismo scraped_at que la entrada más reciente
      const isNew  = r.scraped_at && r.scraped_at === latestScrapedAt;

      // Timestamp de scraped_at abreviado (va debajo de la fecha)
      let scrapedLabel = "";
      if (r.scraped_at) {
        try {
          const d = new Date(r.scraped_at + (r.scraped_at.endsWith("Z") ? "" : "Z"));
          const diffMin = Math.round((nowMs - d.getTime()) / 60000);
          if (diffMin < 1)         scrapedLabel = "ahora";
          else if (diffMin < 60)   scrapedLabel = `${diffMin}min`;
          else if (diffMin < 1440) scrapedLabel = d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
          else                     scrapedLabel = d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
        } catch(_) {}
      }

      // Fecha cell: fecha principal + scraped_at como sub-línea
      const fechaCell = `<span class="scraper-mov-fecha">
        ${escHtml(r.fecha)}
        ${scrapedLabel ? `<span class="scraper-mov-scraped-time" title="Escaneado: ${escHtml(r.scraped_at || '')}">${escHtml(scrapedLabel)}</span>` : ''}
      </span>`;

      // Subtitle con detalles del raw_data (tipo de pago y operación)
      let rawSubtitle = "";
      try {
        const rd = r.raw_data ? (typeof r.raw_data === "string" ? JSON.parse(r.raw_data) : r.raw_data) : {};
        const typeLabels = {
          "account_money": "Billetera",
          "debit_card":    "Débito",
          "credit_card":   "Crédito",
          "ticket":        "Ticket/cupón",
          "atm":           "ATM",
          "digital_currency": "Cripto",
        };
        const opLabels = {
          "regular_payment":    "Pago",
          "money_transfer":     "Transferencia",
          "recurring_payment":  "Pago recurrente",
          "account_fund":       "Carga de saldo",
          "investment":         "Inversión",
          "pos_payment":        "Pago QR",
          "checkout_pro":       "Compra online",
          "checkout_on":        "Compra online",
          "money_outflows":     "Transf. saliente",
          "money_release":      "Liberación fondos",
          "partition_transfer": "Transf. interna",
        };
        const parts = [];
        if (rd.payment_type_id) parts.push(typeLabels[rd.payment_type_id] || rd.payment_type_id);
        if (rd.operation_type)  parts.push(opLabels[rd.operation_type]  || rd.operation_type);
        if (rd.payment_id)      parts.push(`#${rd.payment_id}`);
        if (parts.length) rawSubtitle = parts.join(" · ");
      } catch(_) {}

      // Desc cell: punto azul "●" si es nuevo, luego descripción + subtitle
      const descCell = `<span class="scraper-mov-desc" title="${escHtml(r.descripcion)}">
        ${isNew ? '<span class="scraper-mov-new-dot" title="Nuevo en el último run">●</span>' : ''}${escHtml(r.descripcion)}${rawSubtitle ? `<span class="scraper-mov-raw-sub">${escHtml(rawSubtitle)}</span>` : ''}
      </span>`;

      const isIgnored   = r.estado === 'ignored';
      // Borrado definitivo (hard delete) — quita la fila y el gasto vinculado.
      // El scraper podrá re-importar si la transacción está dentro del rango
      // de "dias" configurado.  Para bloquear definitivamente: reducir "dias"
      // o usar una regla de categorización.
      const delTitle    = "Borrar definitivamente (también borra el gasto vinculado)";
      const rowExtraClass = isIgnored ? " scraper-mov-row-ignored" : "";
      return `<div class="scraper-mov-row${rowExtraClass}" id="mov-row-${r.id}">
        ${fechaCell}
        ${descCell}
        <span class="scraper-mov-monto${neg ? " neg" : ""}">${prefix}${monto}</span>
        <span class="mov-estado-badge ${b.cls}">${b.txt}</span>
        <button class="btn-del-mov" onclick="deleteMovimientoRaw(${r.id},'${banco}',${isIgnored})" title="${delTitle}">✕</button>
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<span style="font-size:.78rem;color:#b91c1c">Error: ${escHtml(e.message)}</span>`;
  }
}

async function deleteMovimientoRaw(rawId, banco, isIgnored = false) {
  // Hard delete: la fila se elimina completamente, junto con el gasto vinculado
  // si lo había.  El scraper podrá re-importar la transacción si todavía cae
  // en el rango de "dias" configurado (para bloquear: bajar "dias" o usar
  // una regla de categorización que la filtre).
  const msg = "¿Borrar este registro?\nSi tiene un gasto vinculado, también se borrará.\n\n⚠ Si el scraper vuelve a correr y la transacción está dentro del rango de días configurado, la va a re-importar.";
  if (!confirm(msg)) return;
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

// ── Budget vs real home chart ─────────────────────────────────────────────────
let _budgetChart       = null;
let _budgetData        = [];   // top-level only (for chips)
let _budgetAllData     = [];   // full vs_actual (for drill-down)
let _budgetAllCats     = [];
let _budgetSelectedCat = null; // chip seleccionado (null = todas)

function _applyBudChartMode(mode) {
  const card = document.getElementById("bud-chart-card");
  const btn  = document.getElementById("bud-chart-toggle");
  if (!card) return;
  card.classList.remove("chart-card--compact", "chart-card--hidden");
  if (mode === "compact") card.classList.add("chart-card--compact");
  if (mode === "hidden")  card.classList.add("chart-card--hidden");
  if (btn) {
    btn.textContent = _BUD_MODE_LABELS[mode] || "▾";
    btn.title       = _BUD_MODE_TITLES[mode] || "";
  }
}

function toggleBudChartMode() {
  const current = getUiPref("bud_chart_mode");
  const idx     = _BUD_MODE_CYCLE.indexOf(current);
  const next    = _BUD_MODE_CYCLE[(idx + 1) % _BUD_MODE_CYCLE.length];
  const stored  = JSON.parse(localStorage.getItem("ui_prefs") || "{}");
  stored.bud_chart_mode = next;
  localStorage.setItem("ui_prefs", JSON.stringify(stored));
  _applyBudChartMode(next);
}

function _getBudPrefs() {
  return JSON.parse(localStorage.getItem("bud_prefs") || "{}");
}
function _saveBudPrefs(patch) {
  localStorage.setItem("bud_prefs", JSON.stringify({ ..._getBudPrefs(), ...patch }));
}

async function loadBudgetChart() {
  const sel = document.getElementById("bud-mes");
  const mes = sel ? sel.value : "";
  if (!mes) return;
  _saveBudPrefs({ mes });

  let data;
  try {
    const res = await fetch(`${BASE}/api/presupuesto?mes=${mes}`);
    data = await res.json();
  } catch (e) {
    console.error("loadBudgetChart error:", e);
    return;
  }

  const vs = data.vs_actual || [];
  _budgetAllData = vs.filter(d => d.presupuesto > 0 || d.gastado > 0);
  _budgetData    = _budgetAllData.filter(d => !d.parent);   // top-level para chips
  _budgetAllCats = _budgetData.map(d => d.categoria);
  _budgetSelectedCat = null;

  _renderBudCatChips();
  _updateBudChartTitle();
  _drawBudgetChart();
}

// Formato compacto para el título: K/M sin decimales innecesarios.
function _fmtCompactKM(v) {
  const n = Math.abs(+v || 0);
  if (n >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return Math.round(v / 1e3) + "K";
  return String(Math.round(v || 0));
}

// Título del chart: "Presupuesto (xxK) vs Real (xxK)" con los totales del mes
// seleccionado en el combo (suma de categorías top-level, sin doble conteo).
function _updateBudChartTitle() {
  const el = document.getElementById("bud-chart-title-text");
  if (!el) return;
  if (!_budgetData.length) { el.textContent = "Presupuesto vs real"; return; }
  const totalPresup = _budgetData.reduce((s, d) => s + (d.presupuesto || 0), 0);
  const totalReal   = _budgetData.reduce((s, d) => s + (d.gastado    || 0), 0);
  el.textContent = `Presupuesto (${_fmtCompactKM(totalPresup)}) vs Real (${_fmtCompactKM(totalReal)})`;
}

function _renderBudCatChips() {
  const wrap = document.getElementById("bud-cat-chips");
  if (!wrap) return;
  wrap.innerHTML = "";
  const todas = document.createElement("span");
  todas.className = `cat-chip cat-todos${!_budgetSelectedCat ? " active" : ""}`;
  todas.textContent = "Todas";
  todas.onclick = toggleAllBudCats;
  wrap.appendChild(todas);
  _budgetAllCats.forEach(c => {
    const chip = document.createElement("span");
    chip.className = `cat-chip${_budgetSelectedCat === c ? " active" : ""}`;
    chip.textContent = c;
    chip.onclick = () => toggleBudCat(c);
    wrap.appendChild(chip);
  });
}

function toggleAllBudCats() {
  _budgetSelectedCat = null;
  _renderBudCatChips();
  _drawBudgetChart();
}

function toggleBudCat(cat) {
  _budgetSelectedCat = (_budgetSelectedCat === cat) ? null : cat;
  _renderBudCatChips();
  _drawBudgetChart();
}

function _drawBudgetChart() {
  const empty  = document.getElementById("bud-chart-empty");
  const canvas = document.getElementById("budget-chart");
  let visible;
  if (_budgetSelectedCat) {
    const children = _catHierarchy[_budgetSelectedCat] || [];
    if (children.length > 0) {
      const childSet = new Set(children);
      visible = _budgetAllData.filter(d => childSet.has(d.categoria));
    } else {
      visible = _budgetAllData.filter(d => d.categoria === _budgetSelectedCat); // hoja: solo ella misma
    }
    if (!visible.length) visible = _budgetData;   // fallback
  } else {
    visible = _budgetData;
  }

  if (!visible.length) {
    if (_budgetChart) { _budgetChart.destroy(); _budgetChart = null; }
    if (canvas) canvas.style.display = "none";
    if (empty)  empty.style.display  = "";
    return;
  }
  if (canvas) canvas.style.display = "";
  if (empty)  empty.style.display  = "none";

  const labels     = visible.map(d => d.categoria);
  const presup     = visible.map(d => d.presupuesto);
  const gastado    = visible.map(d => d.gastado);
  const _cEgr  = _cssVar("--color-egreso", "#dc2626");   // Real por encima del presupuesto
  const _cReal = _cssVar("--color-real",   "#eab308");   // Real dentro del presupuesto
  const _cPres = _cssVar("--color-presup", "#22c55e");   // barra Presupuesto
  const gastadoBg  = visible.map(d => d.presupuesto > 0 && d.gastado > d.presupuesto ? _cEgr : _cReal);
  const gastadoBdr = gastadoBg;

  const chartData = {
    labels,
    datasets: [
      { label: "Presupuesto", data: presup,  backgroundColor: _cPres,    borderColor: _cPres,    borderWidth: 1, borderRadius: 3 },
      { label: "Real",        data: gastado, backgroundColor: gastadoBg, borderColor: gastadoBdr, borderWidth: 1, borderRadius: 3 },
    ],
  };

  if (_budgetChart) {
    _budgetChart.data = chartData;
    _budgetChart.update();
    return;
  }

  _budgetChart = new Chart(canvas.getContext("2d"), {
    type: "bar",
    data: chartData,
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: window.innerWidth <= 600 ? 1 : 2,
      plugins: {
        legend: { position: "top" },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${_fmtNum(c.raw)}` } },
      },
      scales: {
        x: { ticks: { maxRotation: 45, autoSkip: false } },
        y: { ticks: { callback: v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v } },
      },
    },
  });
}

document.getElementById("bud-mes").addEventListener("change", loadBudgetChart);

// ── Categorías manager ────────────────────────────────────────────────────────

let _categoriasManaged = [];
let _expandedCats      = new Set();
let _showAllKeywords   = false;

async function _fetchRules() {
  const res  = await fetch(`${BASE}/api/rules`);
  const data = await res.json();
  _rules = (data.reglas || []).map(r => ({
    palabras:     Array.isArray(r.palabras) ? r.palabras.map(String) : _patternToWords(r.patron || ""),
    patron:       r.patron || null,
    categoria:    r.categoria || "",
    especial:     !!r.especial,
    solo_egresos: !!r.solo_egresos,
    fuentes:      Array.isArray(r.fuentes) ? r.fuentes : [],
  }));
}

async function loadCategoriasManaged() {
  await _fetchRules();
  const res  = await fetch(`${BASE}/api/categorias/managed`);
  const data = await res.json();
  _categoriasManaged = (data.categorias || []).map(c => ({...c}));
  renderCategoriasManaged();
}

function _isCatExpanded(nombre) { return _showAllKeywords || _expandedCats.has(nombre); }

function toggleCatExpand(nombre) {
  if (_expandedCats.has(nombre)) _expandedCats.delete(nombre); else _expandedCats.add(nombre);
  renderCategoriasManaged();
}

function toggleAllCatsKeywords() {
  _showAllKeywords = !_showAllKeywords;
  const btn = document.getElementById("btn-toggle-all-keywords");
  if (btn) btn.textContent = _showAllKeywords ? "🔑 Cerrar keywords" : "🔑 Ver keywords";
  renderCategoriasManaged();
}

function addKeywordToCat(nombre, kw) {
  kw = kw.trim();
  if (!kw) return;
  let rule = _rules.find(r => r.categoria === nombre);
  if (!rule) {
    rule = {palabras: [], categoria: nombre, especial: false, solo_egresos: false, fuentes: [], patron: null};
    _rules.push(rule);
  }
  if (!rule.palabras.includes(kw)) {
    rule.palabras.push(kw);
    _doSaveRules();
    renderCategoriasManaged();
  }
}

function removeKeywordFromCat(nombre, kw) {
  const rule = _rules.find(r => r.categoria === nombre);
  if (!rule) return;
  rule.palabras = rule.palabras.filter(p => p !== kw);
  _doSaveRules();
  renderCategoriasManaged();
}

function renderCategoriasManaged() {
  const wrap = document.getElementById("categorias-managed-list");
  if (!wrap) return;
  if (!_categoriasManaged.length) {
    wrap.innerHTML = '<p style="color:#aaa;padding:1rem 0">No hay categorías. Importá movimientos o agregá una nueva.</p>';
    return;
  }

  const allNombres = _categoriasManaged.map(c => c.nombre).filter(Boolean).sort((a, b) => a.localeCompare(b, "es"));

  // Separate new (unsaved) items from established tree
  const withIdx  = _categoriasManaged.map((c, i) => ({...c, _i: i}));
  const existing = withIdx.filter(c => !c._new);

  const sortAlpha = arr => arr.slice().sort((a, b) => (a.nombre||"").localeCompare(b.nombre||"", "es"));

  const byParent = {};
  existing.forEach(c => { (byParent[c.parent_nombre || ""] = byParent[c.parent_nombre || ""] || []).push(c); });
  // New (unsaved) items grouped by their target parent so a subcategoría aparece
  // justo debajo de su padre, no al final de toda la lista.
  const newByParent = {};
  withIdx.filter(c => c._new).forEach(c => {
    (newByParent[c.parent_nombre || ""] = newByParent[c.parent_nombre || ""] || []).push(c);
  });
  const parentSet = new Set(existing.map(c => c.parent_nombre).filter(Boolean));

  const ordered = [];
  const pushChildren = (parentName) => {
    sortAlpha(byParent[parentName] || []).forEach(child =>
      ordered.push({...child, _indent: true, _isParent: false}));
    (newByParent[parentName] || []).forEach(child =>
      ordered.push({...child, _indent: true, _isParent: false}));
  };
  sortAlpha(byParent[""] || []).forEach(c => {
    const isParent = parentSet.has(c.nombre) || (newByParent[c.nombre] || []).length > 0;
    ordered.push({...c, _indent: false, _isParent: isParent});
    pushChildren(c.nombre);
  });
  // Categorías nuevas de nivel superior (sin padre) al final.
  (newByParent[""] || []).forEach(c => ordered.push({...c, _indent: false, _isParent: false}));

  // Duplicate keyword map: kw.toLowerCase() → Set of category names that have it
  const kwOwners = new Map();
  _rules.forEach(r => {
    (r.palabras || []).forEach(kw => {
      const k = kw.toLowerCase();
      if (!kwOwners.has(k)) kwOwners.set(k, new Set());
      kwOwners.get(k).add(r.categoria);
    });
  });

  const tableRows = [];
  ordered.forEach(c => {
    const opts = allNombres
      .filter(n => n !== c.nombre)
      .map(n => `<option value="${escHtml(n)}"${c.parent_nombre === n ? " selected" : ""}>${escHtml(n)}</option>`)
      .join("");
    const expanded    = !c._new && _isCatExpanded(c.nombre);
    const rule        = _rules.find(r => r.categoria === c.nombre) || {palabras: [], solo_egresos: false};
    const kwCount     = rule.palabras.length;
    const kwBadge     = kwCount ? `<span style="font-size:.75rem;color:#888;margin-left:.3rem">(${kwCount})</span>` : "";
    const caret       = `<span class="cat-caret" style="color:#999;font-size:.75rem;margin-right:.25rem">${expanded ? "▾" : "▸"}</span>`;
    const nameCell = c._new
      ? `<input class="cat-name-inp" data-i="${c._i}" value="${escHtml(c.nombre||"")}" placeholder="Nombre de categoría" style="width:100%;box-sizing:border-box">`
      : `<span class="cat-name-static" data-nombre="${escHtml(c.nombre)}" title="Click para ver/ocultar keywords · Doble clic para renombrar" style="cursor:pointer">${caret}${
          c._isParent
            ? `<strong style="color:var(--color-cat-parent)">${escHtml(c.nombre)}</strong>`
            : escHtml(c.nombre)
        }</span>`;
    const indentStyle = c._indent ? "padding-left:1.6rem;color:var(--color-cat-child)" : "";
    const prefix      = c._indent ? "└ " : "";

    tableRows.push(`<tr${c._indent ? ' class="presup-child-row"' : ""}>
      <td style="${indentStyle}">${prefix}${nameCell}${!c._new ? kwBadge : ""}</td>
      <td data-lbl="Padre"><select class="cat-parent-sel" data-i="${c._i}" style="width:100%;max-width:220px">
        <option value="">—</option>${opts}
      </select></td>
      <td data-lbl="Especial" style="text-align:center"><input type="checkbox" class="cat-especial-chk" data-i="${c._i}"${c.especial ? " checked" : ""}></td>
      <td style="white-space:nowrap">
        ${(!c._new && !c._indent) ? `<button class="btn btn-sm cat-addsub-btn" data-parent="${escHtml(c.nombre)}" title="Agregar subcategoría">+</button>` : ""}
        ${c._new ? `<button class="btn btn-sm btn-danger" data-del="${c._i}">✕</button>` : ""}
      </td>
    </tr>`);

    if (expanded) {
      const chips = (rule.palabras || []).map(kw => {
        const owners = kwOwners.get(kw.toLowerCase());
        const isDup  = owners && (owners.size > 1 || !owners.has(c.nombre));
        return `<span class="tag${isDup ? " tag-dup" : ""}" title="${isDup ? "Esta palabra ya está en otra categoría" : ""}">
          <span class="tag-label">${escHtml(kw)}</span>
          <button class="tag-x cat-kw-remove" type="button" data-nombre="${escHtml(c.nombre)}" data-kw="${escHtml(kw)}">×</button>
        </span>`;
      }).join("");
      tableRows.push(`<tr class="presup-child-row">
        <td colspan="4" style="padding:.4rem .75rem .6rem ${c._indent ? "2.6rem" : "1rem"};background:#f8f9fa">
          <div style="display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;min-height:1.8rem">
            ${chips || '<span style="color:#bbb;font-size:.82rem">Sin keywords — escribí una y presioná Enter</span>'}
            <input class="cat-kw-input tag-input" data-nombre="${escHtml(c.nombre)}"
                   placeholder="Agregar…" style="min-width:140px;border:1px solid #ccc;border-radius:4px;padding:.2rem .5rem;font-size:.85rem">
          </div>
          <div style="margin-top:.4rem;display:flex;align-items:center;gap:1rem">
            <label style="font-size:.8rem;color:#666;display:inline-flex;align-items:center;gap:.3rem;cursor:pointer">
              <input type="checkbox" class="cat-solo-egresos" data-nombre="${escHtml(c.nombre)}"${rule.solo_egresos ? " checked" : ""}> Solo egresos
            </label>
            <button class="btn btn-sm cat-preview-btn" data-nombre="${escHtml(c.nombre)}">▶ Probar</button>
            <button class="btn btn-sm btn-danger" data-del="${c._i}" style="margin-left:auto">Borrar</button>
          </div>
        </td>
      </tr>`);
    }
  });

  wrap.innerHTML = `<div class="table-wrap"><table class="presup-table">
    <thead><tr>
      <th>Categoría</th><th>Categoría padre</th>
      <th style="text-align:center">Especial</th><th></th>
    </tr></thead>
    <tbody>${tableRows.join("")}</tbody>
  </table></div>`;

  // Parent selector
  wrap.querySelectorAll(".cat-parent-sel").forEach(sel => {
    sel.addEventListener("change", () => {
      _categoriasManaged[+sel.dataset.i].parent_nombre = sel.value || null;
      saveCategoriasManaged();
    });
  });
  // Especial checkbox
  wrap.querySelectorAll(".cat-especial-chk").forEach(chk => {
    chk.addEventListener("change", () => {
      _categoriasManaged[+chk.dataset.i].especial = chk.checked ? 1 : 0;
      saveCategoriasManaged();
    });
  });
  // New category name input
  wrap.querySelectorAll(".cat-name-inp").forEach(inp => {
    inp.addEventListener("input", () => { _categoriasManaged[+inp.dataset.i].nombre = inp.value.trim(); });
    inp.addEventListener("keydown", e => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      _categoriasManaged[+inp.dataset.i].nombre = inp.value.trim();
      saveCategoriasManaged();
    });
  });
  // Delete category
  wrap.querySelectorAll("[data-del]").forEach(btn => {
    btn.addEventListener("click", () => { _categoriasManaged.splice(+btn.dataset.del, 1); renderCategoriasManaged(); });
  });
  // Agregar subcategoría a una categoría padre (se inserta debajo del padre)
  wrap.querySelectorAll(".cat-addsub-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = _categoriasManaged.push({nombre: "", parent_nombre: btn.dataset.parent, especial: 0, _new: true}) - 1;
      renderCategoriasManaged();
      document.querySelector(`.cat-name-inp[data-i="${idx}"]`)?.focus();
    });
  });
  // Remove keyword chip
  wrap.querySelectorAll(".cat-kw-remove").forEach(btn => {
    btn.addEventListener("click", () => removeKeywordFromCat(btn.dataset.nombre, btn.dataset.kw));
  });
  // Add keyword on Enter
  wrap.querySelectorAll(".cat-kw-input").forEach(inp => {
    inp.addEventListener("keydown", e => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      addKeywordToCat(inp.dataset.nombre, inp.value);
      inp.value = "";
    });
  });
  // Solo egresos toggle
  wrap.querySelectorAll(".cat-solo-egresos").forEach(chk => {
    chk.addEventListener("change", () => {
      const rule = _rules.find(r => r.categoria === chk.dataset.nombre);
      if (rule) { rule.solo_egresos = chk.checked; _doSaveRules(); }
    });
  });
  // Probar (dry-run preview)
  wrap.querySelectorAll(".cat-preview-btn").forEach(btn => {
    btn.addEventListener("click", () => openCatPreview(btn.dataset.nombre));
  });
  // Click simple = expandir/colapsar keywords · Doble clic = renombrar
  wrap.querySelectorAll(".cat-name-static").forEach(span => {
    let clickTimer = null;
    span.addEventListener("click", () => {
      // Esperamos por un posible doble clic antes de togglear.
      if (clickTimer) return;
      clickTimer = setTimeout(() => { clickTimer = null; toggleCatExpand(span.dataset.nombre); }, 220);
    });
    span.addEventListener("dblclick", () => {
      if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; }
      const oldNombre = span.dataset.nombre;
      const inp = document.createElement("input");
      inp.value = oldNombre;
      inp.style.cssText = "border:1px solid #ccc;border-radius:4px;padding:.2rem .4rem;font-size:.85rem;width:100%;box-sizing:border-box";
      let saved = false;
      async function doSave() {
        if (saved) return; saved = true;
        const newNombre = inp.value.trim();
        if (!newNombre || newNombre === oldNombre) { loadCategoriasManaged(); return; }
        const res = await fetch(`${BASE}/api/categorias/rename`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({old: oldNombre, new: newNombre}),
        });
        if (res.ok) showToast(`✓ "${oldNombre}" → "${newNombre}"`, "ok", 2500);
        else showToast("Error al renombrar", "err", 0);
        loadCategoriasManaged();
        loadCategorias();  // actualiza los chips de gastos
      }
      inp.addEventListener("keydown", e => {
        if (e.key === "Enter")  { e.preventDefault(); doSave(); }
        if (e.key === "Escape") { saved = true; renderCategoriasManaged(); }
      });
      inp.addEventListener("blur", doSave);
      span.replaceWith(inp);
      inp.focus(); inp.select();
    });
  });
}

async function saveCategoriasManaged() {
  // Sync any name inputs still in the DOM
  document.querySelectorAll(".cat-name-inp").forEach(inp => {
    const i = +inp.dataset.i;
    if (_categoriasManaged[i]) _categoriasManaged[i].nombre = inp.value.trim();
  });
  const items = _categoriasManaged.filter(c => (c.nombre || "").trim());
  const res = await fetch(`${BASE}/api/categorias/managed`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({categorias: items}),
  });
  if (res.ok) {
    showToast("✓ Categorías guardadas", "ok", 2000);
    loadCategoriasManaged();
    refreshAfterDataChange();   // refresca _catList/jerarquía y la grilla de Gastos
  } else {
    showToast("❌ Error al guardar categorías", "err", 0);
  }
}

document.getElementById("btn-reload-categorias").addEventListener("click", loadCategoriasManaged);
document.getElementById("btn-toggle-all-keywords").addEventListener("click", toggleAllCatsKeywords);

document.getElementById("btn-apply-rules-cat").addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-rules-cat");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/rules/apply`, {method: "POST"});
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${data.categorizados} movimientos categorizados`, "ok", 4000);
      refreshAfterDataChange();
    } else {
      showToast(`❌ Error al aplicar reglas: ${data.detail || res.status}`, "err", 0);
    }
  } catch (e) {
    showToast(`❌ ${e.message}`, "err", 0);
  } finally {
    btn.disabled = false; btn.textContent = "🔄 Reaplicar";
  }
});

document.getElementById("btn-export-rules-cat").addEventListener("click", () => {
  window.location.href = `${BASE}/api/rules/export`;
});

document.getElementById("inp-import-rules-cat").addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const res  = await fetch(`${BASE}/api/rules/import`, {method: "POST", body: fd});
  const data = await res.json();
  if (res.ok) { showToast(`✓ ${data.reglas} reglas importadas`, "ok", 3000); loadCategoriasManaged(); }
  else showToast(`❌ ${data.detail || "Error al importar"}`, "err", 0);
  e.target.value = "";
});

document.getElementById("btn-add-categoria").addEventListener("click", () => {
  _categoriasManaged.push({nombre: "", parent_nombre: null, especial: 0, _new: true});
  renderCategoriasManaged();
  const inputs = document.querySelectorAll(".cat-name-inp");
  if (inputs.length) inputs[inputs.length - 1].focus();
});

document.getElementById("btn-save-categorias").addEventListener("click", saveCategoriasManaged);

// ── Cuotas ────────────────────────────────────────────────────────────────────
function _cuotasParams() {
  const p = new URLSearchParams();
  const fuente  = document.getElementById("cq-filter-fuente").value;
  const usuario = document.getElementById("cq-filter-usuario").value;
  const moneda  = document.getElementById("cq-filter-moneda").value;
  const excluir = document.getElementById("cq-chk-excluir-especiales")?.checked;
  if (fuente)  p.set("fuente",  fuente);
  if (usuario) p.set("usuario", usuario);
  if (moneda)  p.set("moneda",  moneda);
  if (excluir) p.set("excluir_especiales", "true");
  return p;
}

async function loadCuotas() {
  const res  = await fetch(`${BASE}/api/cuotas?${_cuotasParams()}`);
  const data = await res.json();
  _renderCuotas(data);
}

function _renderCuotas(data) {
  // ── Resumen top ───────────────────────────────────────────────────────────
  const sumEl = document.getElementById("cuotas-summary");
  const parts = [];
  if (data.proximo_mes_ars) parts.push(`Próximo mes ARS ${_fmtNum2(data.proximo_mes_ars)}`);
  if (data.proximo_mes_usd) parts.push(`Próximo mes USD ${_fmtNum2(data.proximo_mes_usd)}`);
  if (data.total_adeudado_ars) parts.push(`Total adeudado ARS ${_fmtNum2(data.total_adeudado_ars)}`);
  if (data.total_adeudado_usd) parts.push(`Total adeudado USD ${_fmtNum2(data.total_adeudado_usd)}`);
  sumEl.textContent = parts.join(" — ") || "Sin cuotas pendientes";

  // ── Tarjetas de resumen ───────────────────────────────────────────────────
  const statsEl = document.getElementById("cuotas-stats");
  let sh = `<div class="cq-stat-cards">`;
  const _statCard = (label, arsVal, usdVal) => {
    let inner = `<div class="cq-stat-label">${label}</div><div class="cq-stat-val">`;
    if (arsVal) inner += `<span class="cq-ars">ARS ${_fmtNum2(arsVal)}</span>`;
    if (usdVal) inner += `<span class="cq-usd">USD ${_fmtNum2(usdVal)}</span>`;
    if (!arsVal && !usdVal) inner += `<span>—</span>`;
    inner += `</div>`;
    return `<div class="cq-stat-card">${inner}</div>`;
  };
  sh += _statCard("Próximo mes",    data.proximo_mes_ars,    data.proximo_mes_usd);
  sh += _statCard("Total adeudado", data.total_adeudado_ars, data.total_adeudado_usd);
  sh += `</div>`;
  statsEl.innerHTML = sh;

  // ── Tabla por mes ─────────────────────────────────────────────────────────
  const porMesEl = document.getElementById("cuotas-por-mes");
  if (data.por_mes && data.por_mes.length) {
    const allFuenteKeys = [...new Set(
      data.por_mes.flatMap(m => Object.keys(m.ars_por_fuente || {}))
    )];
    const fuentes   = allFuenteKeys.filter(f => f !== "pagos_man").sort();
    const hasPagMan = allFuenteKeys.includes("pagos_man");
    const hasUsd    = data.por_mes.some(m => m.total_usd > 0);

    let th = `<tr><th>Mes</th>`;
    fuentes.forEach(f => { th += `<th>${f.replace(/_/g, " ")}</th>`; });
    if (hasPagMan) th += `<th style="border-left:2px solid #e5e7eb">💰 Pagos</th>`;
    th += `<th>Total ARS</th>`;
    if (hasUsd) th += `<th>Total USD</th>`;
    th += `</tr>`;

    const today_ym = new Date().toISOString().slice(0, 7);
    let rows = "";
    data.por_mes.forEach(pm => {
      const past = pm.mes < today_ym;
      rows += `<tr class="${past ? "cq-past" : ""}">`;
      rows += `<td>${_fmtMes(pm.mes)}</td>`;
      fuentes.forEach(f => {
        const v = (pm.ars_por_fuente || {})[f] || 0;
        rows += `<td class="monto">${v ? _fmtNum2(v) : "—"}</td>`;
      });
      if (hasPagMan) {
        const v = (pm.ars_por_fuente || {}).pagos_man || 0;
        rows += `<td class="monto cq-pagos-man">${v ? _fmtNum2(v) : "—"}</td>`;
      }
      rows += `<td class="monto">${pm.total_ars ? _fmtNum2(pm.total_ars) : "—"}</td>`;
      if (hasUsd) rows += `<td class="monto usd">${pm.total_usd ? _fmtNum2(pm.total_usd) : "—"}</td>`;
      rows += `</tr>`;
    });

    porMesEl.innerHTML = `
      <div class="table-wrap cq-por-mes-wrap">
        <table class="cq-por-mes-table">
          <thead>${th}</thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } else {
    porMesEl.innerHTML = "";
  }

  // ── Tabla de detalle ──────────────────────────────────────────────────────
  const tbody = document.getElementById("cuotas-body");
  tbody.innerHTML = "";

  if (!data.cuotas || !data.cuotas.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#aaa;padding:2rem">Sin cuotas pendientes</td></tr>`;
    return;
  }

  const today_ym2 = new Date().toISOString().slice(0, 7);
  data.cuotas.forEach(c => {
    const nextMes = c.proyeccion?.[0]?.mes || "";
    const past    = nextMes && nextMes < today_ym2;
    const usdCls  = c.moneda === "USD" ? " usd" : "";
    const tr      = document.createElement("tr");
    if (past) tr.className = "cq-past";
    tr.innerHTML = `
      <td title="${escHtml(c.descripcion_original)}">${escHtml(c.descripcion)}</td>
      <td>${_fuenteBadge(c.fuente)}</td>
      <td>${escHtml(c.usuario || "—")}</td>
      <td class="cq-progress">${c.cuota_actual}/${c.total_cuotas}</td>
      <td class="col-moneda">${c.moneda}</td>
      <td class="monto${usdCls}">${_fmtNum2(c.monto_cuota)}</td>
      <td>${c.restantes}</td>
      <td class="monto${usdCls}">${_fmtNum2(c.total_adeudado)}</td>
      <td>${escHtml(c.categoria || "")}</td>`;
    tbody.appendChild(tr);
  });
}

["cq-filter-fuente","cq-filter-usuario","cq-filter-moneda"].forEach(id =>
  document.getElementById(id).addEventListener("change", function() { this.blur(); loadCuotas(); }));
document.getElementById("cq-chk-excluir-especiales").addEventListener("change", loadCuotas);
document.getElementById("btn-cq-load").addEventListener("click", loadCuotas);

// ── Log unificado ────────────────────────────────────────────────────────────
let _logAutorefreshTimer = null;

async function loadLogs() {
  const source = document.getElementById("log-filter-source")?.value || "";
  const level  = document.getElementById("log-filter-level")?.value  || "";
  const params = new URLSearchParams({ limit: 500 });
  if (source) params.set("source", source);
  if (level)  params.set("level",  level);
  const tbody = document.getElementById("log-tbody");
  if (!tbody) return;
  try {
    const res = await fetch(`${BASE}/api/logs?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const r = await res.json();
    const entries = r.entries || [];
    if (!entries.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#888">Sin entradas</td></tr>';
      return;
    }
    // Render newest-first (API returns oldest-first; we reverse)
    const rows = [...entries].reverse().map(e => {
      const lvlCls = e.level === "ERROR" ? "log-err" : e.level === "WARNING" ? "log-warn" : "";
      return `<tr class="${lvlCls}">
        <td style="white-space:nowrap">${escHtml(_fmtLogTs(e.ts))}</td>
        <td><span class="log-level log-${(e.level||"").toLowerCase()}">${escHtml(e.level||"")}</span></td>
        <td style="word-break:break-all">${escHtml(e.source||"")}</td>
        <td style="word-break:break-all;white-space:pre-wrap">${escHtml(e.message||"")}</td>
      </tr>`;
    });
    tbody.innerHTML = rows.join("");
  } catch(err) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--danger)">Error cargando logs: ${escHtml(String(err))}</td></tr>`;
  }
}

async function loadLogSources() {
  try {
    const res = await fetch(`${BASE}/api/logs/sources`);
    if (!res.ok) return;
    const r = await res.json();
    const sel = document.getElementById("log-filter-source");
    if (!sel) return;
    const current = sel.value;
    // Keep the "all" option, add sources
    sel.innerHTML = '<option value="">Todos los orígenes</option>';
    (r.sources || []).forEach(s => {
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === current) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch(_) {}
}

async function clearLogs() {
  if (!confirm("¿Borrar todo el log unificado? Esta acción no se puede deshacer.")) return;
  await fetch(`${BASE}/api/logs`, { method: "DELETE" });
  loadLogs();
}

function toggleLogAutorefresh() {
  const chk = document.getElementById("log-autorefresh");
  if (!chk) return;
  if (chk.checked) {
    _logAutorefreshTimer = setInterval(loadLogs, 30000);
  } else {
    clearInterval(_logAutorefreshTimer);
    _logAutorefreshTimer = null;
  }
}

// Cargar fuentes disponibles al abrir la sección por primera vez
document.querySelector('.cfg-tab[data-cfgtab="log"]')?.addEventListener("click", loadLogSources, { once: true });

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
function showResult(el, msg, ok) { el.textContent = msg; el.className = ok?"ok":"err"; }
