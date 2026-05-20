const BASE = window.INGRESS_PREFIX || "";

// ── Tab switching ─────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// ── User info ─────────────────────────────────────────────────────────────────

fetch(`${BASE}/auth/me`).then(r => r.json()).then(u => {
  if (u.email) document.getElementById("user-email").textContent = u.email;
});

// ── GASTOS ────────────────────────────────────────────────────────────────────

function _gastosParams() {
  const fuente = document.getElementById("filter-fuente").value;
  const usuario = document.getElementById("filter-usuario").value;
  const cat = document.getElementById("filter-categoria").value.trim();
  const p = new URLSearchParams();
  if (fuente) p.set("fuente", fuente);
  if (usuario) p.set("usuario", usuario);
  if (cat) p.set("categoria", cat);
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

  const totalARS = gastos.filter(g => g.moneda === "ARS").reduce((s, g) => s + parseFloat(g.monto), 0);
  const totalUSD = gastos.filter(g => g.moneda === "USD").reduce((s, g) => s + parseFloat(g.monto), 0);
  let summary = `${gastos.length} movimientos`;
  if (totalARS) summary += ` — ARS ${totalARS.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  if (totalUSD) summary += ` — USD ${totalUSD.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
  document.getElementById("gastos-summary").textContent = summary;

  gastos.forEach(g => {
    const tr = document.createElement("tr");
    const u = g.usuario || "";
    tr.innerHTML = `
      <td>${g.fecha}</td>
      <td>${escHtml(g.descripcion)}</td>
      <td class="monto ${g.moneda === 'USD' ? 'usd' : ''}">${formatMonto(g.monto)}</td>
      <td>${g.moneda}</td>
      <td><span class="badge badge-${g.fuente}">${g.fuente}</span></td>
      <td>
        <select class="usuario-select" data-id="${g.id}" onchange="saveUsuario(${g.id},this)">
          <option value="" ${!u ? "selected" : ""}>—</option>
          <option value="Seba" ${u === "Seba" ? "selected" : ""}>Seba</option>
          <option value="Mada" ${u === "Mada" ? "selected" : ""}>Mada</option>
        </select>
      </td>
      <td>
        <input class="cat-input" data-id="${g.id}" value="${escHtml(g.categoria || '')}"
          title="${g.categoria_fuente ? 'Fuente: ' + g.categoria_fuente : ''}" />
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
  const params = _gastosParams();
  window.open(`${BASE}/api/gastos/export?${params}`, "_blank");
});

loadGastos();

// ── UPLOAD ────────────────────────────────────────────────────────────────────

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
    } else {
      showResult(result, `❌ ${data.detail || JSON.stringify(data)}`, false);
    }
  } catch (e) {
    showResult(result, `❌ Error de red: ${e}`, false);
  }
});

// ── RULES ─────────────────────────────────────────────────────────────────────

let _rules = []; // [{palabras: string[], categoria: string}]

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
  // Convert legacy "(?i)(word1|word2|...)" to array of words
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
  if (!_rules[i].palabras.includes(word)) {
    _rules[i].palabras.push(word);
  }
  renderRules();
  // Restore focus to this rule's tag input
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

// ── Helpers ───────────────────────────────────────────────────────────────────

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
