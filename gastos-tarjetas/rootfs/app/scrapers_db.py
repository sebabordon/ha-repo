"""
Acceso directo a la DB para el servicio de scraping (background job).

No usa el ContextVar de userctx porque no hay request HTTP activo.
Determina la DB correcta buscando la del owner_email configurado en
scrapers.yaml, o por escaneo de /data/*/gastos.db, o la raíz como fallback.
"""

import glob
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _find_db_path() -> str:
    """
    Localiza la DB del usuario propietario.
    Orden de prioridad:
    1. scrapers.yaml → owner_email → /data/{safe_email}/gastos.db
    2. primer subdirectorio de /data/ que tenga gastos.db
    3. /data/gastos.db (fallback raíz)
    """
    try:
        from scrapers_config import get_owner_email
        email = get_owner_email()
        if email:
            safe = re.sub(r"[^a-zA-Z0-9._-]", "_", email.lower())
            candidate = os.path.join(_DATA_DIR, safe, "gastos.db")
            if os.path.exists(candidate):
                return candidate
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
            movimientos_nuevos  INTEGER DEFAULT 0
        )
    """)

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


def importar_a_gastos(raw_id: int, categoria: Optional[str] = None) -> Optional[int]:
    """
    Mueve un movimiento_raw (unmatched) a la tabla gastos.
    Devuelve el nuevo gasto_id, o None si el raw_id no existe / ya fue procesado.
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
                "scraper",
            ),
        )
        new_id = cur.lastrowid
        conn.execute(
            "UPDATE movimientos_raw SET estado='imported', gasto_id=? WHERE id=?",
            (new_id, raw_id),
        )
    return new_id
