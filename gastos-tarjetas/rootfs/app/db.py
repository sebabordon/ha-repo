import re
import sqlite3
from contextlib import contextmanager
from typing import Optional

from config import DB_PATH

# SQL expression that normalises monto to a positive ARS egreso value.
# Returns 0 for ingresos / non-expense rows — useful in SUM().
_EGRESO_EXPR = f"""CASE
  WHEN fuente IN ('{("','".join(("amex","bbva_mc","bbva_visa","galicia_mc")))}')
       AND CAST(monto AS REAL) > 0 THEN  CAST(monto AS REAL)
  WHEN fuente NOT IN ('{("','".join(("amex","bbva_mc","bbva_visa","galicia_mc")))}')
       AND CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL)
  ELSE 0 END"""

# Fuentes that are credit cards: positive monto = expense
_CC_FUENTES = ("amex", "bbva_mc", "bbva_visa", "galicia_mc")
_cc_list = "','".join(_CC_FUENTES)


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto TEXT NOT NULL,
                moneda TEXT NOT NULL,
                fuente TEXT NOT NULL,
                categoria TEXT,
                categoria_fuente TEXT,
                archivo_origen TEXT,
                usuario TEXT
            )
        """)
        gcols = {r[1] for r in conn.execute("PRAGMA table_info(gastos)").fetchall()}
        if "usuario" not in gcols:
            conn.execute("ALTER TABLE gastos ADD COLUMN usuario TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                fuente TEXT PRIMARY KEY,
                nombre TEXT,
                saldo REAL DEFAULT 0,
                moneda TEXT DEFAULT 'ARS',
                fecha_actualizacion TEXT,
                activa INTEGER DEFAULT 1,
                auto_saldo INTEGER DEFAULT 1
            )
        """)
        _defaults = [
            ("bbva_cuenta", "BBVA Cuenta",       0, "ARS", None, 1, 1),
            ("mercadopago", "MercadoPago",        0, "ARS", None, 1, 1),
            ("amex",        "AMEX",               0, "ARS", None, 0, 0),
            ("bbva_mc",     "BBVA Mastercard",    0, "ARS", None, 0, 0),
            ("bbva_visa",   "BBVA Visa",          0, "ARS", None, 0, 0),
            ("galicia_mc",  "Galicia Mastercard", 0, "ARS", None, 0, 0),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO cuentas (fuente,nombre,saldo,moneda,fecha_actualizacion,activa,auto_saldo) VALUES (?,?,?,?,?,?,?)",
            _defaults,
        )

        ccols = {r[1] for r in conn.execute("PRAGMA table_info(cuentas)").fetchall()}
        if "tipo" not in ccols:
            conn.execute("ALTER TABLE cuentas ADD COLUMN tipo TEXT DEFAULT 'auto'")
        if "saldo_usd" not in ccols:
            conn.execute("ALTER TABLE cuentas ADD COLUMN saldo_usd REAL DEFAULT 0")
            # Credit cards can have both ARS and USD charges
            conn.execute(
                "UPDATE cuentas SET moneda='MULTI' WHERE fuente IN ('amex','bbva_mc','bbva_visa','galicia_mc')"
            )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos (
                categoria TEXT PRIMARY KEY,
                monto_mensual REAL DEFAULT 0,
                moneda TEXT DEFAULT 'ARS'
            )
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_gastos(gastos: list[dict]) -> int:
    with _conn() as conn:
        conn.executemany(
            """INSERT INTO gastos
               (fecha, descripcion, monto, moneda, fuente, categoria, categoria_fuente, archivo_origen, usuario)
               VALUES (:fecha, :descripcion, :monto, :moneda, :fuente, :categoria, :categoria_fuente, :archivo_origen, :usuario)""",
            [
                {**g, "fecha": str(g["fecha"]), "monto": str(g["monto"]), "usuario": g.get("usuario")}
                for g in gastos
            ],
        )
        return conn.execute("SELECT changes()").fetchone()[0]


def list_gastos(
    fuente: Optional[str] = None,
    categorias: Optional[list] = None,
    usuario: Optional[str] = None,
    mes: Optional[str] = None,
    sin_categoria: bool = False,
    moneda: Optional[str] = None,
) -> list[dict]:
    query = """SELECT g.*, COALESCE(c.tipo,'auto') AS tipo
               FROM gastos g LEFT JOIN cuentas c ON g.fuente = c.fuente
               WHERE 1=1"""
    params: list = []
    if fuente:
        query += " AND g.fuente = ?"; params.append(fuente)
    if moneda:
        query += " AND g.moneda = ?"; params.append(moneda)
    if sin_categoria:
        query += " AND (g.categoria IS NULL OR g.categoria = '')"
    elif categorias:
        placeholders = ",".join("?" * len(categorias))
        query += f" AND g.categoria IN ({placeholders})"; params.extend(categorias)
    if usuario:
        query += " AND g.usuario = ?"; params.append(usuario)
    if mes:
        query += " AND g.fecha LIKE ?"; params.append(f"{mes}-%")
    query += " ORDER BY g.fecha DESC"
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def delete_gasto_manual(gasto_id: int) -> bool:
    """Delete a gasto only if it belongs to a manual cuenta."""
    gasto = get_gasto(gasto_id)
    if not gasto:
        return False
    with _conn() as conn:
        row = conn.execute("SELECT tipo FROM cuentas WHERE fuente=?", (gasto["fuente"],)).fetchone()
    if not row or row[0] != "manual":
        return False
    return delete_movimiento_manual(gasto_id, gasto["fuente"])


def monthly_summary() -> list[dict]:
    """
    Returns month-by-month ARS totals with correct sign interpretation.
    Transactions with categoria = 'Transferencia' are excluded from both
    egresos and ingresos so inter-account transfers don't inflate totals.

    - Credit cards (amex, bbva_mc, bbva_visa, galicia_mc): positive = egreso
    - Savings/wallet (bbva_cuenta, mercadopago): positive = ingreso, negative = egreso
    """
    query = f"""
        SELECT substr(fecha, 1, 7) AS mes,
          ROUND(SUM(CASE
            WHEN fuente IN ('{_cc_list}') AND CAST(monto AS REAL) > 0 THEN  CAST(monto AS REAL)
            WHEN fuente NOT IN ('{_cc_list}') AND CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL)
            ELSE 0 END), 2) AS egresos,
          ROUND(SUM(CASE
            WHEN fuente NOT IN ('{_cc_list}') AND CAST(monto AS REAL) > 0 THEN  CAST(monto AS REAL)
            WHEN fuente IN ('{_cc_list}') AND CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL)
            ELSE 0 END), 2) AS ingresos
        FROM gastos
        WHERE moneda = 'ARS'
          AND (categoria IS NULL OR categoria != 'Transferencia')
        GROUP BY mes ORDER BY mes
    """
    with _conn() as conn:
        rows = conn.execute(query).fetchall()
    return [{"mes": r["mes"], "ingresos": float(r["ingresos"]), "egresos": float(r["egresos"])} for r in rows]


def detect_transfers(days_window: int = 3) -> list[dict]:
    """
    Find candidate inter-account transfer pairs:
    a BBVA Cuenta egreso matched to a MercadoPago ingreso (or vice versa)
    with the same absolute ARS amount within `days_window` days.
    Returns only pairs where neither transaction is already categorized
    as 'Transferencia'.
    """
    query = f"""
        SELECT
            a.id        AS id_out,
            a.fecha     AS fecha_out,
            a.descripcion AS desc_out,
            a.monto     AS monto_out,
            a.fuente    AS fuente_out,
            b.id        AS id_in,
            b.fecha     AS fecha_in,
            b.descripcion AS desc_in,
            b.monto     AS monto_in,
            b.fuente    AS fuente_in
        FROM gastos a
        JOIN gastos b ON
            ABS(CAST(a.monto AS REAL)) = ABS(CAST(b.monto AS REAL))
            AND ABS(julianday(a.fecha) - julianday(b.fecha)) <= {days_window}
            AND a.moneda = 'ARS' AND b.moneda = 'ARS'
            AND (
                (a.fuente = 'bbva_cuenta' AND CAST(a.monto AS REAL) < 0
                 AND b.fuente = 'mercadopago' AND CAST(b.monto AS REAL) > 0)
                OR
                (a.fuente = 'mercadopago' AND CAST(a.monto AS REAL) < 0
                 AND b.fuente = 'bbva_cuenta' AND CAST(b.monto AS REAL) > 0)
            )
            AND (a.categoria IS NULL OR a.categoria != 'Transferencia')
            AND (b.categoria IS NULL OR b.categoria != 'Transferencia')
        ORDER BY a.fecha DESC
    """
    with _conn() as conn:
        rows = conn.execute(query).fetchall()
    seen = set()
    result = []
    for r in rows:
        key = tuple(sorted([r["id_out"], r["id_in"]]))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(r))
    return result


def mark_transfers(id_pairs: list[tuple[int, int]]):
    """Mark both sides of each transfer pair as categoria='Transferencia'."""
    ids = list({i for pair in id_pairs for i in pair})
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with _conn() as conn:
        conn.execute(
            f"UPDATE gastos SET categoria='Transferencia', categoria_fuente='auto' WHERE id IN ({placeholders})",
            ids,
        )


def get_gasto(gasto_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM gastos WHERE id=?", (gasto_id,)).fetchone()
    return dict(row) if row else None


def list_categorias() -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT categoria FROM gastos WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria"
        ).fetchall()
    return [r[0] for r in rows]


def update_categoria(gasto_id: int, categoria: str):
    # Empty category → clear categoria_fuente so rules can re-apply
    cf = "manual" if categoria and categoria.strip() else None
    with _conn() as conn:
        conn.execute(
            "UPDATE gastos SET categoria = ?, categoria_fuente = ? WHERE id = ?",
            (categoria or None, cf, gasto_id),
        )


def update_gasto_fecha(gasto_id: int, fecha: str):
    with _conn() as conn:
        conn.execute("UPDATE gastos SET fecha = ? WHERE id = ?", (fecha, gasto_id))


def update_usuario(gasto_id: int, usuario: str):
    with _conn() as conn:
        conn.execute("UPDATE gastos SET usuario = ? WHERE id = ?", (usuario or None, gasto_id))


def delete_gastos_by_archivo(archivo: str):
    with _conn() as conn:
        conn.execute("DELETE FROM gastos WHERE archivo_origen = ?", (archivo,))


# ── Stats ──────────────────────────────────────────────────────────────────────

def _base_where(fuente=None, usuario=None, mes=None, meses=None, extra="", moneda='ARS'):
    """Build WHERE clause + params for stats queries."""
    conds = ["(categoria IS NULL OR categoria != 'Transferencia')"]
    params = []
    if moneda:
        conds.insert(0, "moneda = ?"); params.insert(0, moneda)
    if fuente:
        conds.append("fuente = ?"); params.append(fuente)
    if usuario:
        conds.append("usuario = ?"); params.append(usuario)
    if mes:
        conds.append("fecha LIKE ?"); params.append(f"{mes}-%")
    elif meses:
        conds.append(f"fecha >= date('now', '-{int(meses)} months')")
    if extra:
        conds.append(extra)
    return "WHERE " + " AND ".join(conds), params


def stats_by_category(fuente=None, usuario=None, mes=None, meses=6, moneda='ARS'):
    where, params = _base_where(fuente, usuario, mes, meses if not mes else None, moneda=moneda)
    q = f"""SELECT COALESCE(categoria,'Sin categoría') AS cat,
              ROUND(SUM({_EGRESO_EXPR}),2) AS total,
              COUNT(*) AS cnt
            FROM gastos {where}
            GROUP BY cat HAVING total > 0 ORDER BY total DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"categoria": r["cat"], "total": float(r["total"]), "count": r["cnt"]} for r in rows]


def stats_by_fuente(usuario=None, mes=None, meses=6, moneda='ARS'):
    where, params = _base_where(None, usuario, mes, meses if not mes else None, moneda=moneda)
    q = f"""SELECT fuente,
              ROUND(SUM({_EGRESO_EXPR}),2) AS egreso
            FROM gastos {where}
            GROUP BY fuente HAVING egreso > 0 ORDER BY egreso DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"fuente": r["fuente"], "total": float(r["egreso"])} for r in rows]


def stats_by_usuario(fuente=None, mes=None, meses=6, moneda='ARS'):
    where, params = _base_where(fuente, None, mes, meses if not mes else None, moneda=moneda)
    q = f"""SELECT COALESCE(usuario,'Sin asignar') AS usr,
              ROUND(SUM({_EGRESO_EXPR}),2) AS egreso
            FROM gastos {where}
            GROUP BY usr HAVING egreso > 0 ORDER BY egreso DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"usuario": r["usr"], "total": float(r["egreso"])} for r in rows]


def stats_top_descriptions(fuente=None, usuario=None, mes=None, meses=6, limit=15, moneda='ARS'):
    where, params = _base_where(fuente, usuario, mes, meses if not mes else None, moneda=moneda)
    q = f"""SELECT descripcion,
              ROUND(SUM({_EGRESO_EXPR}),2) AS total,
              COUNT(*) AS cnt
            FROM gastos {where}
            GROUP BY descripcion HAVING total > 0
            ORDER BY total DESC LIMIT {int(limit)}"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"descripcion": r["descripcion"], "total": float(r["total"]), "count": r["cnt"]} for r in rows]


def stats_monthly_by_category(fuente=None, usuario=None, meses=6, moneda='ARS'):
    where, params = _base_where(fuente, usuario, meses=meses, moneda=moneda)
    q = f"""SELECT substr(fecha,1,7) AS mes,
              COALESCE(categoria,'Sin categoría') AS cat,
              ROUND(SUM({_EGRESO_EXPR}),2) AS total
            FROM gastos {where}
            GROUP BY mes, cat HAVING total > 0
            ORDER BY mes, total DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"mes": r["mes"], "categoria": r["cat"], "total": float(r["total"])} for r in rows]


# ── Match rules ─────────────────────────────────────────────────────────────────

def apply_match_rules(rules: list[dict]) -> int:
    """
    For each match rule, find transactions matching Lado A (and optionally
    paired with Lado B within the time window) and tag them with the
    specified category.  Manually-categorized rows are never touched.
    Returns the total number of rows updated.
    """
    total = 0
    for rule in rules:
        patron_a  = rule.get("patron_a", "").strip()
        fuente_a  = rule.get("fuente_a", "").strip()
        patron_b  = rule.get("patron_b", "").strip()
        fuente_b  = rule.get("fuente_b", "").strip()
        ventana   = max(0, int(rule.get("ventana_dias", 3)))
        categoria = rule.get("categoria", "Transferencia").strip() or "Transferencia"

        if not patron_a and not fuente_a:
            continue

        # ── Build Side-A query ──────────────────────────────────────────
        q_a = ("SELECT id, fecha FROM gastos "
               "WHERE (categoria_fuente IS NULL OR categoria_fuente != 'manual')")
        p_a: list = []
        if patron_a:
            q_a += " AND UPPER(descripcion) LIKE UPPER(?)"; p_a.append(f"%{patron_a}%")
        if fuente_a:
            q_a += " AND fuente = ?"; p_a.append(fuente_a)

        with _conn() as conn:
            rows_a = conn.execute(q_a, p_a).fetchall()

        ids_to_mark: set[int] = set()

        if patron_b or fuente_b:
            # ── Two-sided: find matching partner in Lado B ──────────────
            q_b = ("SELECT id FROM gastos "
                   "WHERE (categoria_fuente IS NULL OR categoria_fuente != 'manual') "
                   f"AND ABS(julianday(fecha) - julianday(?)) <= {ventana}")
            p_b_base: list = []
            if patron_b:
                q_b += " AND UPPER(descripcion) LIKE UPPER(?)"; p_b_base.append(f"%{patron_b}%")
            if fuente_b:
                q_b += " AND fuente = ?"; p_b_base.append(fuente_b)

            with _conn() as conn:
                for row_a in rows_a:
                    ids_to_mark.add(row_a["id"])
                    p_b = [row_a["fecha"]] + p_b_base
                    for rb in conn.execute(q_b, p_b).fetchall():
                        ids_to_mark.add(rb["id"])
        else:
            ids_to_mark = {r["id"] for r in rows_a}

        if ids_to_mark:
            ph = ",".join("?" * len(ids_to_mark))
            with _conn() as conn:
                conn.execute(
                    f"UPDATE gastos SET categoria=?, categoria_fuente='auto' WHERE id IN ({ph})",
                    [categoria, *ids_to_mark],
                )
            total += len(ids_to_mark)

    return total


def apply_rules_to_all(categorize_fn) -> int:
    """
    Apply rule-based categorization to every gasto that was NOT manually
    categorized (categoria_fuente != 'manual').  Rows that match a rule
    get categoria + categoria_fuente='regla'; rows that no longer match
    any rule get both fields cleared (so they don't keep a stale category).
    Returns the number of rows where a rule matched.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, descripcion FROM gastos "
            "WHERE categoria_fuente IS NULL OR categoria_fuente NOT IN ('manual', 'auto')"
        ).fetchall()

    updates = []
    matched = 0
    for row in rows:
        cat = categorize_fn(row["descripcion"])
        updates.append((cat, "regla" if cat else None, row["id"]))
        if cat:
            matched += 1

    if updates:
        with _conn() as conn:
            conn.executemany(
                "UPDATE gastos SET categoria=?, categoria_fuente=? WHERE id=?",
                updates,
            )
    return matched


# ── Cuentas ────────────────────────────────────────────────────────────────────

def get_cuentas() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM cuentas ORDER BY activa DESC, fuente").fetchall()
    return [dict(r) for r in rows]


def upsert_cuenta_saldo(fuente: str, saldo: float, moneda: str = "ARS", fecha: str = None):
    from datetime import date
    fecha = fecha or str(date.today())
    # Update the right field based on the currency of this balance reading
    field = "saldo_usd" if moneda == "USD" else "saldo"
    with _conn() as conn:
        conn.execute(
            f"UPDATE cuentas SET {field}=?, fecha_actualizacion=? WHERE fuente=? AND auto_saldo=1",
            (saldo, fecha, fuente),
        )


def update_cuenta(fuente: str, saldo: float, saldo_usd: float, moneda: str, activa: int, auto_saldo: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE cuentas SET saldo=?, saldo_usd=?, moneda=?, activa=?, auto_saldo=? WHERE fuente=?",
            (saldo, saldo_usd, moneda, activa, auto_saldo, fuente),
        )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")
    return f"manual_{slug}" if slug else "manual_cuenta"


def create_cuenta_manual(nombre: str, moneda: str = "ARS") -> dict:
    """Create a new manual account. Returns the created row as dict."""
    base = _slugify(nombre)
    with _conn() as conn:
        fuente = base
        i = 2
        while conn.execute("SELECT 1 FROM cuentas WHERE fuente=?", (fuente,)).fetchone():
            fuente = f"{base}_{i}"; i += 1
        conn.execute(
            "INSERT INTO cuentas (fuente,nombre,saldo,saldo_usd,moneda,activa,auto_saldo,tipo) "
            "VALUES (?,?,0,0,?,1,0,'manual')",
            (fuente, nombre, moneda),
        )
    return {"fuente": fuente, "nombre": nombre, "saldo": 0.0, "saldo_usd": 0.0,
            "moneda": moneda, "activa": 1, "auto_saldo": 0, "tipo": "manual",
            "fecha_actualizacion": None}


def delete_cuenta_manual(fuente: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT tipo FROM cuentas WHERE fuente=?", (fuente,)).fetchone()
        if not row or row["tipo"] != "manual":
            return False
        conn.execute("DELETE FROM gastos  WHERE fuente=?", (fuente,))
        conn.execute("DELETE FROM cuentas WHERE fuente=?", (fuente,))
    return True


def recalc_cuenta_saldo(fuente: str):
    """Recompute saldo for a manual account from the sum of its movements."""
    with _conn() as conn:
        cuenta = conn.execute("SELECT moneda FROM cuentas WHERE fuente=?", (fuente,)).fetchone()
        if not cuenta:
            return
        moneda = cuenta["moneda"] or "ARS"
        row = conn.execute(
            "SELECT ROUND(SUM(CAST(monto AS REAL)),2) AS t FROM gastos WHERE fuente=?",
            (fuente,),
        ).fetchone()
        total = float(row["t"] or 0)
        field = "saldo_usd" if moneda == "USD" else "saldo"
        conn.execute(
            f"UPDATE cuentas SET {field}=?, fecha_actualizacion=date('now') "
            "WHERE fuente=? AND tipo='manual'",
            (total, fuente),
        )


def get_movimientos_cuenta(fuente: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM gastos WHERE fuente=? ORDER BY fecha DESC, id DESC",
            (fuente,),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_movimiento_manual(
    fuente: str, fecha: str, descripcion: str,
    monto: float, moneda: str, categoria: str = None,
) -> int:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO gastos "
            "(fecha,descripcion,monto,moneda,fuente,categoria,categoria_fuente,archivo_origen,usuario) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (fecha, descripcion.strip(), str(monto), moneda, fuente,
             categoria or None, "manual" if categoria else None, "manual", None),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    recalc_cuenta_saldo(fuente)
    return new_id


def delete_movimiento_manual(gasto_id: int, fuente: str) -> bool:
    with _conn() as conn:
        conn.execute("DELETE FROM gastos WHERE id=? AND fuente=?", (gasto_id, fuente))
        changed = bool(conn.execute("SELECT changes()").fetchone()[0])
    if changed:
        recalc_cuenta_saldo(fuente)
    return changed


# ── Presupuestos ───────────────────────────────────────────────────────────────

def get_presupuestos() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM presupuestos ORDER BY categoria").fetchall()
    return [dict(r) for r in rows]


def save_presupuestos(items: list[dict]):
    with _conn() as conn:
        conn.execute("DELETE FROM presupuestos")
        conn.executemany(
            "INSERT INTO presupuestos (categoria, monto_mensual, moneda) VALUES (?,?,?)",
            [(it["categoria"], it["monto_mensual"], it.get("moneda","ARS")) for it in items if it.get("categoria")],
        )


def stats_presupuesto_vs_actual(mes: str) -> list[dict]:
    """
    Returns all categories that have a budget OR actual spending in `mes`,
    comparing budget (monto_mensual) vs actual egreso for the month.
    """
    where, params = _base_where(mes=mes)
    q_actual = f"""
        SELECT COALESCE(categoria,'Sin categoría') AS cat,
               ROUND(SUM({_EGRESO_EXPR}), 2) AS gastado
        FROM gastos {where}
        GROUP BY cat
    """
    with _conn() as conn:
        actual_rows = conn.execute(q_actual, params).fetchall()
        budget_rows = conn.execute("SELECT categoria, monto_mensual FROM presupuestos").fetchall()

    actual = {r["cat"]: float(r["gastado"]) for r in actual_rows if float(r["gastado"]) > 0}
    budget = {r["categoria"]: float(r["monto_mensual"]) for r in budget_rows}

    cats = sorted(set(list(actual) + list(budget)))
    result = []
    for cat in cats:
        g = actual.get(cat, 0.0)
        b = budget.get(cat, 0.0)
        result.append({
            "categoria":  cat,
            "presupuesto": b,
            "gastado":     g,
            "diferencia":  round(b - g, 2),
            "pct":         round(g / b * 100, 1) if b > 0 else None,
        })
    result.sort(key=lambda r: (-r["gastado"]))
    return result


# ── Forecast ───────────────────────────────────────────────────────────────────

def _add_months(ym: str, n: int) -> str:
    y, m = map(int, ym.split("-"))
    m += n
    while m > 12: m -= 12; y += 1
    return f"{y:04d}-{m:02d}"


def stats_forecast(meses_futuro: int = 6, meses_historico: int = 3) -> dict:
    """
    Linear-regression forecast on the last `meses_historico` months.
    Returns historical monthly data + projected future months.
    """
    historical = monthly_summary()
    if len(historical) < 2:
        return {"historical": historical, "forecast": []}

    recent = historical[-max(2, meses_historico):]
    n = len(recent)

    def _linreg(vals):
        mx = (n - 1) / 2
        my = sum(vals) / n
        num = sum((i - mx) * (vals[i] - my) for i in range(n))
        den = sum((i - mx) ** 2 for i in range(n))
        m_slope = num / den if den else 0
        return my - m_slope * mx, m_slope   # intercept, slope

    eg_b,  eg_m  = _linreg([r["egresos"]  for r in recent])
    ing_b, ing_m = _linreg([r["ingresos"] for r in recent])

    last_mes = historical[-1]["mes"]
    forecast = []
    for k in range(1, meses_futuro + 1):
        x = n - 1 + k
        forecast.append({
            "mes":      _add_months(last_mes, k),
            "egresos":  round(max(0, eg_b  + eg_m  * x), 2),
            "ingresos": round(max(0, ing_b + ing_m * x), 2),
        })

    return {"historical": historical, "forecast": forecast}


def delete_all_gastos(fuente: str = None) -> int:
    with _conn() as conn:
        if fuente:
            conn.execute("DELETE FROM gastos WHERE fuente = ?", (fuente,))
        else:
            conn.execute("DELETE FROM gastos")
        return conn.execute("SELECT changes()").fetchone()[0]
