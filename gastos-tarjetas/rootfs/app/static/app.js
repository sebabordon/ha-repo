const BASE = window.INGRESS_PREFIX || "";

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

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "graficos")    loadCharts();
    if (tab.dataset.tab === "presupuesto") loadPresupuesto();
    if (tab.dataset.tab === "cuentas")     loadCuentas();
    if (tab.dataset.tab === "config")      { loadRules(); loadMatchRules(); renderUsuarios(); renderUserRules(); }
  });
});

// ── Config accordion (⚙ tab) ─────────────────────────────────────────────────
function toggleCfgSection(id) {
  const body  = document.getElementById(`cfg-body-${id}`);
  const arrow = document.getElementById(`cfg-arr-${id}`);
  if (!body) return;
  const open = body.style.display !== "none";
  body.style.display = open ? "none" : "";
  if (arrow) arrow.textContent = open ? "+" : "−";
}

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
  const res = await fetch(`${BASE}/api/gastos/monthly`);
  const data = await res.json();
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
  // Auto-select the most recent month ≤ today when there is no prior selection
  const today = new Date().toISOString().slice(0, 7); // "YYYY-MM"
  const defaultMes = meses.filter(m => m <= today).at(-1) || meses.at(-1) || "";

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
    if (current) sel.value = current;
    else if (defaultMes) sel.value = defaultMes;
  });

  // Trigger initial gastos load now that the month filter is set
  if (!_monthFilterReady) {
    _monthFilterReady = true;
    loadGastos();
  }
}

loadMonthlyChart();
loadCharts();

// ── Charts tab ────────────────────────────────────────────────────────────────
const _charts = {};

function _chartParams() {
  const p = new URLSearchParams();
  const fuente     = document.getElementById("cf-fuente").value;
  const usuario    = document.getElementById("cf-usuario").value;
  const mes        = document.getElementById("cf-mes").value;
  const meses      = document.getElementById("cf-meses").value;
  const moneda     = document.getElementById("cf-moneda").value;
  const excluirEsp = document.getElementById("chk-excluir-especiales-graf")?.checked ?? true;
  if (fuente)  p.set("fuente",  fuente);
  if (usuario) p.set("usuario", usuario);
  if (mes)     p.set("mes", mes);
  else         p.set("meses", meses);
  if (moneda)  p.set("moneda", moneda);
  p.set("excluir_especiales", excluirEsp ? "true" : "false");
  return p;
}

async function loadCharts() {
  const res  = await fetch(`${BASE}/api/stats?${_chartParams()}`);
  const data = await res.json();
  _drawDonut(data.by_category);
  _drawTopDesc(data.top_descriptions);
  _drawMonthlyCat(data.monthly_by_category);
  _drawByFuente(data.by_fuente);
  _drawByUsuario(data.by_usuario);
  loadForecast();
}

function _destroyAndCreate(id, config) {
  if (_charts[id]) _charts[id].destroy();
  _charts[id] = new Chart(document.getElementById(id).getContext("2d"), config);
}

function _drawDonut(data) {
  const top = data.slice(0, 12);
  _destroyAndCreate("chart-by-category", {
    type: "doughnut",
    data: {
      labels:   top.map(d => d.categoria),
      datasets: [{ data: top.map(d => d.total),
        backgroundColor: PALETTE.slice(0, top.length),
        borderWidth: 2, borderColor: "#fff" }],
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: {
        legend: { position: "right", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${_fmtNum(c.raw)}` } },
      },
    },
  });
}

function _drawTopDesc(data) {
  const d = data.slice(0, 15);
  // Fix height on the wrapper BEFORE creating the chart so Chart.js reads
  // a stable size and doesn't enter a grow loop.
  const wrap = document.getElementById("top-desc-wrap");
  wrap.style.height = Math.max(240, d.length * 26 + 40) + "px";

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
  const months = [...new Set(rows.map(r => r.mes))].sort();
  const cats   = [...new Map(
    rows.sort((a,b)=>b.total-a.total).map(r=>[r.categoria, r.total])
  ).entries()].slice(0, 10).map(([c]) => c);

  const datasets = cats.map((cat, i) => ({
    label: cat,
    data:  months.map(m => { const f = rows.find(r=>r.mes===m&&r.categoria===cat); return f?f.total:0; }),
    backgroundColor: PALETTE[i % PALETTE.length],
    borderRadius: 2, borderWidth: 0,
  }));

  _destroyAndCreate("chart-monthly-cat", {
    type: "bar",
    data: { labels: months.map(_fmtMes), datasets },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: {
        legend: { position:"top", labels:{ boxWidth:12, font:{size:11} } },
        tooltip: { mode:"index", callbacks:{ label: c => ` ${c.dataset.label}: ${_fmtNum(c.raw)}` } },
      },
      scales: {
        x: { stacked: true },
        y: { stacked: true, ticks:{ callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v } },
      },
    },
  });
}

function _drawByFuente(data) {
  _destroyAndCreate("chart-by-fuente", {
    type: "bar",
    data: {
      labels:   data.map(d => d.fuente.replace("_"," ")),
      datasets: [{ label:"ARS", data: data.map(d => d.total),
        backgroundColor: data.map((_,i) => PALETTE[i % PALETTE.length]), borderRadius:4 }],
    },
    options: {
      responsive:true, maintainAspectRatio:true,
      plugins:{ legend:{display:false},
        tooltip:{callbacks:{label: c => ` ${_fmtNum(c.raw)}`}} },
      scales:{ y:{ ticks:{callback: v => v>=1000?`${(v/1000).toFixed(0)}k`:v} } },
    },
  });
}

function _drawByUsuario(data) {
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
      plugins:{ legend:{position:"bottom"},
        tooltip:{callbacks:{label: c => ` ${c.label}: ${_fmtNum(c.raw)}`}} },
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

function renderCatChips(cats) {
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

async function loadGastos() {
  const res    = await fetch(`${BASE}/api/gastos?${_gastosParams()}`);
  const gastos = await res.json();
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
          title="${g.categoria_fuente?"Fuente: "+g.categoria_fuente:""}" />
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

    catInput.addEventListener("input", () => {
      const changed = catInput.value !== origCat;
      catInput.classList.toggle("dirty", changed);
      saveBtn.classList.toggle("btn-dirty", changed);
    });
    catInput.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); saveCategoria(g.id, saveBtn); }
    });

    fechaInput.addEventListener("change", () => {
      if (fechaInput.value !== origFecha) saveFecha(g.id, fechaInput);
    });

    tbody.appendChild(tr);
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
async function loadImportaciones() {
  const res  = await fetch(`${BASE}/api/importaciones`);
  const data = await res.json();
  const grp  = document.getElementById("delete-import-optgroup");
  const _FUENTE_LABEL = {
    amex:"AMEX", bbva_mc:"BBVA MC", bbva_visa:"BBVA Visa",
    bbva_cuenta:"BBVA Cuenta", galicia_mc:"Galicia MC", mercadopago:"MercadoPago",
  };

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
    // Restore selection if still valid
    if (current && filterImport.querySelector(`option[value="${current}"]`)) {
      filterImport.value = current;
    }
  }
}

// ── Delete all ────────────────────────────────────────────────────────────────
document.getElementById("btn-delete-all").addEventListener("click", () => {
  const val   = document.getElementById("delete-target").value;
  const label = val
    ? document.querySelector(`#delete-target option[value="${val}"]`)?.textContent || val
    : "TODAS las fuentes";

  showConfirm(`⚠️ Eliminar movimientos: ${label}`, async () => {
    let url;
    if (val.startsWith("fuente:")) {
      url = `${BASE}/api/gastos?fuente=${val.slice(7)}`;
    } else if (val.startsWith("import:")) {
      url = `${BASE}/api/gastos?import_id=${val.slice(7)}`;
    } else {
      url = `${BASE}/api/gastos`;
    }
    const res  = await fetch(url, {method:"DELETE"});
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${data.eliminados} movimientos eliminados`, "ok");
      loadGastos(); loadMonthlyChart(); loadCategorias(); loadImportaciones();
    } else { showToast("Error al borrar", "err", 0); }
  });
});

// ── Upload ────────────────────────────────────────────────────────────────────
document.getElementById("btn-upload").addEventListener("click", async () => {
  const file   = document.getElementById("upload-file").files[0];
  const fuente = document.getElementById("upload-fuente").value;
  const result = document.getElementById("upload-result");
  if (!file) { showResult(result, "Seleccioná un archivo.", false); return; }
  const fd = new FormData(); fd.append("file", file); fd.append("fuente", fuente);
  result.className = ""; result.textContent = "Procesando…";
  try {
    const res  = await fetch(`${BASE}/api/upload`, {method:"POST", body:fd});
    const data = await res.json();
    if (res.ok) {
      showResult(result, `✅ ${data.importados} movimientos importados (${data.total_parseados} parseados).`, true);
      loadGastos(); loadMonthlyChart(); loadCategorias(); loadSaldos(); loadImportaciones();
    } else { showResult(result, `❌ ${data.detail||JSON.stringify(data)}`, false); }
  } catch(e) { showResult(result, `❌ Error de red: ${e}`, false); }
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
  const cls = saldo > 0 ? "positivo" : saldo < 0 ? "negativo" : "";
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

// ── Presupuesto tab ───────────────────────────────────────────────────────────
let _presupItems = [];  // [{categoria, monto_mensual, moneda}]

async function loadPresupuesto() {
  const mes = document.getElementById("presup-mes").value;
  const url = mes ? `${BASE}/api/presupuesto?mes=${mes}` : `${BASE}/api/presupuesto`;
  const res  = await fetch(url);
  const data = await res.json();
  _presupItems = data.items || [];
  renderPresupuesto(data.vs_actual || []);
}

function renderPresupuesto(vsActual) {
  const wrap = document.getElementById("presup-table-wrap");
  if (!vsActual.length && !_presupItems.length) {
    wrap.innerHTML = `<p style="color:#aaa;padding:1rem 0">No hay categorías con gastos ni presupuesto definido. Importá movimientos primero.</p>`;
    return;
  }

  const budgetMap = {};
  _presupItems.forEach(it => { budgetMap[it.categoria] = it.monto_mensual; });

  const rows = vsActual.length ? vsActual : _presupItems.map(it => ({
    categoria: it.categoria, presupuesto: it.monto_mensual, gastado: 0, diferencia: it.monto_mensual, pct: null,
  }));

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

  wrap.innerHTML = summaryHtml + `
    <div class="table-wrap">
    <table class="presup-table">
      <thead>
        <tr>
          <th>Categoría</th>
          <th>Presupuesto</th>
          <th>Gastado</th>
          <th>Diferencia</th>
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
  renderPresupuesto([]);
  _scheduleSavePresup();
}

document.getElementById("presup-mes").addEventListener("change", function() {
  this.blur();
  loadPresupuesto();
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
    renderPresupuesto([]);
    _scheduleSavePresup();
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

document.getElementById("btn-forecast-exclude-add")?.addEventListener("click", async () => {
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
});

_renderForecastExcludes();

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

["cf-forecast-meses","cf-forecast-historico"].forEach(id =>
  document.getElementById(id)?.addEventListener("change", function() { this.blur(); loadForecast(); }));

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

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function showResult(el, msg, ok) { el.textContent = msg; el.className = ok?"ok":"err"; }
