import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Optional

import yaml

from userctx import get_db_path, get_rules_file

# After the sign-normalization migration (v0.2.35), ALL sources use the same
# convention: positive monto = egreso (money going out), negative = ingreso.
# This expression returns the absolute egreso amount for a row, or 0 for income.
_EGRESO_EXPR = "CASE WHEN CAST(monto AS REAL) > 0 THEN CAST(monto AS REAL) ELSE 0 END"

# Credit-card sources — only used during import to know which sources do NOT
# need their sign flipped (CC parsers already return positive = expense).
_CC_FUENTES = frozenset(("amex", "bbva_mc", "bbva_visa", "galicia_mc"))

# Categories that are always considered "special" regardless of user rules.
_BUILTIN_SPECIALS = frozenset({"Transferencia", "Transferencia Intercuentas"})


def get_special_categorias() -> set[str]:
    """
    Return the set of category names to exclude from totals and charts.
    Includes built-in specials (Transferencia / Transferencia Intercuentas) plus
    any categories where especial=True in rules.yaml.
    """
    try:
        with open(get_rules_file()) as f:
            data = yaml.safe_load(f) or {}
        user_specials = {
            r["categoria"] for r in data.get("reglas", [])
            if r.get("especial") and r.get("categoria")
        }
    except Exception:
        user_specials = set()
    return _BUILTIN_SPECIALS | user_specials


def init_db():
    with _conn() as conn:
        # ── Migration tracking ──────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
            )
        """)

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
                usuario TEXT,
                import_id INTEGER
            )
        """)
        gcols = {r[1] for r in conn.execute("PRAGMA table_info(gastos)").fetchall()}
        if "usuario" not in gcols:
            conn.execute("ALTER TABLE gastos ADD COLUMN usuario TEXT")
        if "import_id" not in gcols:
            conn.execute("ALTER TABLE gastos ADD COLUMN import_id INTEGER")

        # Import batches tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS importaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fuente TEXT NOT NULL,
                archivo TEXT,
                mes_resumen TEXT,
                fecha_import TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
                cantidad INTEGER DEFAULT 0,
                fecha_venc TEXT
            )
        """)
        # Migrations: add columns to existing installations
        icols = {r[1] for r in conn.execute("PRAGMA table_info(importaciones)").fetchall()}
        if "fecha_venc"     not in icols:
            conn.execute("ALTER TABLE importaciones ADD COLUMN fecha_venc TEXT")
        if "total_ars"      not in icols:
            conn.execute("ALTER TABLE importaciones ADD COLUMN total_ars REAL")
        if "total_usd"      not in icols:
            conn.execute("ALTER TABLE importaciones ADD COLUMN total_usd REAL")
        if "proximo_cierre" not in icols:
            conn.execute("ALTER TABLE importaciones ADD COLUMN proximo_cierre TEXT")
        if "proximo_venc"   not in icols:
            conn.execute("ALTER TABLE importaciones ADD COLUMN proximo_venc TEXT")

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos_usuario (
                usuario TEXT PRIMARY KEY,
                monto_mensual REAL DEFAULT 0,
                moneda TEXT DEFAULT 'ARS'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_charts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre    TEXT NOT NULL,
                tipo      TEXT NOT NULL DEFAULT 'bar',
                dimension TEXT NOT NULL DEFAULT 'categoria',
                metrica   TEXT NOT NULL DEFAULT 'egresos',
                filtros   TEXT NOT NULL DEFAULT '{}'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_layout (
                position INTEGER PRIMARY KEY,
                chart_id TEXT NOT NULL
            )
        """)

        # ── Tablas del scraper (staging + estado) ──────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_raw (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                fuente        TEXT NOT NULL,
                tarjeta       TEXT,
                fecha         TEXT NOT NULL,
                fecha_proceso TEXT,
                descripcion   TEXT NOT NULL,
                monto         TEXT NOT NULL,
                moneda        TEXT NOT NULL DEFAULT 'ARS',
                scraped_at    TEXT NOT NULL,
                estado        TEXT NOT NULL DEFAULT 'new',
                gasto_id      INTEGER REFERENCES gastos(id),
                confianza     REAL,
                raw_data      TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_fuente_fecha "
            "ON movimientos_raw(fuente, fecha)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_estado ON movimientos_raw(estado)"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_status (
                fuente              TEXT PRIMARY KEY,
                ultimo_run          TEXT,
                ultimo_ok           TEXT,
                estado              TEXT DEFAULT 'idle',
                error_msg           TEXT,
                saldo_ars           REAL,
                saldo_usd           REAL,
                movimientos_nuevos  INTEGER DEFAULT 0
            )
        """)
        for _f in ("amex", "bbva", "galicia", "mercadopago"):
            conn.execute(
                "INSERT OR IGNORE INTO scraper_status (fuente, estado) VALUES (?, 'idle')",
                (_f,),
            )

        # ── One-time migrations ─────────────────────────────────────────────────
        _run_migrations(conn)


def _run_migrations(conn):
    """Apply any pending one-time DB migrations in order."""
    done = {r[0] for r in conn.execute("SELECT name FROM db_migrations").fetchall()}

    if "normalize_signs_v1" not in done:
        # v0.2.35: unify sign convention — positive monto = egreso for ALL sources.
        # Before this migration, non-CC sources (bbva_cuenta, mercadopago, manual_*)
        # used negative = egreso. Flip their signs so all sources are consistent.
        cc_list = "','".join(_CC_FUENTES)
        conn.execute(f"""
            UPDATE gastos
            SET monto = CAST(-CAST(monto AS REAL) AS TEXT)
            WHERE fuente NOT IN ('{cc_list}')
              AND CAST(monto AS REAL) != 0
        """)
        conn.execute("INSERT INTO db_migrations (name) VALUES ('normalize_signs_v1')")

    if "quick_form_archivo_origen_v1" not in done:
        # v0.3.12: gastos insertados por el formulario rápido (/quick) quedaban con
        # archivo_origen='scraper' (antes del fix). Los identificamos via movimientos_raw
        # que tienen raw_data con 'manual_quick' y gasto_id vinculado.
        conn.execute("""
            UPDATE gastos SET archivo_origen = 'manual'
            WHERE id IN (
                SELECT gasto_id FROM movimientos_raw
                WHERE raw_data LIKE '%manual_quick%'
                  AND gasto_id IS NOT NULL
            )
        """)
        conn.execute("INSERT INTO db_migrations (name) VALUES ('quick_form_archivo_origen_v1')")

    if "fix_importaciones_cantidad_v1" not in done:
        # v0.2.43: SELECT changes() after executemany() returns 1 (last row only).
        # Recalculate cantidad for all import batches from actual gastos counts.
        conn.execute("""
            UPDATE importaciones
            SET cantidad = (
                SELECT COUNT(*) FROM gastos WHERE gastos.import_id = importaciones.id
            )
        """)
        conn.execute("INSERT INTO db_migrations (name) VALUES ('fix_importaciones_cantidad_v1')")

    if "dedup_scraper_gastos_v1" not in done:
        # v0.3.61: bug en v0.3.55→0.3.57 dejó duplicados en `gastos` cuando un
        # scraper corría dos veces (las filas atascadas en movimientos_raw con
        # estado='new' por el mismatch banco/fuente se reimportaban junto con
        # las nuevas).  Encontrar gastos con la misma (fuente, fecha, monto,
        # descripcion, moneda) que provengan del scraper (archivo_origen='scraper')
        # y mantener sólo el de menor id; del resto, borrar el gasto y eliminar
        # la fila vinculada en movimientos_raw.
        dups = conn.execute("""
            SELECT fuente, fecha, monto, descripcion, moneda,
                   GROUP_CONCAT(id, ',') AS ids
            FROM gastos
            WHERE archivo_origen = 'scraper'
            GROUP BY fuente, fecha, CAST(monto AS REAL), descripcion, moneda
            HAVING COUNT(*) > 1
        """).fetchall()
        deleted = 0
        for row in dups:
            ids = [int(x) for x in str(row[5]).split(",") if x]
            ids.sort()
            keep, drop = ids[0], ids[1:]
            for did in drop:
                conn.execute("DELETE FROM gastos WHERE id=?", (did,))
                conn.execute(
                    "DELETE FROM movimientos_raw WHERE gasto_id=?", (did,)
                )
                deleted += 1
        conn.execute("INSERT INTO db_migrations (name) VALUES ('dedup_scraper_gastos_v1')")


@contextmanager
def _conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_gastos(gastos: list[dict], import_info: dict = None) -> int:
    with _conn() as conn:
        import_id = None
        if import_info:
            cur = conn.execute(
                "INSERT INTO importaciones "
                "(fuente, archivo, mes_resumen, fecha_venc, total_ars, total_usd, proximo_cierre, proximo_venc) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (import_info.get("fuente"), import_info.get("archivo"),
                 import_info.get("mes_resumen"), import_info.get("fecha_venc"),
                 import_info.get("total_ars"), import_info.get("total_usd"),
                 import_info.get("proximo_cierre"), import_info.get("proximo_venc")),
            )
            import_id = cur.lastrowid

        before = conn.execute("SELECT total_changes()").fetchone()[0]
        conn.executemany(
            """INSERT INTO gastos
               (fecha, descripcion, monto, moneda, fuente, categoria, categoria_fuente, archivo_origen, usuario, import_id)
               VALUES (:fecha, :descripcion, :monto, :moneda, :fuente, :categoria, :categoria_fuente, :archivo_origen, :usuario, :import_id)""",
            [
                {
                    **g,
                    "fecha":    str(g["fecha"]),
                    "monto":    str(g["monto"]),
                    "usuario":  g.get("usuario"),
                    "import_id": import_id,
                }
                for g in gastos
            ],
        )
        count = conn.execute("SELECT total_changes()").fetchone()[0] - before
        if import_id:
            conn.execute("UPDATE importaciones SET cantidad = ? WHERE id = ?", (count, import_id))
        return count


def list_importaciones() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, fuente, archivo, mes_resumen, fecha_import, cantidad, fecha_venc "
            "FROM importaciones ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_vencimientos() -> list[dict]:
    """
    Return the most-recent import per fuente that has a fecha_venc.

    For each import the query returns:
      total_ars / total_usd  – statement SALDO ACTUAL / TOTAL A PAGAR extracted
                               from the PDF at parse time (may be NULL for older
                               imports or parsers that don't detect it).
      sum_ars   / sum_usd    – gross egresos computed from the gastos table
                               (sum of positive-monto rows for that import_id).
                               Always available; includes the synthetic
                               "Créditos del resumen" adjustment only if it was
                               positive (i.e. an extra charge), never the credit.

    The frontend uses sum_ars as the primary displayed amount so the widget
    always shows something.  When total_ars is present and differs from sum_ars
    the UI flags the discrepancy so the user can investigate.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT i.id, i.fuente, i.archivo, i.mes_resumen, i.fecha_venc,
                   i.total_ars, i.total_usd, i.proximo_cierre, i.proximo_venc,
                   COALESCE(ROUND(SUM(CASE WHEN g.moneda='ARS' AND CAST(g.monto AS REAL) > 0
                                          THEN CAST(g.monto AS REAL) ELSE 0 END), 2), 0) AS sum_ars,
                   COALESCE(ROUND(SUM(CASE WHEN g.moneda='USD' AND CAST(g.monto AS REAL) > 0
                                          THEN CAST(g.monto AS REAL) ELSE 0 END), 2), 0) AS sum_usd,
                   COALESCE(ROUND(SUM(CASE WHEN g.moneda='ARS'
                                               AND NOT (UPPER(g.descripcion) LIKE '%5617%'
                                                        AND CAST(g.monto AS REAL) < 0)
                                          THEN CAST(g.monto AS REAL) ELSE 0 END), 2), 0) AS net_ars,
                   COALESCE(ROUND(SUM(CASE WHEN g.moneda='USD'
                                          THEN CAST(g.monto AS REAL) ELSE 0 END), 2), 0) AS net_usd,
                   COALESCE(ROUND(SUM(CASE WHEN g.moneda='ARS' AND UPPER(g.descripcion) LIKE '%5617%'
                                               AND CAST(g.monto AS REAL) > 0
                                          THEN CAST(g.monto AS REAL) ELSE 0 END), 2), 0) AS rg5617_ars
            FROM importaciones i
            LEFT JOIN gastos g ON g.import_id = i.id
            WHERE i.fecha_venc IS NOT NULL
            GROUP BY i.id
            ORDER BY i.fecha_venc DESC
            LIMIT 20
        """).fetchall()
    return [dict(r) for r in rows]


def list_gastos(
    fuente: Optional[str] = None,
    categorias: Optional[list] = None,
    usuario: Optional[str] = None,
    mes: Optional[str] = None,
    sin_categoria: bool = False,
    moneda: Optional[str] = None,
    import_id: Optional[int] = None,
    excluir_especiales: bool = False,
) -> list[dict]:
    query = """SELECT g.*,
                      CASE WHEN g.archivo_origen='manual' THEN 'manual'
                           ELSE COALESCE(c.tipo, 'auto')
                      END AS tipo
               FROM gastos g LEFT JOIN cuentas c ON g.fuente = c.fuente
               WHERE 1=1"""
    params: list = []
    if fuente:
        query += " AND g.fuente = ?"; params.append(fuente)
    if moneda:
        query += " AND g.moneda = ?"; params.append(moneda)
    if import_id is not None:
        query += " AND g.import_id = ?"; params.append(import_id)
    if excluir_especiales:
        specials = get_special_categorias()
        if specials:
            ph = ",".join("?" * len(specials))
            query += f" AND (g.categoria IS NULL OR g.categoria NOT IN ({ph}))"
            params.extend(specials)
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
    """
    Borra un gasto si pertenece a una cuenta manual O si fue ingresado
    manualmente vía el formulario rápido (archivo_origen='manual').
    """
    gasto = get_gasto(gasto_id)
    if not gasto:
        return False
    # Permitir borrado si la cuenta es manual O si el gasto fue cargado a mano
    if gasto.get("archivo_origen") == "manual":
        return delete_movimiento_manual(gasto_id, gasto["fuente"])
    with _conn() as conn:
        row = conn.execute("SELECT tipo FROM cuentas WHERE fuente=?", (gasto["fuente"],)).fetchone()
    if not row or row[0] != "manual":
        return False
    return delete_movimiento_manual(gasto_id, gasto["fuente"])


def monthly_summary(excluir_especiales: bool = True) -> list[dict]:
    """
    Returns month-by-month ARS totals.
    After the normalize_signs_v1 migration: positive monto = egreso for ALL sources.
    Special categories (Transferencia, Transferencia Intercuentas, user-defined) are
    excluded by default.
    """
    base = "WHERE moneda = 'ARS'"
    params: list = []
    if excluir_especiales:
        specials = get_special_categorias()
        if specials:
            ph = ",".join("?" * len(specials))
            base += f" AND (categoria IS NULL OR categoria NOT IN ({ph}))"
            params.extend(specials)
    query = f"""
        SELECT substr(fecha, 1, 7) AS mes,
          ROUND(SUM(CASE WHEN CAST(monto AS REAL) > 0 THEN  CAST(monto AS REAL) ELSE 0 END), 2) AS egresos,
          ROUND(SUM(CASE WHEN CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL) ELSE 0 END), 2) AS ingresos
        FROM gastos
        {base}
        GROUP BY mes ORDER BY mes
    """
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"mes": r["mes"], "ingresos": float(r["ingresos"]), "egresos": float(r["egresos"])} for r in rows]


def detect_transfers(days_window: int = 3) -> list[dict]:
    """
    Find candidate inter-account transfer pairs:
    a BBVA Cuenta egreso matched to a MercadoPago ingreso (or vice versa)
    with the same absolute ARS amount within `days_window` days.
    Returns only pairs where neither transaction is already a special category.
    """
    # After normalize_signs_v1: positive monto = egreso for all sources.
    # A transfer from bbva_cuenta to mercadopago (or vice-versa) appears as
    # an outflow (monto > 0) on the sending side and an inflow (monto < 0) on
    # the receiving side.
    specials = get_special_categorias()
    if specials:
        ph = ",".join("?" * len(specials))
        excl_a = f"AND (a.categoria IS NULL OR a.categoria NOT IN ({ph}))"
        excl_b = f"AND (b.categoria IS NULL OR b.categoria NOT IN ({ph}))"
        excl_params = list(specials) + list(specials)
    else:
        excl_a = excl_b = ""
        excl_params = []
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
                (a.fuente = 'bbva_cuenta' AND CAST(a.monto AS REAL) > 0
                 AND b.fuente = 'mercadopago' AND CAST(b.monto AS REAL) < 0)
                OR
                (a.fuente = 'mercadopago' AND CAST(a.monto AS REAL) > 0
                 AND b.fuente = 'bbva_cuenta' AND CAST(b.monto AS REAL) < 0)
            )
            {excl_a}
            {excl_b}
        ORDER BY a.fecha DESC
    """
    with _conn() as conn:
        rows = conn.execute(query, excl_params).fetchall()
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
    """Mark both sides of each transfer pair as categoria='Transferencia Intercuentas'."""
    ids = list({i for pair in id_pairs for i in pair})
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with _conn() as conn:
        conn.execute(
            f"UPDATE gastos SET categoria='Transferencia Intercuentas', categoria_fuente='auto' WHERE id IN ({placeholders})",
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


def rename_categoria_in_gastos(old: str, new: Optional[str]) -> int:
    """Rename (or clear if new=None/empty) a category across all gastos."""
    new_val  = new.strip() if new and new.strip() else None
    new_cf   = "manual" if new_val else None
    with _conn() as conn:
        conn.execute(
            "UPDATE gastos SET categoria=?, categoria_fuente=? WHERE categoria=?",
            (new_val, new_cf, old.strip()),
        )
        return conn.execute("SELECT changes()").fetchone()[0]


def rename_usuario_in_gastos(old_name: str, new_name: str) -> int:
    """Rename all occurrences of a persona in the gastos table. Returns rows updated."""
    with _conn() as conn:
        conn.execute(
            "UPDATE gastos SET usuario = ? WHERE usuario = ?",
            (new_name.strip(), old_name.strip()),
        )
        return conn.execute("SELECT changes()").fetchone()[0]


def delete_gastos_by_archivo(archivo: str):
    with _conn() as conn:
        conn.execute("DELETE FROM gastos WHERE archivo_origen = ?", (archivo,))


# ── Stats ──────────────────────────────────────────────────────────────────────

def _base_where(fuente=None, usuario=None, mes=None, meses=None, extra="", moneda='ARS',
                excluir_especiales=True, categoria=None):
    """Build WHERE clause + params for stats queries."""
    conds = []
    params = []
    if excluir_especiales and not categoria:  # skip special-exclusion when drilling into a specific cat
        specials = get_special_categorias()
        if specials:
            ph = ",".join("?" * len(specials))
            conds.append(f"(categoria IS NULL OR categoria NOT IN ({ph}))")
            params.extend(specials)
    if moneda:
        conds.insert(0, "moneda = ?"); params.insert(0, moneda)
    if fuente:
        conds.append("fuente = ?"); params.append(fuente)
    if usuario:
        conds.append("usuario = ?"); params.append(usuario)
    if categoria:
        conds.append("categoria = ?"); params.append(categoria)
    if mes:
        conds.append("fecha LIKE ?"); params.append(f"{mes}-%")
    elif meses:
        conds.append(f"fecha >= date('now', '-{int(meses)} months')")
    if extra:
        conds.append(extra)
    return "WHERE " + " AND ".join(conds), params


def stats_by_category(fuente=None, usuario=None, mes=None, meses=6, moneda='ARS', excluir_especiales=True, categoria=None):
    where, params = _base_where(fuente, usuario, mes, meses if not mes else None, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria)
    q = f"""SELECT COALESCE(categoria,'Sin categoría') AS cat,
              ROUND(SUM({_EGRESO_EXPR}),2) AS total,
              COUNT(*) AS cnt
            FROM gastos {where}
            GROUP BY cat HAVING total > 0 ORDER BY total DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"categoria": r["cat"], "total": float(r["total"]), "count": r["cnt"]} for r in rows]


def stats_by_fuente(usuario=None, mes=None, meses=6, moneda='ARS', excluir_especiales=True, categoria=None):
    where, params = _base_where(None, usuario, mes, meses if not mes else None, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria)
    q = f"""SELECT fuente,
              ROUND(SUM({_EGRESO_EXPR}),2) AS egreso
            FROM gastos {where}
            GROUP BY fuente HAVING egreso > 0 ORDER BY egreso DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"fuente": r["fuente"], "total": float(r["egreso"])} for r in rows]


def stats_by_usuario(fuente=None, mes=None, meses=6, moneda='ARS', excluir_especiales=True, categoria=None):
    where, params = _base_where(fuente, None, mes, meses if not mes else None, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria)
    q = f"""SELECT COALESCE(usuario,'Sin asignar') AS usr,
              ROUND(SUM({_EGRESO_EXPR}),2) AS egreso
            FROM gastos {where}
            GROUP BY usr HAVING egreso > 0 ORDER BY egreso DESC"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"usuario": r["usr"], "total": float(r["egreso"])} for r in rows]


def stats_top_descriptions(fuente=None, usuario=None, mes=None, meses=6, limit=15, moneda='ARS', excluir_especiales=True, categoria=None):
    where, params = _base_where(fuente, usuario, mes, meses if not mes else None, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria)
    q = f"""SELECT descripcion,
              ROUND(SUM({_EGRESO_EXPR}),2) AS total,
              COUNT(*) AS cnt
            FROM gastos {where}
            GROUP BY descripcion HAVING total > 0
            ORDER BY total DESC LIMIT {int(limit)}"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"descripcion": r["descripcion"], "total": float(r["total"]), "count": r["cnt"]} for r in rows]


def stats_monthly_by_category(fuente=None, usuario=None, meses=6, moneda='ARS', excluir_especiales=True, categoria=None):
    where, params = _base_where(fuente, usuario, meses=meses, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria)
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


def apply_user_rules(reglas: list[dict]) -> int:
    """
    Apply keyword→person rules to all gastos.
    Rules are evaluated in order; the first matching rule wins.
    Returns the number of rows updated.
    """
    if not reglas:
        return 0
    with _conn() as conn:
        rows = conn.execute("SELECT id, descripcion FROM gastos").fetchall()

    updates = []
    for row in rows:
        desc_upper = row["descripcion"].upper()
        for rule in reglas:
            palabras = rule.get("palabras", [])
            if not palabras:
                continue
            if any(p.upper() in desc_upper for p in palabras):
                usuario = rule.get("usuario", "")
                if usuario:
                    updates.append((usuario, row["id"]))
                break

    if updates:
        with _conn() as conn:
            conn.executemany("UPDATE gastos SET usuario=? WHERE id=?", updates)
    return len(updates)


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


def rename_cuenta(fuente: str, nombre: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE cuentas SET nombre=? WHERE fuente=?", (nombre.strip(), fuente))


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
    """Recompute saldo for a manual account from the sum of its movements.

    After the normalize_signs_v1 migration, positive monto = egreso.
    Balance = income - expenses = -SUM(monto).
    """
    with _conn() as conn:
        cuenta = conn.execute("SELECT moneda FROM cuentas WHERE fuente=?", (fuente,)).fetchone()
        if not cuenta:
            return
        moneda = cuenta["moneda"] or "ARS"
        row = conn.execute(
            "SELECT ROUND(SUM(CAST(monto AS REAL)),2) AS t FROM gastos WHERE fuente=?",
            (fuente,),
        ).fetchone()
        total = -float(row["t"] or 0)  # negate: income adds to balance, expense subtracts
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
            # Actualizar el movimiento_raw vinculado según su origen:
            # - /quick (manual_quick): borrar completamente (no hay razón para guardar sentinel)
            # - scraper: marcar 'ignored' para que no reimporte en el próximo run
            raw_row = conn.execute(
                "SELECT id, raw_data FROM movimientos_raw WHERE gasto_id=?", (gasto_id,)
            ).fetchone()
            if raw_row:
                import json as _json
                is_manual_quick = False
                try:
                    rd = _json.loads(raw_row["raw_data"]) if raw_row["raw_data"] else {}
                    is_manual_quick = bool(rd.get("manual_quick"))
                except Exception:
                    pass
                if is_manual_quick:
                    conn.execute("DELETE FROM movimientos_raw WHERE id=?", (raw_row["id"],))
                else:
                    conn.execute(
                        "UPDATE movimientos_raw SET estado='ignored', gasto_id=NULL WHERE id=?",
                        (raw_row["id"],),
                    )
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


def get_presupuestos_usuario() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM presupuestos_usuario ORDER BY usuario").fetchall()
    return [dict(r) for r in rows]


def save_presupuestos_usuario(items: list[dict]):
    with _conn() as conn:
        conn.execute("DELETE FROM presupuestos_usuario")
        conn.executemany(
            "INSERT INTO presupuestos_usuario (usuario, monto_mensual, moneda) VALUES (?,?,?)",
            [(it["usuario"], it["monto_mensual"], it.get("moneda","ARS")) for it in items if it.get("usuario")],
        )


_DEFAULT_LAYOUT = ["category", "top_desc", "monthly_cat", "fuente", "usuario", "forecast"]

_INGRESO_EXPR = "CASE WHEN CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL) ELSE 0 END"


def get_chart_layout() -> list[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT chart_id FROM chart_layout ORDER BY position").fetchall()
    return [r["chart_id"] for r in rows] if rows else _DEFAULT_LAYOUT[:]


def save_chart_layout(layout: list[str]):
    with _conn() as conn:
        conn.execute("DELETE FROM chart_layout")
        conn.executemany(
            "INSERT INTO chart_layout (position, chart_id) VALUES (?,?)",
            [(i, cid) for i, cid in enumerate(layout)],
        )


def get_custom_charts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM custom_charts ORDER BY id").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["filtros"] = json.loads(d.get("filtros") or "{}")
        result.append(d)
    return result


def create_custom_chart(data: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO custom_charts (nombre,tipo,dimension,metrica,filtros) VALUES (?,?,?,?,?)",
            (data["nombre"], data.get("tipo","bar"), data.get("dimension","categoria"),
             data.get("metrica","egresos"), json.dumps(data.get("filtros",{}))),
        )
        return cur.lastrowid


def update_custom_chart(id: int, data: dict):
    with _conn() as conn:
        conn.execute(
            "UPDATE custom_charts SET nombre=?,tipo=?,dimension=?,metrica=?,filtros=? WHERE id=?",
            (data["nombre"], data.get("tipo","bar"), data.get("dimension","categoria"),
             data.get("metrica","egresos"), json.dumps(data.get("filtros",{})), id),
        )


def delete_custom_chart(id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM custom_charts WHERE id=?", (id,))


def stats_pivot(dimension="categoria", metrica="egresos", fuente=None, usuario=None,
                mes=None, meses=6, moneda="ARS", excluir_especiales=True, categoria=None) -> list[dict]:
    """Generic pivot query: group gastos by any dimension, aggregate by any metric."""
    DIM_MAP = {
        "categoria": "COALESCE(categoria,'Sin categoría')",
        "fuente":    "fuente",
        "usuario":   "COALESCE(usuario,'Sin asignar')",
        "mes":       "substr(fecha,1,7)",
    }
    MET_MAP = {
        "egresos":  f"ROUND(SUM({_EGRESO_EXPR}),2)",
        "ingresos": f"ROUND(SUM({_INGRESO_EXPR}),2)",
        "cantidad": "COUNT(*)",
    }
    dim_expr = DIM_MAP.get(dimension, DIM_MAP["categoria"])
    met_expr = MET_MAP.get(metrica,   MET_MAP["egresos"])
    order_by = "dim ASC" if dimension == "mes" else "valor DESC"
    where, params = _base_where(
        fuente, usuario, mes, meses if not mes else None,
        moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria,
    )
    q = f"""SELECT {dim_expr} AS dim, {met_expr} AS valor
            FROM gastos {where}
            GROUP BY dim HAVING valor > 0 ORDER BY {order_by}"""
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"label": r["dim"], "valor": float(r["valor"])} for r in rows]


def stats_presupuesto_usuario_vs_actual(mes: str) -> list[dict]:
    """Presupuesto por persona vs gasto real del mes."""
    where, params = _base_where(mes=mes)
    q_actual = f"""
        SELECT COALESCE(usuario, 'Sin asignar') AS usr,
               ROUND(SUM({_EGRESO_EXPR}), 2) AS gastado
        FROM gastos {where}
        GROUP BY usr
    """
    with _conn() as conn:
        actual_rows = conn.execute(q_actual, params).fetchall()
        budget_rows = conn.execute("SELECT usuario, monto_mensual FROM presupuestos_usuario").fetchall()

    actual = {r["usr"]: float(r["gastado"]) for r in actual_rows if float(r["gastado"]) > 0}
    budget = {r["usuario"]: float(r["monto_mensual"]) for r in budget_rows}

    users = sorted(set(list(actual) + list(budget)))
    result = []
    for usr in users:
        g = actual.get(usr, 0.0)
        b = budget.get(usr, 0.0)
        result.append({
            "usuario":     usr,
            "presupuesto": b,
            "gastado":     g,
            "diferencia":  round(b - g, 2),
            "pct":         round(g / b * 100, 1) if b > 0 else None,
        })
    result.sort(key=lambda r: -r["gastado"])
    return result


# ── Forecast ───────────────────────────────────────────────────────────────────

def _add_months(ym: str, n: int) -> str:
    y, m = map(int, ym.split("-"))
    m += n
    while m > 12: m -= 12; y += 1
    return f"{y:04d}-{m:02d}"


def stats_forecast(
    meses_futuro: int = 6,
    meses_historico: int = 3,
    exclude_income_cats: list = None,
) -> dict:
    """
    Linear-regression forecast on the last `meses_historico` months.
    Returns historical monthly data + projected future months.

    If ``exclude_income_cats`` is provided, those categories are subtracted
    from each month's income total before fitting the trend line (useful to
    ignore one-off windfalls like bonuses when projecting).
    """
    historical = monthly_summary()

    if exclude_income_cats:
        placeholders = ",".join("?" * len(exclude_income_cats))
        excl_q = f"""
            SELECT substr(fecha, 1, 7) AS mes,
              ROUND(SUM(CASE WHEN CAST(monto AS REAL) < 0 THEN -CAST(monto AS REAL) ELSE 0 END), 2) AS ingreso_excl
            FROM gastos
            WHERE moneda = 'ARS'
              AND categoria IN ({placeholders})
            GROUP BY mes
        """
        with _conn() as conn:
            rows = conn.execute(excl_q, list(exclude_income_cats)).fetchall()
        excl_map = {r["mes"]: float(r["ingreso_excl"]) for r in rows}
        historical = [
            {**h, "ingresos": max(0.0, h["ingresos"] - excl_map.get(h["mes"], 0.0))}
            for h in historical
        ]

    if len(historical) < 2:
        return {"historical": historical, "forecast": []}

    # Exclude the current (incomplete) month from the regression baseline so a
    # partial month doesn't drag the trend line toward zero.  The current month
    # is still shown in the historical series on the chart.
    from datetime import date as _date
    current_ym = _date.today().strftime("%Y-%m")
    regression_base = [h for h in historical if h["mes"] < current_ym]
    if len(regression_base) < 2:
        regression_base = historical  # fall back if not enough complete months

    recent = regression_base[-max(2, meses_historico):]
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


def delete_all_gastos(fuente: str = None, import_id: int = None) -> int:
    with _conn() as conn:
        if import_id:
            conn.execute("DELETE FROM gastos WHERE import_id = ?", (import_id,))
        elif fuente:
            conn.execute("DELETE FROM gastos WHERE fuente = ?", (fuente,))
        else:
            conn.execute("DELETE FROM gastos")
        deleted = conn.execute("SELECT changes()").fetchone()[0]
        # Remove import batch records that no longer have any gastos
        conn.execute("""
            DELETE FROM importaciones
            WHERE id NOT IN (SELECT DISTINCT import_id FROM gastos WHERE import_id IS NOT NULL)
        """)
        return deleted
