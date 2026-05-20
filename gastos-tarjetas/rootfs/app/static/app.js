const BASE = window.INGRESS_PREFIX || "";

// ── Tab switching ──────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// ── User info ──────────────────────────────────────────────────────────────────

fetch(`${BASE}/auth/me`).then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
});

// ── Monthly chart ──────────────────────────────────────────────────────────────

let _chart = null;

async function loadChart() {
  const res = await fetch(`${BASE}/api/gastos/monthly`);
  const data = await res.json();

  const labels = data.map(d => _fmtMes(d.mes));
  const egresos = data.map(d => d.egresos);
  const ingresos = data.map(d => d.ingresos);

  // Populate month filter while we have the data
  _populateMonthFilter(data.map(d => d.mes));

  const ctx = document.getElementById("monthly-chart").getContext("2d");

  if (_chart) {
    _chart.data.labels = labels;
    _chart.data.datasets[0].data = egresos;
    _chart.data.datasets[1].data = ingresos;
    _chart.update();
    return;
  }

  _chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Egresos",
          data: egresos,
          backgroundColor: "rgba(220, 80, 60, 0.75)",
          borderColor: "rgba(200, 50, 40, 1)",
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: "Ingresos",
          data: ingresos,
          backgroundColor: "rgba(34, 180, 120, 0.75)",
          borderColor: "rgba(20, 140, 90, 1)",
          borderWidth: 1,
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${ctx.raw.toLocaleString("es-AR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
          },
        },
      },
      scales: {
        y: {
          ticks: {
            callback: v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v,
          },
        },
      },
    },
  });
}

function _fmtMes(ym) {
  const [y, m] = ym.split("-");
  const names = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
  return `${names[parseInt(m, 10) - 1]} ${y.slice(2)}`;
}

function _populateMonthFilter(meses) {
  const sel = document.getElementById("filter-mes");
  const current = sel.value;
  // Keep first option ("Todos los meses"), replace the rest
  while (sel.options.length > 1) sel.remove(1);
  meses.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = _fmtMes(m);
    sel.appendChild(opt);
  });
  if (current) sel.value = current;
}

loadChart();

// ── Category slicer ────────────────────────────────────────────────────────────

let _selectedCats = new Set();

async function loadCategorias() {
  const res = await fetch(`${BASE}/api/categorias`);
  const cats = await res.json();
  renderCatChips(cats);
}

function renderCatChips(cats) {
  const container = document.getElementById("cat-chips");
  // Preserve "Todas" chip, rebuild the rest
  container.innerHTML = `<span class="cat-chip cat-todos ${_selectedCats.size === 0 ? "active" : ""}" onclick="toggleAllCats()">Todas</span>`;
  cats.forEach(cat => {
    const chip = document.createElement("span");
    chip.className = `cat-chip ${_selectedCats.has(cat) ? "active" : ""}`;
    chip.textContent = cat;
    chip.onclick = () => toggleCat(cat);
    container.appendChild(chip);
  });
}

function toggleCat(cat) {
  if (_selectedCats.has(cat)) {
    _selectedCats.delete(cat);
  } else {
    _selectedCats.add(cat);
  }
  // Update chip appearance without full re-fetch
  document.querySelectorAll(".cat-chip:not(.cat-todos)").forEach(chip => {
    chip.classList.toggle("active", _selectedCats.has(chip.textContent));
  });
  const todosChip = document.querySelector(".cat-todos");
  if (todosChip) todosChip.classList.toggle("active", _selectedCats.size === 0);
}

function toggleAllCats() {
  _selectedCats.clear();
  document.querySelectorAll(".cat-chip").forEach(c => c.classList.remove("active"));
  const todosChip = document.querySelector(".cat-todos");
  if (todosChip) todosChip.classList.add("active");
}

loadCategorias();

// ── Filter toggle ──────────────────────────────────────────────────────────────

document.getElementById("btn-toggle-filters").addEventListener("click", function () {
  const panel = document.getElementById("filter-panel");
  const open = panel.style.display !== "none";
  panel.style.display = open ? "none" : "";
  this.textContent = open ? "Filtros ▾" : "Filtros ▴";
  this.setAttribute("aria-expanded", !open);
});

// ── GASTOS ─────────────────────────────────────────────────────────────────────

function _gastosParams() {
  const fuente = document.getElementById("filter-fuente").value;
  const usuario = document.getElementById("filter-usuario").value;
  const mes = document.getElementById("filter-mes").value;
  const p = new URLSearchParams();
  if (fuente) p.set("fuente", fuente);
  if (usuario) p.set("usuario", usuario);
  if (mes) p.set("mes", mes);
  if (_selectedCats.size > 0) p.set("categorias", [..._selectedCats].join(","));
  return p;
}

async function loadGastos() {
  const res = await fetch(`${BASE}/api/gastos?${_gastosParams()}`);
  const gastos = await res.json();

  const tbody = document.getElementById("gastos-body");
  tbody.innerHTML = "";

  if (!gastos.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#aaa;padding:2rem">Sin movimientos</td></tr>`;
    document.getElementById("gastos-summary").textContent = "";
    return;
  }

  const arsGastos = gastos.filter(g => g.moneda === "ARS");
  const totalARS = arsGastos.reduce((s, g) => s + parseFloat(g.monto), 0);
  const totalUSD = gastos.filter(g => g.moneda === "USD").reduce((s, g) => s + parseFloat(g.monto), 0);
  let summary = `${gastos.length} movimientos`;
  if (totalARS) summary += ` — ARS ${totalARS.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  if (totalUSD) summary += ` — USD ${totalUSD.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  document.getElementById("gastos-summary").textContent = summary;

  gastos.forEach(g => {
    const tr = document.createElement("tr");
    const u = g.usuario || "";
    const isNeg = parseFloat(g.monto) < 0;
    tr.innerHTML = `
      <td>${g.fecha}</td>
      <td>${escHtml(g.descripcion)}</td>
      <td class="monto ${g.moneda === "USD" ? "usd" : ""} ${isNeg ? "neg" : ""}">${formatMonto(g.monto)}</td>
      <td>${g.moneda}</td>
      <td><span class="badge badge-${g.fuente}">${g.fuente.replace("_", " ")}</span></td>
      <td>
        <select class="usuario-select" onchange="saveUsuario(${g.id}, this)">
          <option value="" ${!u ? "selected" : ""}>—</option>
          <option value="Seba" ${u === "Seba" ? "selected" : ""}>Seba</option>
          <option value="Mada" ${u === "Mada" ? "selected" : ""}>Mada</option>
        </select>
      </td>
      <td>
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria || '')}"
          title="${g.categoria_fuente ? "Fuente: " + g.categoria_fuente : ""}" />
      </td>
      <td><button class="btn btn-sm" onclick="saveCategoria(${g.id}, this)">✓</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function saveCategoria(id, btn) {
  const input = document.querySelector(`.cat-input[data-id="${id}"]`);
  const res = await fetch(`${BASE}/api/gastos/${id}/categoria`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ categoria: input.value }),
  });
  btn.textContent = res.ok ? "✓" : "✗";
  setTimeout(() => btn.textContent = "✓", 1500);
}

async function saveUsuario(id, sel) {
  await fetch(`${BASE}/api/gastos/${id}/usuario`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ usuario: sel.value }),
  });
}

document.getElementById("btn-load").addEventListener("click", loadGastos);

document.getElementById("btn-export").addEventListener("click", () => {
  window.open(`${BASE}/api/gastos/export?${_gastosParams()}`, "_blank");
});

loadGastos();

// ── UPLOAD ─────────────────────────────────────────────────────────────────────

document.getElementById("btn-upload").addEventListener("click", async () => {
  const file = document.getElementById("upload-file").files[0];
  const fuente = document.getElementById("upload-fuente").value;
  const result = document.getElementById("upload-result");

  if (!file) { showResult(result, "Seleccioná un archivo.", false); return; }

  const fd = new FormData();
  fd.append("file", file);
  fd.append("fuente", fuente);

  result.className = "";
  result.textContent = "Procesando…";

  try {
    const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      showResult(result, `✅ ${data.importados} movimientos importados (${data.total_parseados} parseados).`, true);
      loadGastos();
      loadChart();
      loadCategorias();
    } else {
      showResult(result, `❌ ${data.detail || JSON.stringify(data)}`, false);
    }
  } catch (e) {
    showResult(result, `❌ Error de red: ${e}`, false);
  }
});

// ── RULES ──────────────────────────────────────────────────────────────────────

let _rules = [];

async function loadRules() {
  const res = await fetch(`${BASE}/api/rules`);
  const data = await res.json();
  _rules = (data.reglas || []).map(r => ({
    palabras: Array.isArray(r.palabras) ? r.palabras.map(String) : _patternToWords(r.patron || ""),
    categoria: r.categoria || "",
  }));
  renderRules();
}

function _patternToWords(patron) {
  const m = patron.match(/^\(\?i\)\((.+)\)$/s);
  if (m) return m[1].split("|").map(w => w.trim()).filter(Boolean);
  return patron ? [patron] : [];
}

function renderRules() {
  const list = document.getElementById("rules-list");
  list.innerHTML = "";
  _rules.forEach((rule, i) => {
    const card = document.createElement("div");
    card.className = "rule-card";
    const tagsHtml = rule.palabras
      .map((w, j) => `<span class="tag">${escHtml(w)}<button class="tag-x" type="button" onclick="removeTag(${i},${j})">×</button></span>`)
      .join("");
    card.innerHTML = `
      <div class="rule-header">
        <input class="rule-cat" data-i="${i}" value="${escHtml(rule.categoria)}" placeholder="Nombre de categoría">
        <button type="button" class="btn btn-danger btn-sm" onclick="removeRule(${i})">Eliminar</button>
      </div>
      <div class="rule-tags" id="tags-${i}">${tagsHtml}</div>
      <div class="rule-add">
        <input class="tag-input" data-i="${i}" placeholder="Escribí una palabra y presioná Enter…"
               onkeydown="addTag(event,${i})">
      </div>
    `;
    list.appendChild(card);
  });
}

function _syncState() {
  document.querySelectorAll(".rule-cat").forEach((inp, i) => {
    if (_rules[i]) _rules[i].categoria = inp.value;
  });
}

function removeRule(i) {
  _syncState();
  _rules.splice(i, 1);
  renderRules();
}

function removeTag(i, j) {
  _syncState();
  _rules[i].palabras.splice(j, 1);
  renderRules();
}

function addTag(event, i) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const word = event.target.value.trim();
  if (!word) return;
  _syncState();
  if (!_rules[i].palabras.includes(word)) _rules[i].palabras.push(word);
  renderRules();
  const inputs = document.querySelectorAll(".tag-input");
  if (inputs[i]) inputs[i].focus();
}

document.getElementById("btn-add-rule").addEventListener("click", () => {
  _syncState();
  _rules.push({ palabras: [], categoria: "" });
  renderRules();
  const cats = document.querySelectorAll(".rule-cat");
  if (cats.length) cats[cats.length - 1].focus();
});

document.getElementById("btn-save-rules").addEventListener("click", async () => {
  _syncState();
  const reglas = _rules.filter(r => r.palabras.length > 0 && r.categoria.trim());
  const res = await fetch(`${BASE}/api/rules`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reglas }),
  });
  alert(res.ok ? "Reglas guardadas." : "Error al guardar.");
});

loadRules();

// ── Helpers ────────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatMonto(monto) {
  return parseFloat(monto).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showResult(el, msg, ok) {
  el.textContent = msg;
  el.className = ok ? "ok" : "err";
}
