const BASE = window.INGRESS_PREFIX || "";

// ── Palette ───────────────────────────────────────────────────────────────────
const PALETTE = [
  "#6366f1","#22c55e","#f59e0b","#ef4444","#3b82f6",
  "#ec4899","#14b8a6","#f97316","#8b5cf6","#84cc16",
  "#06b6d4","#a855f7","#eab308","#10b981","#f43f5e",
];

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "graficos") loadCharts();
  });
});

// ── User info ─────────────────────────────────────────────────────────────────
fetch(`${BASE}/auth/me`).then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
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

function _populateMonthFilter(meses) {
  ["filter-mes","cf-mes"].forEach(id => {
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
  });
}

loadMonthlyChart();

// ── Charts tab ────────────────────────────────────────────────────────────────
const _charts = {};

function _chartParams() {
  const p = new URLSearchParams();
  const fuente  = document.getElementById("cf-fuente").value;
  const usuario = document.getElementById("cf-usuario").value;
  const mes     = document.getElementById("cf-mes").value;
  const meses   = document.getElementById("cf-meses").value;
  if (fuente)  p.set("fuente",  fuente);
  if (usuario) p.set("usuario", usuario);
  if (mes)     p.set("mes", mes);
  else         p.set("meses", meses);
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

["cf-fuente","cf-usuario","cf-mes","cf-meses"].forEach(id =>
  document.getElementById(id).addEventListener("change", loadCharts));
document.getElementById("btn-refresh-charts").addEventListener("click", loadCharts);

// ── Category slicer ───────────────────────────────────────────────────────────
let _selectedCats = new Set();

async function loadCategorias() {
  const res = await fetch(`${BASE}/api/categorias`);
  const cats = await res.json();
  renderCatChips(cats);
}

function renderCatChips(cats) {
  const container = document.getElementById("cat-chips");
  container.innerHTML = `<span class="cat-chip cat-todos ${_selectedCats.size===0?"active":""}" onclick="toggleAllCats()">Todas</span>`;
  cats.forEach(cat => {
    const chip = document.createElement("span");
    chip.className = `cat-chip ${_selectedCats.has(cat)?"active":""}`;
    chip.textContent = cat;
    chip.onclick = () => toggleCat(cat);
    container.appendChild(chip);
  });
}

function toggleCat(cat) {
  if (_selectedCats.has(cat)) _selectedCats.delete(cat); else _selectedCats.add(cat);
  document.querySelectorAll(".cat-chip:not(.cat-todos)").forEach(c =>
    c.classList.toggle("active", _selectedCats.has(c.textContent)));
  document.querySelector(".cat-todos")?.classList.toggle("active", _selectedCats.size===0);
  loadGastos();
}
function toggleAllCats() {
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
});

// ── Gastos ────────────────────────────────────────────────────────────────────
function _gastosParams() {
  const p = new URLSearchParams();
  const fuente  = document.getElementById("filter-fuente").value;
  const usuario = document.getElementById("filter-usuario").value;
  const mes     = document.getElementById("filter-mes").value;
  if (fuente)  p.set("fuente",  fuente);
  if (usuario) p.set("usuario", usuario);
  if (mes)     p.set("mes",     mes);
  if (_selectedCats.size > 0) p.set("categorias", [..._selectedCats].join(","));
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

  const totalARS = gastos.filter(g=>g.moneda==="ARS").reduce((s,g)=>s+parseFloat(g.monto),0);
  const totalUSD = gastos.filter(g=>g.moneda==="USD").reduce((s,g)=>s+parseFloat(g.monto),0);
  let summary = `${gastos.length} movimientos`;
  if (totalARS) summary += ` — ARS ${_fmtNum2(totalARS)}`;
  if (totalUSD) summary += ` — USD ${_fmtNum2(totalUSD)}`;
  document.getElementById("gastos-summary").textContent = summary;

  gastos.forEach(g => {
    const tr = document.createElement("tr");
    const u = g.usuario || "";
    const isNeg = parseFloat(g.monto) < 0;
    tr.innerHTML = `
      <td>${g.fecha}</td>
      <td>${escHtml(g.descripcion)}</td>
      <td class="monto ${g.moneda==="USD"?"usd":""} ${isNeg?"neg":""}">${_fmtNum2(g.monto)}</td>
      <td class="col-moneda">${g.moneda}</td>
      <td><span class="badge badge-${g.fuente}">${g.fuente.replace("_"," ")}</span></td>
      <td>
        <select class="usuario-select" onchange="saveUsuario(${g.id},this)">
          <option value="" ${!u?"selected":""}>—</option>
          <option value="Seba" ${u==="Seba"?"selected":""}>Seba</option>
          <option value="Mada" ${u==="Mada"?"selected":""}>Mada</option>
        </select>
      </td>
      <td>
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria||"")}"
          title="${g.categoria_fuente?"Fuente: "+g.categoria_fuente:""}" />
      </td>
      <td><button class="btn btn-sm" onclick="saveCategoria(${g.id},this)">✓</button></td>`;

    const catInput = tr.querySelector(".cat-input");
    const saveBtn  = tr.querySelector("td:last-child .btn");
    const orig     = catInput.value;
    catInput.addEventListener("input", () => {
      const changed = catInput.value !== orig;
      catInput.classList.toggle("dirty", changed);
      saveBtn.classList.toggle("btn-dirty", changed);
    });
    catInput.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); saveCategoria(g.id, saveBtn); }
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
  if (res.ok) { input.classList.remove("dirty"); btn.classList.remove("btn-dirty"); }
  btn.textContent = res.ok ? "✓" : "✗";
  setTimeout(() => btn.textContent = "✓", 1500);
}

async function saveUsuario(id, sel) {
  await fetch(`${BASE}/api/gastos/${id}/usuario`, {
    method:"PATCH", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({usuario: sel.value}),
  });
}

["filter-fuente","filter-usuario","filter-mes"].forEach(id =>
  document.getElementById(id).addEventListener("change", loadGastos));
document.getElementById("btn-load").addEventListener("click", loadGastos);
document.getElementById("btn-export").addEventListener("click", () =>
  window.open(`${BASE}/api/gastos/export?${_gastosParams()}`, "_blank"));

loadGastos();

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
  alert(`${data.marcados} movimientos marcados como Transferencia.`);
  loadGastos(); loadMonthlyChart();
}
document.getElementById("transfer-modal").addEventListener("click", function(e) {
  if (e.target === this) closeTransferModal();
});

// ── Delete all ────────────────────────────────────────────────────────────────
document.getElementById("btn-delete-all").addEventListener("click", async () => {
  const fuente = document.getElementById("delete-fuente").value;
  const label  = fuente
    ? document.querySelector(`#delete-fuente option[value="${fuente}"]`).textContent
    : "TODAS las fuentes";
  if (!confirm(`⚠️ Esto elimina los movimientos de: ${label}.\n\n¿Estás seguro?`)) return;
  const url = fuente ? `${BASE}/api/gastos?fuente=${fuente}` : `${BASE}/api/gastos`;
  const res  = await fetch(url, {method:"DELETE"});
  const data = await res.json();
  if (res.ok) {
    alert(`Se eliminaron ${data.eliminados} movimientos.`);
    loadGastos(); loadMonthlyChart(); loadCategorias();
  } else { alert("Error al borrar."); }
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
      loadGastos(); loadMonthlyChart(); loadCategorias();
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
    card.className = "rule-card";
    const tagsHtml = rule.palabras.map((w,j) =>
      `<span class="tag">${escHtml(w)}<button class="tag-x" type="button" onclick="removeTag(${i},${j})">×</button></span>`
    ).join("");
    card.innerHTML = `
      <div class="rule-header">
        <input class="rule-cat" data-i="${i}" value="${escHtml(rule.categoria)}" placeholder="Nombre de categoría">
        <button type="button" class="btn btn-danger btn-sm" onclick="removeRule(${i})">Eliminar</button>
      </div>
      <div class="rule-tags" id="tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input" data-i="${i}" placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addTag(event,${i})">
      </div>`;
    list.appendChild(card);
  });
}

function _syncRules() {
  document.querySelectorAll(".rule-cat").forEach((inp,i) => { if (_rules[i]) _rules[i].categoria = inp.value; });
}
function removeRule(i)    { _syncRules(); _rules.splice(i,1); renderRules(); }
function removeTag(i,j)   { _syncRules(); _rules[i].palabras.splice(j,1); renderRules(); }
function addTag(event,i)  {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const word = event.target.value.trim();
  if (!word) return;
  _syncRules();
  if (!_rules[i].palabras.includes(word)) _rules[i].palabras.push(word);
  renderRules();
  document.querySelectorAll(".tag-input")[i]?.focus();
}

document.getElementById("btn-add-rule").addEventListener("click", () => {
  _syncRules(); _rules.push({palabras:[],categoria:""}); renderRules();
  document.querySelectorAll(".rule-cat").at(-1)?.focus();
});

document.getElementById("btn-save-rules").addEventListener("click", async () => {
  _syncRules();
  const reglas = _rules.filter(r => r.palabras.length > 0 && r.categoria.trim());
  const res = await fetch(`${BASE}/api/rules`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({reglas}),
  });
  alert(res.ok ? "Reglas guardadas." : "Error al guardar.");
});

document.getElementById("btn-apply-rules").addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-rules");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/rules/apply`, {method:"POST"});
    const data = await res.json();
    if (res.ok) { alert(`Reglas aplicadas: ${data.categorizados} movimientos categorizados.`); loadGastos(); loadCategorias(); }
    else alert("Error al aplicar reglas.");
  } finally { btn.disabled = false; btn.textContent = "Reaplicar a todos"; }
});

loadRules();

// ── Match rules ───────────────────────────────────────────────────────────────
const FUENTE_OPTS = `
  <option value="">Cualquier fuente</option>
  <option value="amex">AMEX</option>
  <option value="bbva_mc">BBVA Mastercard</option>
  <option value="bbva_visa">BBVA Visa</option>
  <option value="bbva_cuenta">BBVA Cuenta</option>
  <option value="galicia_mc">Galicia Mastercard</option>
  <option value="mercadopago">MercadoPago</option>`;

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
          <select class="match-fuente-a" data-i="${i}">${FUENTE_OPTS}</select>
        </div>
        <div class="match-arrow-col">↔</div>
        <div class="match-side">
          <div class="match-side-label">Lado B <span class="match-side-hint">(opcional, para emparejado)</span></div>
          <input class="match-patron-b" data-i="${i}" value="${escHtml(r.patron_b||"")}" placeholder="Patrón (vacío = cualquiera)">
          <select class="match-fuente-b" data-i="${i}">${FUENTE_OPTS}</select>
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

function removeMatchRule(i) { _syncMatchRules(); _matchRules.splice(i,1); renderMatchRules(); }

document.getElementById("btn-add-match-rule").addEventListener("click", () => {
  _syncMatchRules();
  _matchRules.push({nombre:"",patron_a:"",fuente_a:"",patron_b:"",fuente_b:"",ventana_dias:3,categoria:"Transferencia"});
  renderMatchRules();
  document.querySelectorAll(".match-nombre").at(-1)?.focus();
});

document.getElementById("btn-save-match-rules").addEventListener("click", async () => {
  _syncMatchRules();
  const res = await fetch(`${BASE}/api/rules/match`, {
    method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({reglas: _matchRules}),
  });
  alert(res.ok ? "Reglas de emparejado guardadas." : "Error al guardar.");
});

document.getElementById("btn-apply-match-rules").addEventListener("click", async () => {
  const btn = document.getElementById("btn-apply-match-rules");
  btn.disabled = true; btn.textContent = "Aplicando…";
  try {
    const res  = await fetch(`${BASE}/api/rules/match/apply`, {method:"POST"});
    const data = await res.json();
    if (res.ok) { alert(`${data.marcados} movimientos marcados.`); loadGastos(); loadCategorias(); }
    else alert("Error al aplicar.");
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
    alert(`${data.marcados} movimientos marcados.`);
    loadGastos(); loadCategorias();
  } finally { if (btn) { btn.disabled = false; btn.textContent = "Aplicar"; } }
}

loadMatchRules();

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function showResult(el, msg, ok) { el.textContent = msg; el.className = ok?"ok":"err"; }
