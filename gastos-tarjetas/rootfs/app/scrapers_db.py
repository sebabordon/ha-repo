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

# Fallback hardcoded — usado cuando las tablas multi-instancia (v0.4.0) todavía
# no existen (DB recién creada antes del primer run de migraciones).  Después
# de la migración, fuentes_for_banco() resuelve por query a `cuentas` /
# `scraper_instances`, que captura cualquier alias custom que el usuario haya
# creado en la tab Cuentas.
_BANCO_FUENTES_FALLBACK: dict[str, list[str]] = {
    "bbva":           ["bbva", "bbva_cuenta", "bbva_visa", "bbva_mc"],
    "amex":           ["amex"],
    "galicia":        ["galicia", "galicia_mc"],
    "mercadopago":    ["mercadopago"],
    "invertironline": ["invertironline"],
}

def fuentes_for_banco(banco_or_fuente: str) -> list[str]:
    """
    Devuelve todas las `fuente` (columna en cuentas/gastos/movimientos_raw)
    asociadas al argumento.

    - Si `banco_or_fuente` es una banco-key conocida (bbva/amex/galicia/...):
      devuelve todas las fuentes de cuentas linkeadas a instancias de ese banco.
    - Si es una fuente específica (ej. "bbva_cuenta", "mis_pesos_bbva"):
      devuelve [fuente] (pasa por single match).

    Hace fallback al mapping hardcoded si las tablas multi-instancia todavía
    no están creadas (primer arranque, pre-migración).
    """
    try:
        with _conn() as conn:
            # Primero: probar como banco-key — recoger fuentes de cuentas
            # linkeadas a instancias de ese banco.
            rows = conn.execute(
                "SELECT c.fuente FROM cuentas c "
                "JOIN scraper_instances si ON si.id = c.scraper_instance_id "
                "WHERE si.banco = ?",
                (banco_or_fuente,),
            ).fetchall()
            fuentes = sorted({r["fuente"] for r in rows})
            if fuentes:
                # Incluir el banco-key como alias por si quedan datos legacy
                # con fuente=banco-key (pre-migración).
                if banco_or_fuente not in fuentes:
                    fuentes.append(banco_or_fuente)
                return fuentes
            # No matchea como banco — devolver como fuente específica
            return [banco_or_fuente]
    except Exception:
        # Tablas todavía no creadas → fallback hardcoded
        return _BANCO_FUENTES_FALLBACK.get(banco_or_fuente, [banco_or_fuente])


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

    # Pre-cargar filas para los bancos conocidos
    for f in ("amex", "bbva", "galicia", "mercadopago", "invertironline"):
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


# Descripciones exactas genéricas/temporales que BBVA puede reemplazar por
# una más específica en corridas posteriores.
_GENERIC_DESCS = frozenset({
    "TRANSFERENCIA",
    "Transferencia inmediata",
    "Movimiento BBVA",
    "DEPOSITO",
    "DEBITO",
    # BBVA tarjetas de crédito: descripción provisoria hasta que la transacción liquide
    "CONSUMO EN PESOS",
    "CONSUMO EN DOLARES",
    "CONSUMO EN DÓLARES",
})

# Prefijos de descripciones temporales de BBVA (match por startswith).
# Ejemplos: "BANELCO Nro:003164"      → reemplazado por "OPERACION EN EFECTIVO TARJE..."
#           "PAGO SERVICIOS Nro:XXXX" → reemplazado por "PAGO DE SERVICIOS TARJETA..."
#           "DB TRF INM COE Nro:XXXX" → reemplazado por desc estable
#           "TRANSF DEBITO Nro:XXXX"  → ídem
# Nota: "CR TRF INM COE Nro:" y "TRANSF CREDITO Nro:" NO están aquí porque son
# la versión estable/liquidada (se mantienen, no se reemplazan).
_GENERIC_PREFIXES = (
    "BANELCO Nro:",
    "PAGO SERVICIOS Nro:",
    "DB TRF",
    "TRANSF DEBITO",
)


def _load_dedup_config() -> tuple[frozenset, tuple]:
    """
    Carga los sets de dedup desde user_config.json.
    Usa los defaults hardcodeados si no hay configuración guardada o falla la lectura.
    Se llama una vez por invocación de insert_movimientos_raw para no leer el
    archivo en cada iteración del loop.
    """
    try:
        from user_config import read_user_config
        cfg = read_user_config()
        descs    = frozenset(cfg["dedup_exactos"])  if cfg.get("dedup_exactos")  else _GENERIC_DESCS
        prefixes = tuple(cfg["dedup_prefijos"])      if cfg.get("dedup_prefijos") else _GENERIC_PREFIXES
        return descs, prefixes
    except Exception:
        return _GENERIC_DESCS, _GENERIC_PREFIXES


def _is_generic(desc: str, descs: frozenset = None, prefixes: tuple = None) -> bool:
    """True si la descripción es genérica/temporal (puede ser reemplazada por una específica)."""
    d = descs    if descs    is not None else _GENERIC_DESCS
    p = prefixes if prefixes is not None else _GENERIC_PREFIXES
    return desc in d or any(desc.startswith(px) for px in p)


def _generic_sql_cond(col: str = "descripcion",
                      descs: frozenset = None,
                      prefixes: tuple = None) -> tuple[str, tuple]:
    """Devuelve (fragmento_sql, params) para WHERE que matchea descripciones genéricas."""
    d = descs    if descs    is not None else _GENERIC_DESCS
    p = prefixes if prefixes is not None else _GENERIC_PREFIXES
    ph    = ",".join("?" * len(d))
    likes = " OR ".join(f"{col} LIKE ?" for _ in p)
    sql   = f"({col} IN ({ph}) OR {likes})" if p else f"({col} IN ({ph}))"
    return sql, (*d, *(px + "%" for px in p))


def _not_generic_sql_cond(col: str = "descripcion",
                           descs: frozenset = None,
                           prefixes: tuple = None) -> tuple[str, tuple]:
    """Inverso de _generic_sql_cond — matchea descripciones NO genéricas."""
    d = descs    if descs    is not None else _GENERIC_DESCS
    p = prefixes if prefixes is not None else _GENERIC_PREFIXES
    ph    = ",".join("?" * len(d))
    likes = " AND ".join(f"{col} NOT LIKE ?" for _ in p)
    sql   = f"({col} NOT IN ({ph}) AND {likes})" if p else f"({col} NOT IN ({ph}))"
    return sql, (*d, *(px + "%" for px in p))


def insert_movimientos_raw(
    movimientos: list[dict],
    _out_inserted: list[dict] | None = None,
    _log_fn=None,
) -> int:
    """
    Inserta una tanda de movimientos scrapeados.
    Cada dict debe tener: fuente, fecha, descripcion, monto, moneda.
    Campos opcionales: tarjeta, fecha_proceso, raw_data.

    DEDUP: si ya existe una fila con misma (fuente, fecha, monto, descripción,
    moneda) en cualquier estado (new/unmatched/matched/imported/ignored), se
    skipea — el scraper es idempotente, correr 2 veces el mismo día no debería
    crear duplicados.  Si el scraper tiene un identificador único en raw_data
    (ej. numero_operacion para BBVA, payment_id para MP), se usa eso en lugar
    del descriptor para mejor precisión.

    _out_inserted: si se pasa una lista, se le agregan los dicts efectivamente
    insertados (útil para calcular delta de saldo solo sobre los reales nuevos).
    _log_fn: función opcional para loguear skips/inserts en el log del run.

    Devuelve cantidad de filas EFECTIVAMENTE insertadas (excluye duplicados).
    """
    if not movimientos:
        return 0
    now = datetime.utcnow().isoformat()

    # Cargar config de dedup una sola vez (no en cada iteración del loop)
    _eff_descs, _eff_prefixes = _load_dedup_config()

    inserted = 0
    with _conn() as conn:
        for m in movimientos:
            fuente = m["fuente"]
            fecha  = m["fecha"]
            monto  = str(m["monto"])
            desc   = m["descripcion"]
            moneda = m.get("moneda", "ARS")
            raw    = m.get("raw_data") or {}

            # Identificador único del scraper si existe (BBVA: numero_operacion,
            # MP: payment_id, etc.).  Buscar por ese ID es más preciso que por
            # descriptor + monto.
            scraper_uid = None
            for k in ("numero_operacion", "payment_id", "operation_id", "transaction_id"):
                v = raw.get(k) if isinstance(raw, dict) else None
                if v:
                    scraper_uid = (k, str(v))
                    break

            existing = None
            existing_check_name = None  # trackear cuál check encontró el existing
            if scraper_uid:
                # Buscar por scraper UID dentro de raw_data.
                # Matching tanto string ("123") como integer (123) porque
                # json.dumps() serializa enteros sin comillas, pero la versión
                # anterior del código los almacenaba como strings.
                k, v = scraper_uid
                existing = conn.execute(
                    """SELECT id FROM movimientos_raw
                       WHERE fuente = ? AND (
                         raw_data LIKE ? OR raw_data LIKE ? OR
                         raw_data LIKE ? OR raw_data LIKE ?
                       )
                       LIMIT 1""",
                    (
                        fuente,
                        f'%"{k}": "{v}"%',   # string con espacio
                        f'%"{k}":"{v}"%',    # string sin espacio
                        f'%"{k}": {v},%',    # entero seguido de coma
                        f'%"{k}":{v},%',     # entero sin espacio, coma
                    ),
                ).fetchone()
                # Edge case: el campo es el último del objeto (termina en })
                if not existing:
                    existing = conn.execute(
                        """SELECT id FROM movimientos_raw
                           WHERE fuente = ? AND (raw_data LIKE ? OR raw_data LIKE ?)
                           LIMIT 1""",
                        (fuente, f'%"{k}": {v}' + '}%', f'%"{k}":{v}' + '}%'),
                    ).fetchone()

            # Dedup de contraasientos (movimientos opuestos el mismo día).
            # BBVA a veces devuelve dos veces el mismo movimiento: egreso e ingreso opuestos.
            # Ej: -460.000 (pago en cajero) y +460.000 (acreditación/reversión).
            # Si encontramos un movimiento con monto OPUESTO el mismo día → skip el nuevo
            # si el existente es igual o más específico; UPDATE si el nuevo es más específico.
            if not existing and not scraper_uid:
                monto_float = float(monto) if monto else 0.0
                monto_opuesto = -monto_float
                monto_opuesto_str = str(monto_opuesto)

                _cand_opuesto = conn.execute(
                    """SELECT id, descripcion FROM movimientos_raw
                       WHERE fuente = ? AND fecha = ? AND moneda = ?
                         AND CAST(monto AS REAL) = CAST(? AS REAL)
                       LIMIT 1""",
                    (fuente, fecha, moneda, monto_opuesto_str),
                ).fetchone()

                if _cand_opuesto:
                    # Existe el opuesto. Decidir: ¿UPDATE al nuevo o SKIP?
                    desc_existente = _cand_opuesto["descripcion"] or ""
                    es_existente_generico = _is_generic(desc_existente, _eff_descs, _eff_prefixes)
                    es_nuevo_generico = _is_generic(desc, _eff_descs, _eff_prefixes)

                    if not es_nuevo_generico and es_existente_generico:
                        # Nuevo es específico, existente es genérico → UPDATE
                        conn.execute(
                            "UPDATE movimientos_raw SET descripcion = ?, monto = ? WHERE id = ?",
                            (desc, monto, _cand_opuesto["id"]),
                        )
                        if _log_fn:
                            _log_fn(
                                f"  [dedup-opuesto-update] {fecha} {moneda} {monto:>14} "
                                f"→ reemplaza opuesto genérico (id={_cand_opuesto['id']})"
                            )
                        existing = _cand_opuesto
                    else:
                        # Nuevo es genérico o existente es igual/más específico → SKIP
                        if _log_fn:
                            _log_fn(
                                f"  [dedup-opuesto-skip] {fecha} {moneda} {monto:>14} "
                                f"— existe opuesto {-monto_float:>14} (id={_cand_opuesto['id']})"
                            )
                        existing = _cand_opuesto

            if not existing and not scraper_uid:
                # Fallback descriptor solo cuando no hay UID único del scraper.
                # Si hay scraper_uid y no se encontró, es un movimiento nuevo aunque
                # coincida en fecha+monto+desc con otro (ej. dos SUBE el mismo día).
                existing = conn.execute(
                    """SELECT id FROM movimientos_raw
                       WHERE fuente = ? AND fecha = ? AND moneda = ?
                         AND CAST(monto AS REAL) = CAST(? AS REAL)
                         AND descripcion = ?
                       LIMIT 1""",
                    (fuente, fecha, moneda, monto, desc),
                ).fetchone()

            # Cross-run: descripción específica que reemplaza una genérica existente.
            # Solo actuamos si el monto aparece exactamente una vez en esa fecha
            # (unicidad), para no fusionar dos movimientos distintos del mismo importe
            # el mismo día (p.ej. dos retiros de cajero de $460.000).
            # Nota: BBVA devuelve saldo=0 en todos los movimientos, por lo que no
            # podemos usar el saldo corriente como discriminador adicional.
            if not existing and not scraper_uid and not _is_generic(desc, _eff_descs, _eff_prefixes):
                _same_day_total = conn.execute(
                    """SELECT COUNT(*) FROM movimientos_raw
                       WHERE fuente = ? AND fecha = ? AND moneda = ?
                         AND CAST(monto AS REAL) = CAST(? AS REAL)""",
                    (fuente, fecha, moneda, monto),
                ).fetchone()[0]
                if _same_day_total == 1:
                    _g_cond, _g_params = _generic_sql_cond(descs=_eff_descs, prefixes=_eff_prefixes)
                    generic_candidate = conn.execute(
                        f"""SELECT id FROM movimientos_raw
                           WHERE fuente = ? AND fecha = ? AND moneda = ?
                             AND CAST(monto AS REAL) = CAST(? AS REAL)
                             AND {_g_cond}
                           LIMIT 1""",
                        (fuente, fecha, moneda, monto, *_g_params),
                    ).fetchone()
                    if generic_candidate:
                        conn.execute(
                            "UPDATE movimientos_raw SET descripcion = ?, fecha = ? WHERE id = ?",
                            (desc, fecha, generic_candidate["id"]),
                        )
                        existing = generic_candidate   # no insertar fila nueva

            # Cross-run dedup para descripciones genéricas/temporales:
            # Solo skipear si el monto es único en esa fecha (mismo razonamiento:
            # si hay 2+ registros del mismo monto el mismo día, no podemos saber
            # cuál es el que ya importamos).
            if not existing and not scraper_uid and _is_generic(desc, _eff_descs, _eff_prefixes):
                _same_day_total = conn.execute(
                    """SELECT COUNT(*) FROM movimientos_raw
                       WHERE fuente = ? AND fecha = ? AND moneda = ?
                         AND CAST(monto AS REAL) = CAST(? AS REAL)""",
                    (fuente, fecha, moneda, monto),
                ).fetchone()[0]
                if _same_day_total == 1:
                    existing = conn.execute(
                        """SELECT id FROM movimientos_raw
                           WHERE fuente = ? AND fecha = ? AND moneda = ?
                             AND CAST(monto AS REAL) = CAST(? AS REAL)
                           LIMIT 1""",
                        (fuente, fecha, moneda, monto),
                    ).fetchone()

            # Cross-date match con unicidad de monto (ventana ±1 día):
            # BBVA a veces cambia la fecha contable de un movimiento entre runs,
            # rompiendo el match exacto por fecha.  Si el monto aparece exactamente
            # una vez en ±1 día (es único → no hay ambigüedad), aplicamos la misma
            # lógica de actualización/skip que el match mismo-día.
            # Si hay 2+ registros con el mismo monto en la ventana NO actuamos
            # para evitar fusionar movimientos distintos que coinciden en importe.
            if not existing and not scraper_uid:
                try:
                    from datetime import date as _date, timedelta as _td
                    _fd     = _date.fromisoformat(fecha)
                    _d_from = (_fd - _td(days=1)).isoformat()
                    _d_to   = (_fd + _td(days=1)).isoformat()

                    _total = conn.execute(
                        """SELECT COUNT(*) FROM movimientos_raw
                           WHERE fuente = ? AND moneda = ?
                             AND CAST(monto AS REAL) = CAST(? AS REAL)
                             AND fecha BETWEEN ? AND ?""",
                        (fuente, moneda, monto, _d_from, _d_to),
                    ).fetchone()[0]

                    if _total == 1:   # monto único en la ventana → match seguro
                        _gc, _gp   = _generic_sql_cond(descs=_eff_descs, prefixes=_eff_prefixes)
                        _ngc, _ngp = _not_generic_sql_cond(descs=_eff_descs, prefixes=_eff_prefixes)

                        if not _is_generic(desc, _eff_descs, _eff_prefixes):
                            # Caso A: descripción específica reemplaza una genérica
                            # (TRF INM COE, OPERACION EN EFECTIVO → BANELCO Nro:, etc.)
                            # Regla: descripción específica + fecha más reciente.
                            _cand = conn.execute(
                                f"""SELECT id, fecha FROM movimientos_raw
                                   WHERE fuente = ? AND moneda = ?
                                     AND CAST(monto AS REAL) = CAST(? AS REAL)
                                     AND fecha BETWEEN ? AND ?
                                     AND {_gc}
                                   LIMIT 1""",
                                (fuente, moneda, monto, _d_from, _d_to, *_gp),
                            ).fetchone()
                            if _cand:
                                _best_fecha = max(fecha, _cand["fecha"])
                                conn.execute(
                                    "UPDATE movimientos_raw SET descripcion = ?, fecha = ? WHERE id = ?",
                                    (desc, _best_fecha, _cand["id"]),
                                )
                                existing = _cand

                            # Caso B: misma descripción específica, solo cambió la fecha
                            # (p.ej. DEBITO DEBIN Nro:XXXXX un día → mismo Nro al día siguiente).
                            if not _cand:
                                _cand = conn.execute(
                                    """SELECT id, fecha FROM movimientos_raw
                                       WHERE fuente = ? AND moneda = ?
                                         AND CAST(monto AS REAL) = CAST(? AS REAL)
                                         AND fecha BETWEEN ? AND ?
                                         AND descripcion = ?
                                       LIMIT 1""",
                                    (fuente, moneda, monto, _d_from, _d_to, desc),
                                ).fetchone()
                                if _cand and fecha > _cand["fecha"]:
                                    conn.execute(
                                        "UPDATE movimientos_raw SET fecha = ? WHERE id = ?",
                                        (fecha, _cand["id"]),
                                    )
                                if _cand:
                                    existing = _cand
                        else:
                            # Descripción genérica: skip si ya hay una específica.
                            # Si la fecha nueva es más reciente, actualizarla también.
                            _cand = conn.execute(
                                f"""SELECT id, fecha FROM movimientos_raw
                                   WHERE fuente = ? AND moneda = ?
                                     AND CAST(monto AS REAL) = CAST(? AS REAL)
                                     AND fecha BETWEEN ? AND ?
                                     AND {_ngc}
                                   LIMIT 1""",
                                (fuente, moneda, monto, _d_from, _d_to, *_ngp),
                            ).fetchone()
                            if _cand:
                                if fecha > _cand["fecha"]:
                                    conn.execute(
                                        "UPDATE movimientos_raw SET fecha = ? WHERE id = ?",
                                        (fecha, _cand["id"]),
                                    )
                                existing = _cand
                except Exception:
                    pass   # si falla el cálculo de fechas, dejar pasar (INSERT normal)

            if existing:
                if _log_fn:
                    # Extraer el id de existing (puede ser Row o dict)
                    try:
                        existing_id = existing['id'] if existing else '?'
                    except (KeyError, TypeError):
                        existing_id = '?'
                    _log_fn(
                        f"  [dedup-skip] {fecha} {moneda} {monto:>14} — {desc!r:.60} (existing_id={existing_id})"
                    )
                continue   # ya estaba — skipear

            conn.execute(
                """INSERT INTO movimientos_raw
                   (fuente, tarjeta, fecha, fecha_proceso, descripcion, monto, moneda,
                    scraped_at, estado, raw_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
                (
                    fuente,
                    m.get("tarjeta"),
                    fecha,
                    m.get("fecha_proceso"),
                    desc,
                    monto,
                    moneda,
                    now,
                    json.dumps(raw) if raw else None,
                ),
            )
            inserted += 1
            if _log_fn:
                _log_fn(
                    f"  [dedup-insert] {fecha} {moneda} {monto:>14} — {desc!r:.60}"
                )
            if _out_inserted is not None:
                _out_inserted.append(m)
    return inserted


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
        # Expandir banco → fuentes (ej. "bbva" → ["bbva","bbva_cuenta","bbva_visa","bbva_mc"]).
        # Si `fuente` ya es una fuente específica, devuelve [fuente].
        fuentes = fuentes_for_banco(fuente)
        placeholders = ",".join("?" * len(fuentes))
        q += f" AND fuente IN ({placeholders})"
        params.extend(fuentes)
    q += f" ORDER BY scraped_at DESC, fecha DESC, id DESC LIMIT {int(limit)}"
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
    Borra un movimiento_raw desde la UI del scraper — HARD DELETE.

    Comportamiento uniforme para todos los scrapers:
      - La fila se elimina completamente de `movimientos_raw`.
      - Si tenía estado='imported' y un `gasto_id` vinculado, ese gasto
        también se borra de la tabla `gastos`.

    Trade-off conocido: como la fila desaparece de la DB, el dedup de
    `insert_movimientos_raw` no la encuentra en el próximo run del scraper,
    por lo que SÍ puede re-importarse mientras la transacción esté dentro
    del rango temporal configurado (`dias`).  Si el usuario quiere bloquear
    re-import definitivamente, las opciones son:
      - Reducir el `dias` configurado para que la transacción quede fuera
        del rango.
      - Usar una regla de categorización que filtre la descripción.

    Devuelve {'deleted_raw': bool, 'deleted_gasto': bool, 'gasto_id': int|None}.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT fuente, estado, gasto_id FROM movimientos_raw WHERE id=?",
            (raw_id,),
        ).fetchone()
        if not row:
            return {"deleted_raw": False, "deleted_gasto": False, "gasto_id": None}

        gasto_id      = row["gasto_id"]
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
                """SELECT id, categoria, categoria_fuente FROM gastos
                   WHERE fuente=? AND moneda=?
                     AND ABS(CAST(monto AS REAL) - ?) < 0.02
                     AND fecha BETWEEN ? AND ?
                     AND (archivo_origen IS NULL OR archivo_origen != 'scraper')
                   ORDER BY id DESC LIMIT 1""",
                (fuente, moneda, monto, date_from, date_to),
            ).fetchone()
            if not pdf_gasto:
                continue
            pdf_gasto_id       = pdf_gasto["id"]
            pdf_cat            = pdf_gasto["categoria"]
            pdf_cat_fuente     = pdf_gasto["categoria_fuente"]

            # Gastos con archivo_origen='scraper' que matcheen la misma transacción
            scraper_candidates = conn.execute(
                """SELECT g.id AS gasto_id, g.descripcion, g.categoria,
                          g.categoria_fuente, m.id AS raw_id
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

                # Preservar categoría del gasto-scraper en el gasto-PDF si corresponde.
                # Regla: la categoría 'manual' del scraper siempre gana sobre la del PDF
                # (salvo que el PDF también sea 'manual'). Una categoría por 'regla'
                # del scraper se copia solo si el PDF no tiene ninguna.
                sc_cat        = sc["categoria"]
                sc_cat_fuente = sc["categoria_fuente"]
                if sc_cat:
                    inherit = False
                    if sc_cat_fuente == "manual" and pdf_cat_fuente != "manual":
                        inherit = True
                    elif sc_cat_fuente != "manual" and not pdf_cat:
                        inherit = True
                    if inherit:
                        conn.execute(
                            "UPDATE gastos SET categoria=?, categoria_fuente=? WHERE id=?",
                            (sc_cat, sc_cat_fuente, pdf_gasto_id),
                        )
                        logger.info(
                            "[consolidate] %s: categoría '%s' (%s) copiada del scraper al PDF gasto id=%d",
                            fuente, sc_cat, sc_cat_fuente, pdf_gasto_id,
                        )

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

        # Extraer usuario del raw_data si el scraper lo guardó (1ra prioridad)
        usuario = None
        if raw["raw_data"]:
            try:
                rd = json.loads(raw["raw_data"])
                u = (rd.get("usuario") or "").strip()
                if u:
                    usuario = u
            except Exception:
                pass
        # Fallback: si el scraper no setea `usuario`, usar el default de
        # user_config.fuente_usuario[fuente] (configurable en la UI:
        # Config → Usuarios).  Esto garantiza que TODOS los gastos importados
        # por un scraper tengan un usuario asignado (no NULL).
        if usuario is None:
            try:
                from user_config import read_user_config
                ucfg = read_user_config()
                usuario = (ucfg.get("fuente_usuario", {}) or {}).get(raw["fuente"]) or None
            except Exception:
                pass

        cur = conn.execute(
            """INSERT INTO gastos
               (fecha, descripcion, monto, moneda, fuente,
                categoria, categoria_fuente, archivo_origen, usuario)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                raw["fecha"],
                raw["descripcion"],
                raw["monto"],
                raw["moneda"],
                raw["fuente"],
                categoria or None,
                "regla" if categoria else None,
                archivo_origen,
                usuario,
            ),
        )
        new_id = cur.lastrowid
        conn.execute(
            "UPDATE movimientos_raw SET estado='imported', gasto_id=? WHERE id=?",
            (new_id, raw_id),
        )
    return new_id
