// Tab switching
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// Load user info
fetch("/auth/me").then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
});

// ── GASTOS ──────────────────────────────────────────────────────────────────

async function loadGastos() {
  const fuente = document.getElementById("filter-fuente").value;
  const cat = document.getElementById("filter-categoria").value.trim();
  const params = new URLSearchParams();
  if (fuente) params.set("fuente", fuente);
  if (cat) params.set("categoria", cat);

  const res = await fetch(`/api/gastos?${params}`);
  const gastos = await res.json();

  const tbody = document.getElementById("gastos-body");
  tbody.innerHTML = "";

  if (!gastos.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#aaa;padding:2rem">Sin movimientos</td></tr>`;
    document.getElementById("gastos-summary").textContent = "";
    return;
  }

  const totalARS = gastos.filter(g => g.moneda === "ARS").reduce((s, g) => s + parseFloat(g.monto), 0);
  const totalUSD = gastos.filter(g => g.moneda === "USD").reduce((s, g) => s + parseFloat(g.monto), 0);
  let summary = `${gastos.length} movimientos`;
  if (totalARS) summary += ` — ARS ${totalARS.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  if (totalUSD) summary += ` — USD ${totalUSD.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  document.getElementById("gastos-summary").textContent = summary;

  gastos.forEach(g => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${g.fecha}</td>
      <td>${escHtml(g.descripcion)}</td>
      <td class="monto ${g.moneda === 'USD' ? 'usd' : ''}">${formatMonto(g.monto, g.moneda)}</td>
      <td>${g.moneda}</td>
      <td><span class="badge badge-${g.fuente}">${g.fuente}</span></td>
      <td>
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria || '')}"
          title="${g.categoria_fuente ? 'Fuente: ' + g.categoria_fuente : ''}" />
      </td>
      <td><button class="btn" onclick="saveCategoria(${g.id}, this)">✓</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function saveCategoria(id, btn) {
  const input = document.querySelector(`.cat-input[data-id="${id}"]`);
  const res = await fetch(`/api/gastos/${id}/categoria`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ categoria: input.value }),
  });
  btn.textContent = res.ok ? "✓" : "✗";
  setTimeout(() => btn.textContent = "✓", 1500);
}

document.getElementById("btn-load").addEventListener("click", loadGastos);
loadGastos();

// ── UPLOAD ───────────────────────────────────────────────────────────────────

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
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      showResult(result, `✅ ${data.importados} movimientos importados (${data.total_parseados} parseados).`, true);
      loadGastos();
    } else {
      showResult(result, `❌ ${data.detail || JSON.stringify(data)}`, false);
    }
  } catch (e) {
    showResult(result, `❌ Error de red: ${e}`, false);
  }
});

// ── RULES ────────────────────────────────────────────────────────────────────

async function loadRules() {
  const res = await fetch("/api/rules");
  const data = await res.json();
  renderRules(data.reglas || []);
}

function renderRules(reglas) {
  const list = document.getElementById("rules-list");
  list.innerHTML = "";
  reglas.forEach((r, i) => {
    const div = document.createElement("div");
    div.className = "rule-row";
    div.innerHTML = `
      <input class="rule-patron" data-i="${i}" value="${escHtml(r.patron)}" placeholder="Regex (ej: (?i)carrefour)" />
      <input class="rule-cat" data-i="${i}" value="${escHtml(r.categoria)}" placeholder="Categoría" />
      <button class="btn-del" onclick="removeRule(${i})">✕</button>
    `;
    list.appendChild(div);
  });
}

function removeRule(i) {
  const rows = document.querySelectorAll(".rule-row");
  rows[i].remove();
}

document.getElementById("btn-add-rule").addEventListener("click", () => {
  const list = document.getElementById("rules-list");
  const i = list.children.length;
  const div = document.createElement("div");
  div.className = "rule-row";
  div.innerHTML = `
    <input class="rule-patron" data-i="${i}" value="" placeholder="Regex (ej: (?i)carrefour)" />
    <input class="rule-cat" data-i="${i}" value="" placeholder="Categoría" />
    <button class="btn-del" onclick="this.closest('.rule-row').remove()">✕</button>
  `;
  list.appendChild(div);
});

document.getElementById("btn-save-rules").addEventListener("click", async () => {
  const reglas = [];
  document.querySelectorAll(".rule-row").forEach(row => {
    const patron = row.querySelector(".rule-patron").value.trim();
    const categoria = row.querySelector(".rule-cat").value.trim();
    if (patron && categoria) reglas.push({ patron, categoria });
  });

  const res = await fetch("/api/rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reglas }),
  });
  alert(res.ok ? "Reglas guardadas." : "Error al guardar.");
});

loadRules();

// ── Helpers ──────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatMonto(monto, moneda) {
  const n = parseFloat(monto);
  return n.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showResult(el, msg, ok) {
  el.textContent = msg;
  el.className = ok ? "ok" : "err";
}
