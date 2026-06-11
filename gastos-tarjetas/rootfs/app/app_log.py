"""
Log unificado de la aplicación.

Todos los logger.info/warning/error de los módulos Python fluyen aquí
a través de DBLogHandler (adjuntado al root logger en main.py).

Los logs de runs de scrapers se escriben en batch al final de cada
ejecución (via write_scraper_run_log), además de guardarse en last_log
por instancia (flujo existente sin cambios).

La tabla app_log vive en la DB de cada usuario (gastos.db) y actúa como
ring buffer de MAX_ENTRIES entradas.  Al llenarse, las más antiguas se
descartan automáticamente.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

MAX_ENTRIES = 2000      # entradas máximas en el ring buffer
_prune_counter = 0      # cuenta inserts para disparar prune ocasionalmente
_prune_every   = 50     # prunar cada N inserts
_lock = threading.Lock()

# Prefijos de loggers del sistema que NO queremos guardar en DB
_EXCLUDE_PREFIXES = (
    "uvicorn", "asyncio", "apscheduler",
    "selenium", "urllib3", "httpx", "hpack",
    "websockets", "h11", "httpcore",
)


# ── Tabla ────────────────────────────────────────────────────────────────────

def init_app_log_table() -> None:
    """Crea la tabla app_log en la DB del usuario actual si no existe."""
    try:
        from db import _conn
        with _conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_log (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      TEXT    NOT NULL,
                    level   TEXT    NOT NULL DEFAULT 'INFO',
                    source  TEXT,
                    message TEXT    NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_app_log_id "
                "ON app_log(id DESC)"
            )
    except Exception:
        pass


# ── Escritura ─────────────────────────────────────────────────────────────────

def write_log(level: str, source: str, message: str) -> None:
    """
    Inserta una entrada en app_log.  Nunca levanta excepción.

    Se pruna automáticamente cada _prune_every inserts para mantener
    el ring buffer dentro de MAX_ENTRIES.
    """
    global _prune_counter
    try:
        # Sin contexto de usuario, get_db_path() apunta al /data/gastos.db raíz
        # huérfano. Los logs globales/de arranque/scheduler sin dueño NO deben
        # escribirse ahí (igual salen al log del contenedor por stdout).
        from userctx import _user_data_dir
        if _user_data_dir.get() is None:
            return
        from db import _conn
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = str(message)[:2000]
        with _lock:
            _prune_counter += 1
            do_prune = (_prune_counter % _prune_every == 0)
        with _conn() as conn:
            conn.execute(
                "INSERT INTO app_log (ts, level, source, message) "
                "VALUES (?, ?, ?, ?)",
                (ts, level[:10], (source or "")[:80], msg),
            )
            if do_prune:
                conn.execute(
                    "DELETE FROM app_log WHERE id NOT IN "
                    "(SELECT id FROM app_log ORDER BY id DESC LIMIT ?)",
                    (MAX_ENTRIES,),
                )
    except Exception:
        pass


def write_scraper_run_log(source: str, log_lines: list[str]) -> None:
    """
    Escribe en lote las líneas de un run de scraper.

    Todas las líneas tienen el mismo timestamp (fin del run) para
    facilitar el agrupamiento visual en el log unificado.
    """
    if not log_lines:
        return
    global _prune_counter
    try:
        from userctx import _user_data_dir
        if _user_data_dir.get() is None:
            return  # sin contexto: no escribir al /data/gastos.db raíz huérfano
        from db import _conn
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        src = (source or "scraper")[:80]
        with _conn() as conn:
            for line in log_lines:
                line = str(line).strip()
                if not line:
                    continue
                # Detectar nivel por prefijos conocidos
                level = "INFO"
                ll = line.lower()
                if ll.startswith("error") or "[error]" in ll:
                    level = "ERROR"
                elif ll.startswith("warn") or "[warn]" in ll:
                    level = "WARNING"
                conn.execute(
                    "INSERT INTO app_log (ts, level, source, message) "
                    "VALUES (?, ?, ?, ?)",
                    (ts, level, src, line[:2000]),
                )
            with _lock:
                _prune_counter += len(log_lines)
                do_prune = True  # siempre prunar al final de un batch
            if do_prune:
                conn.execute(
                    "DELETE FROM app_log WHERE id NOT IN "
                    "(SELECT id FROM app_log ORDER BY id DESC LIMIT ?)",
                    (MAX_ENTRIES,),
                )
    except Exception:
        pass


# ── Lectura ───────────────────────────────────────────────────────────────────

def read_logs(
    limit: int = 300,
    source: Optional[str] = None,
    level: Optional[str] = None,
    since_id: Optional[int] = None,
) -> list[dict]:
    """
    Lee entradas de app_log en orden cronológico (más antiguas primero).

    since_id: si se provee, solo devuelve entradas con id > since_id
              (útil para polling incremental desde el browser).
    """
    try:
        from db import _conn
        q = "SELECT id, ts, level, source, message FROM app_log WHERE 1=1"
        params: list = []
        if source:
            q += " AND source = ?"
            params.append(source)
        if level:
            q += " AND level = ?"
            params.append(level.upper())
        if since_id is not None:
            q += " AND id > ?"
            params.append(since_id)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, MAX_ENTRIES)))
        with _conn() as conn:
            rows = conn.execute(q, params).fetchall()
        # Retornar en orden cronológico (más antiguo primero)
        return [dict(r) for r in reversed(rows)]
    except Exception:
        return []


def list_sources() -> list[str]:
    """Devuelve los sources distintos presentes en app_log."""
    try:
        from db import _conn
        with _conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source FROM app_log "
                "WHERE source IS NOT NULL AND source != '' "
                "ORDER BY source"
            ).fetchall()
        return [r["source"] for r in rows]
    except Exception:
        return []


def clear_logs() -> None:
    """Borra todas las entradas de app_log."""
    try:
        from db import _conn
        with _conn() as conn:
            conn.execute("DELETE FROM app_log")
    except Exception:
        pass


# ── Handler de Python logging ─────────────────────────────────────────────────

class DBLogHandler(logging.Handler):
    """
    Handler de logging que escribe en la tabla app_log.

    Se adjunta al root logger en main.py para capturar todos los
    logger.info/warning/error de los módulos de la aplicación.
    Los loggers del sistema (uvicorn, asyncio, etc.) se filtran.
    """

    def __init__(self):
        super().__init__(level=logging.INFO)
        # Formatter minimalista: solo el mensaje (el timestamp se guarda aparte)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        source = record.name or ""
        # Filtrar loggers del sistema
        for prefix in _EXCLUDE_PREFIXES:
            if source == prefix or source.startswith(prefix + "."):
                return
        try:
            msg = self.format(record)
            write_log(record.levelname, source, msg)
        except Exception:
            pass


def setup_db_log_handler() -> None:
    """
    Adjunta DBLogHandler al root logger.

    Llamar UNA sola vez en el startup de la app (on_startup en main.py).
    Idempotente: si ya existe un DBLogHandler adjunto, no agrega otro.
    """
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, DBLogHandler):
            return  # ya instalado
    handler = DBLogHandler()
    root.addHandler(handler)
    # Asegurar que el root logger procese INFO y superior
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
