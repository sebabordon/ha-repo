"""
Acceso directo a la DB para el servicio de scraping (background job).

Usa el ContextVar de userctx cuando está disponible (jobs con contexto de usuario
seteado por el scheduler). Si no hay contexto, escanea /data/*/gastos.db como
fallback para mantener compatibilidad.
"""

import glob
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _find_db_path() -> str:
    """
    Localiza la DB del usuario activo.

    Orden de prioridad:
    1. ContextVar de userctx (seteado por el scheduler o por requests HTTP)
    2. Primer subdirectorio de /data/ que tenga gastos.db
    3. /data/gastos.db (fallback raíz)
    """
    # Si hay un contexto de usuario activo, usarlo directamente
    try:
        from userctx import get_data_dir, _user_data_dir
        data_dir = _user_data_dir.get()
        if data_dir:
            return os.path.join(data_dir, "gastos.db")
    except Exception:
        pass

    # Escanear subdirectorios
    candidates = sorted(glob.glob(os.path.join(_DATA_DIR, "*/gastos.db")))
    if candidates:
        return candidates[0]

    return os.path.join(_DATA_DIR, "gastos.db")


def _ensure_scraper_tables(conn: sqlite3.Connection) -> None:
    """Crea las tablas del scraper si no existen (idempotente)."""
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
        "CREATE INDEX IF NOT EXISTS idx_raw_estado "
        "ON movimientos_raw(estado)"
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
            movimientos_nuevos  INTEGER DEFAULT 0,
            last_log            TEXT
        )
    """)
    # Migración: agregar last_log si la tabla ya existe sin esa columna
    cols = {r[1] for r in conn.execute("PRAGMA table_info(scraper_status)").fetchall()}
    if "last_log" not in cols:
        conn.execute("ALTER TABLE scraper_status ADD COLUMN last_log TEXT")

    # Pre-cargar filas para los 4 bancos conocidos
    for f in ("amex", "bbva", "galicia", "mercadopago"):
        conn.execute(
            "INSERT OR IGNORE INTO scraper_status (fuente, estado) VALUES (?, 'idle')",
            (f,),
        )


@contextmanager
def _conn():
    path = _find_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_scraper_tables(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── scraper_status ────────────────────────────────────────────────────────────

def upsert_scraper_status(fuente: str, **kwargs) -> None:
    """Actualiza campos de scraper_status para un banco dado."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    with _conn() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO scraper_status (fuente) VALUES (?)", (fuente,)
        )
        conn.execute(
            f"UPDATE scraper_status SET {set_clause} WHERE fuente=?",
            list(kwargs.values()) + [fuente],
        )


def get_scraper_statuses() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM scraper_status ORDER BY fuente").fetchall()
    return [dict(r) for r in rows]


def get_scraper_status(fuente: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scraper_status WHERE fuente=?", (fuente,)
        ).fetchone()
    return dict(row) if row else None


# ── movimientos_raw ───────────────────────────────────────────────────────────

def insert_movimiento_raw_single(m: dict) -> int:
    """
    Inserta un único movimiento y devuelve su ID.
    Útil para entradas manuales donde se necesita el ID para follow-up.
    """
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO movimientos_raw
               (fuente, tarjeta, fecha, fecha_proceso, descripcion, monto, moneda,
                scraped_at, estado, raw_data)
               VALUES (?,?,?,?,?,?,?,?,'new',?)""",
            (
                m["fuente"],
                m.get("tarjeta"),
                m["fecha"],
                m.get("fecha_proceso"),
                m["descripcion"],
                str(m["monto"]),
                m.get("moneda", "ARS"),
                now,
                json.dumps(m.get("raw_data")) if m.get("raw_data") else None,
            ),
        )
        return cur.lastrowid


def insert_movimientos_raw(movimientos: list[dict]) -> int:
    """
    Inserta una tanda de movimientos scrapeados.
    Cada dict debe tener: fuente, fecha, descripcion, monto, moneda.
    Campos opcionales: tarjeta, fecha_proceso, raw_data.
    Devuelve cantidad insertada.
    """
    if not movimientos:
        return 0
    now = datetime.utcnow().isoformat()
    rows = [
        {
            "fuente":        m["fuente"],
            "tarjeta":       m.get("tarjeta"),
            "fecha":         m["fecha"],
            "fecha_proceso": m.get("fecha_proceso"),
            "descripcion":   m["descripcion"],
            "monto":         str(m["monto"]),
            "moneda":        m.get("moneda", "ARS"),
            "scraped_at":    now,
            "raw_data":      json.dumps(m.get("raw_data")) if m.get("raw_data") else None,
        }
        for m in movimientos
    ]
    with _conn() as conn:
        before = conn.execute("SELECT total_changes()").fetchone()[0]
        conn.executemany(
            """INSERT INTO movimientos_raw
               (fuente, tarjeta, fecha, fecha_proceso, descripcion, monto, moneda,
                scraped_at, estado, raw_data)
               VALUES
               (:fuente, :tarjeta, :fecha, :fecha_proceso, :descripcion, :monto, :moneda,
                :scraped_at, 'new', :raw_data)""",
            rows,
        )
        count = conn.execute("SELECT total_changes()").fetchone()[0] - before
    return count


def list_movimientos_raw(
    estado: Optional[str] = None,
    fuente: Optional[str] = None,
    limit: int = 500,
) -> list[dict]:
    q = "SELECT * FROM movimientos_raw WHERE 1=1"
    params: list = []
    if estado:
        q += " AND estado=?"; params.append(estado)
    if fuente:
        q += " AND fuente=?"; params.append(fuente)
    q += f" ORDER BY fecha DESC, id DESC LIMIT {int(limit)}"
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def update_movimiento_raw(
    raw_id: int,
    estado: str,
    gasto_id: Optional[int] = None,
    confianza: Optional[float] = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE movimientos_raw SET estado=?, gasto_id=?, confianza=? WHERE id=?",
            (estado, gasto_id, confianza, raw_id),
        )


def count_pendientes_por_fuente() -> dict[str, int]:
    """Cantidad de 'unmatched' por fuente (para badges en la UI)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT fuente, COUNT(*) AS cnt FROM movimientos_raw "
            "WHERE estado='unmatched' GROUP BY fuente"
        ).fetchall()
    return {r["fuente"]: r["cnt"] for r in rows}


def get_movimiento_raw(raw_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM movimientos_raw WHERE id=?", (raw_id,)
        ).fetchone()
    return dict(row) if row else None


def auto_import_unmatched(fuente: str) -> int:
    """
    Importa a `gastos` todos los movimientos_raw de `fuente` con estado
    'unmatched'. Intenta categorizar automáticamente cada uno.
    Devuelve la cantidad importada.
    """
    rows = list_movimientos_raw(estado="unmatched", fuente=fuente)
    if not rows:
        return 0

    imported = 0
    for raw in rows:
        # Usar solo categorización por reglas (sync). La función `categorize`
        # es async (llama a LLMs) y no se puede await desde un contexto sync.
        cat = None
        try:
            from categorizer import categorize_by_rules
            cat = categorize_by_rules(raw["descripcion"])
        except Exception:
            pass

        gasto_id = importar_a_gastos(raw["id"], categoria=cat, archivo_origen="scraper")
        if gasto_id:
            imported += 1

    return imported


def delete_movimiento_raw(raw_id: int) -> dict:
    """
    Elimina un movimiento_raw.
    Si tenía estado='imported', también borra el gasto asociado de la tabla gastos.
    Devuelve {'deleted_raw': bool, 'deleted_gasto': bool, 'gasto_id': int|None}.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT estado, gasto_id FROM movimientos_raw WHERE id=?", (raw_id,)
        ).fetchone()
        if not row:
            return {"deleted_raw": False, "deleted_gasto": False, "gasto_id": None}

        gasto_id     = row["gasto_id"]
        deleted_gasto = False
        if row["estado"] == "imported" and gasto_id:
            conn.execute("DELETE FROM gastos WHERE id=?", (gasto_id,))
            deleted_gasto = True

        conn.execute("DELETE FROM movimientos_raw WHERE id=?", (raw_id,))
    return {"deleted_raw": True, "deleted_gasto": deleted_gasto, "gasto_id": gasto_id}


def consolidate_scraper_duplicates(fuente: str, pdf_records: list[dict]) -> int:
    """
    Elimina gastos scraper duplicados tras subir un PDF.

    Cuando el scraper auto-importó transacciones de un período abierto y luego
    se sube el PDF del mismo período (ya cerrado), existen duplicados en gastos:
    uno con archivo_origen='scraper' y otro recién insertado desde el PDF.

    Este función hace que el PDF "gane":
      - Elimina el gasto con archivo_origen='scraper'
      - Actualiza el movimiento_raw asociado a estado='matched' apuntando al PDF

    Matching: mismo fuente+moneda, monto ±0.02, fecha ±5 días, descripción >60% similar.
    Devuelve la cantidad de duplicados de scraper eliminados.
    """
    import difflib
    import re
    from datetime import datetime, timedelta

    _CUOTA_RE = re.compile(r"\b(\d{1,2}/\d{1,3})\b")

    if not pdf_records:
        return 0

    eliminated = 0

    for rec in pdf_records:
        try:
            fecha_dt = datetime.fromisoformat(str(rec["fecha"]))
        except Exception:
            continue

        date_from = (fecha_dt - timedelta(days=5)).strftime("%Y-%m-%d")
        date_to   = (fecha_dt + timedelta(days=5)).strftime("%Y-%m-%d")
        monto     = float(rec["monto"])
        moneda    = rec.get("moneda", "ARS")
        desc_pdf  = str(rec.get("descripcion", "")).lower().strip()
        cuota_pdf = _CUOTA_RE.search(desc_pdf)

        with _conn() as conn:
            # El gasto PDF recién insertado (el más reciente que NO es del scraper)
            pdf_gasto = conn.execute(
                """SELECT id FROM gastos
                   WHERE fuente=? AND moneda=?
                     AND ABS(CAST(monto AS REAL) - ?) < 0.02
                     AND fecha BETWEEN ? AND ?
                     AND (archivo_origen IS NULL OR archivo_origen != 'scraper')
                   ORDER BY id DESC LIMIT 1""",
                (fuente, moneda, monto, date_from, date_to),
            ).fetchone()
            if not pdf_gasto:
                continue
            pdf_gasto_id = pdf_gasto["id"]

            # Gastos con archivo_origen='scraper' que matcheen la misma transacción
            scraper_candidates = conn.execute(
                """SELECT g.id AS gasto_id, g.descripcion, m.id AS raw_id
                   FROM gastos g
                   JOIN movimientos_raw m ON m.gasto_id = g.id
                   WHERE g.fuente=? AND g.moneda=?
                     AND ABS(CAST(g.monto AS REAL) - ?) < 0.02
                     AND g.fecha BETWEEN ? AND ?
                     AND g.archivo_origen = 'scraper'
                     AND m.estado = 'imported'
                     AND g.id != ?""",
                (fuente, moneda, monto, date_from, date_to, pdf_gasto_id),
            ).fetchall()

            for sc in scraper_candidates:
                desc_sc   = str(sc["descripcion"]).lower().strip()
                cuota_sc  = _CUOTA_RE.search(desc_sc)

                # Tie-breaker: si ambos tienen N/M y son distintos → no es el mismo gasto
                if cuota_sc and cuota_pdf and cuota_sc.group(1) != cuota_pdf.group(1):
                    continue

                ratio = difflib.SequenceMatcher(None, desc_sc, desc_pdf).ratio()
                if ratio < 0.60:
                    continue

                # PDF gana: borrar gasto scraper, raw pasa a matched
                conn.execute("DELETE FROM gastos WHERE id=?", (sc["gasto_id"],))
                conn.execute(
                    "UPDATE movimientos_raw SET estado='matched', gasto_id=? WHERE id=?",
                    (pdf_gasto_id, sc["raw_id"]),
                )
                eliminated += 1
                logger.info(
                    "[consolidate] %s: scraper gasto id=%d eliminado → raw id=%d matched con PDF gasto id=%d (score=%.2f)",
                    fuente, sc["gasto_id"], sc["raw_id"], pdf_gasto_id, ratio,
                )

    return eliminated


def importar_a_gastos(
    raw_id: int,
    categoria: Optional[str] = None,
    archivo_origen: str = "scraper",
) -> Optional[int]:
    """
    Mueve un movimiento_raw (unmatched) a la tabla gastos.
    Devuelve el nuevo gasto_id, o None si el raw_id no existe / ya fue procesado.
    Pasar archivo_origen='manual' para que el gasto sea borrable desde la UI.
    """
    with _conn() as conn:
        raw = conn.execute(
            "SELECT * FROM movimientos_raw WHERE id=? AND estado='unmatched'",
            (raw_id,),
        ).fetchone()
        if not raw:
            return None

        cur = conn.execute(
            """INSERT INTO gastos
               (fecha, descripcion, monto, moneda, fuente,
                categoria, categoria_fuente, archivo_origen)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                raw["fecha"],
                raw["descripcion"],
                raw["monto"],
                raw["moneda"],
                raw["fuente"],
                categoria or None,
                "regla" if categoria else None,
                archivo_origen,
            ),
        )
        new_id = cur.lastrowid
        conn.execute(
            "UPDATE movimientos_raw SET estado='imported', gasto_id=? WHERE id=?",
            (new_id, raw_id),
        )
    return new_id
