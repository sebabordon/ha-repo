"""
Lógica de conciliación: matchea movimientos_raw contra gastos.

Algoritmo:
  1. Tomar todos los raw con estado='new'
  2. Para cada uno, buscar candidatos en gastos:
       - misma fuente
       - misma moneda
       - monto igual (tolerancia 0.01)
       - fecha dentro de ±DATE_WINDOW_DAYS
  3. Si hay candidatos, puntuar por proximidad de fecha + similitud de descripción
  4. Si mejor score >= AUTO_MATCH_THRESHOLD → matched (gasto_id set)
  5. Si ningún candidato → unmatched (transacción nueva, no está en ningún PDF)
  6. Actualizar scraper_status.movimientos_nuevos con el count de 'unmatched'

No toca filas con categoria_fuente='manual' ni filas ya procesadas.
"""

import difflib
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from scrapers_db import (
    _find_db_path,
    list_movimientos_raw,
    update_movimiento_raw,
    upsert_scraper_status,
    count_pendientes_por_fuente,
)

logger = logging.getLogger(__name__)

AUTO_MATCH_THRESHOLD = 0.80   # confianza mínima para match automático
DATE_WINDOW_DAYS     = 5      # ventana de días alrededor de la fecha del raw


# ── Normalización de descripciones ────────────────────────────────────────────

_CUOTA_RE  = re.compile(r"\b(\d{1,2}/\d{1,3})\b")         # "1/12", "03/24", "3/6"
_SPACES_RE = re.compile(r"\s+")
_PUNCT_RE  = re.compile(r"[^\w\s]")


def _normalize(desc: str) -> str:
    """
    Normaliza descripción para comparación: minúsculas, sin puntuación.

    NO se eliminan los números de cuota (N/M): el tie-breaker en _score()
    se encarga de penalizar matches entre cuotas distintas, y mantener el
    "3/12" en la descripción normalizada beneficia la similitud cuando sí
    coinciden (mismo N/M → más similitud).
    """
    d = desc.lower().strip()
    d = _PUNCT_RE.sub(" ", d)
    d = _SPACES_RE.sub(" ", d).strip()
    return d


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(raw: dict, candidate: dict) -> float:
    """
    Puntaje de coincidencia entre un raw y un candidato de gastos.
    Devuelve 0.0–1.0.
    """
    # Proximidad de fecha
    try:
        d_raw = datetime.fromisoformat(raw["fecha"])
        d_gas = datetime.fromisoformat(candidate["fecha"])
        day_diff = abs((d_raw - d_gas).days)
    except Exception:
        day_diff = DATE_WINDOW_DAYS
    date_score = max(0.0, 1.0 - day_diff / DATE_WINDOW_DAYS)

    # Similitud de descripción
    desc_score = difflib.SequenceMatcher(
        None,
        _normalize(raw["descripcion"]),
        _normalize(candidate["descripcion"]),
    ).ratio()

    # Ponderación: descripción pesa más que fecha porque los bancos
    # a veces registran fechas distintas (compra vs proceso)
    score = 0.35 * date_score + 0.65 * desc_score

    # Tie-breaker de cuotas: "TIENDA 3/12" jamás puede ser "TIENDA 1/12".
    # _normalize() conserva el N/M en la descripción, así que el SequenceMatcher
    # ya penaliza cuotas distintas; este chequeo lo hace explícito y definitivo
    # para el caso en que el monto y la base del nombre sean idénticos.
    m_raw  = _CUOTA_RE.search(raw["descripcion"])
    m_cand = _CUOTA_RE.search(candidate["descripcion"])
    if m_raw and m_cand and m_raw.group(1) != m_cand.group(1):
        return 0.0   # distinto número de cuota → imposible ser el mismo gasto

    return score


# ── Entrada principal ─────────────────────────────────────────────────────────

def run_conciliation(fuente: Optional[str] = None) -> dict:
    """
    Concilia todos los movimientos_raw con estado='new'.
    Si se pasa fuente, solo procesa esa fuente.
    Devuelve {matched, unmatched, errors}.
    """
    raws = list_movimientos_raw(estado="new", fuente=fuente)
    if not raws:
        return {"matched": 0, "unmatched": 0, "errors": 0}

    db_path = _find_db_path()
    matched = unmatched = errors = 0

    for raw in raws:
        try:
            _conciliar_uno(raw, db_path)
            # Contar después de actualizar
            estado_nuevo = _get_estado(raw["id"], db_path)
            if estado_nuevo == "matched":
                matched += 1
            else:
                unmatched += 1
        except Exception as exc:
            logger.exception("Error conciliando raw id=%d: %s", raw["id"], exc)
            errors += 1

    # Actualizar movimientos_nuevos en scraper_status por fuente
    pendientes = count_pendientes_por_fuente()
    # Actualizar todos los bancos afectados (o el que se filtró)
    bancos = [fuente] if fuente else list({r["fuente"] for r in raws})
    for banco in bancos:
        upsert_scraper_status(
            banco,
            movimientos_nuevos=pendientes.get(banco, 0),
        )

    logger.info(
        "Conciliación%s: matched=%d unmatched=%d errors=%d",
        f" [{fuente}]" if fuente else "",
        matched, unmatched, errors,
    )
    return {"matched": matched, "unmatched": unmatched, "errors": errors}


def _conciliar_uno(raw: dict, db_path: str) -> None:
    """Concilia un único movimiento_raw contra la tabla gastos."""
    raw_date  = datetime.fromisoformat(raw["fecha"])
    date_from = (raw_date - timedelta(days=DATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    date_to   = (raw_date + timedelta(days=DATE_WINDOW_DAYS)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        candidates = conn.execute(
            """
            SELECT id, fecha, descripcion, monto, moneda
            FROM gastos
            WHERE fuente  = ?
              AND moneda  = ?
              AND ABS(CAST(monto AS REAL) - ?) < 0.02
              AND fecha BETWEEN ? AND ?
            """,
            (
                raw["fuente"],
                raw["moneda"],
                float(raw["monto"]),
                date_from,
                date_to,
            ),
        ).fetchall()
    finally:
        conn.close()

    if not candidates:
        update_movimiento_raw(raw["id"], "unmatched")
        return

    scored = sorted(
        [(dict(c), _score(raw, dict(c))) for c in candidates],
        key=lambda x: x[1],
        reverse=True,
    )
    best_cand, best_score = scored[0]

    if best_score >= AUTO_MATCH_THRESHOLD:
        update_movimiento_raw(
            raw["id"],
            "matched",
            gasto_id=best_cand["id"],
            confianza=round(best_score, 3),
        )
    else:
        # Score bajo: marcar como unmatched pero guardar la pista del candidato
        # (gasto_id con confianza baja) para que la UI pueda sugerir el match
        update_movimiento_raw(
            raw["id"],
            "unmatched",
            gasto_id=best_cand["id"] if best_score > 0.4 else None,
            confianza=round(best_score, 3),
        )


def _get_estado(raw_id: int, db_path: str) -> str:
    """Lee el estado actual de un movimiento_raw (para contar resultados)."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT estado FROM movimientos_raw WHERE id=?", (raw_id,)
        ).fetchone()
        return row[0] if row else "error"
    finally:
        conn.close()
