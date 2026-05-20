import sqlite3
from contextlib import contextmanager
from typing import Optional

from config import DB_PATH

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
        cols = {r[1] for r in conn.execute("PRAGMA table_info(gastos)").fetchall()}
        if "usuario" not in cols:
            conn.execute("ALTER TABLE gastos ADD COLUMN usuario TEXT")


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
) -> list[dict]:
    query = "SELECT * FROM gastos WHERE 1=1"
    params: list = []
    if fuente:
        query += " AND fuente = ?"
        params.append(fuente)
    if categorias:
        placeholders = ",".join("?" * len(categorias))
        query += f" AND categoria IN ({placeholders})"
        params.extend(categorias)
    if usuario:
        query += " AND usuario = ?"
        params.append(usuario)
    if mes:
        query += " AND fecha LIKE ?"
        params.append(f"{mes}-%")
    query += " ORDER BY fecha DESC"
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


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


def list_categorias() -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT categoria FROM gastos WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria"
        ).fetchall()
    return [r[0] for r in rows]


def update_categoria(gasto_id: int, categoria: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE gastos SET categoria = ?, categoria_fuente = 'manual' WHERE id = ?",
            (categoria, gasto_id),
        )


def update_usuario(gasto_id: int, usuario: str):
    with _conn() as conn:
        conn.execute("UPDATE gastos SET usuario = ? WHERE id = ?", (usuario or None, gasto_id))


def delete_gastos_by_archivo(archivo: str):
    with _conn() as conn:
        conn.execute("DELETE FROM gastos WHERE archivo_origen = ?", (archivo,))


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
            "WHERE categoria_fuente IS NULL OR categoria_fuente != 'manual'"
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


def delete_all_gastos(fuente: str = None) -> int:
    with _conn() as conn:
        if fuente:
            conn.execute("DELETE FROM gastos WHERE fuente = ?", (fuente,))
        else:
            conn.execute("DELETE FROM gastos")
        return conn.execute("SELECT changes()").fetchone()[0]
