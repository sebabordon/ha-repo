import os
import sqlite3
import json
import contextvars

DATA_DIR = os.environ.get("DATA_DIR", "/data")

_current_user = contextvars.ContextVar("current_user", default=None)


def set_user(email: str):
    _current_user.set(email)


def _user_dir() -> str:
    email = _current_user.get()
    if not email:
        return DATA_DIR
    d = os.path.join(DATA_DIR, "users", email.replace("@", "_at_"))
    os.makedirs(d, exist_ok=True)
    return d


def get_db():
    db_path = os.path.join(_user_dir(), "migraines.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS migraines (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       TEXT NOT NULL,
            inicio      TEXT NOT NULL,
            fin         TEXT,
            intensidad  INTEGER NOT NULL CHECK(intensidad BETWEEN 1 AND 10),
            localizacion TEXT,
            tipo_dolor  TEXT,
            aura        INTEGER DEFAULT 0,
            medicacion  TEXT,
            comentarios TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.close()


def list_migraines(limit=50, offset=0, fecha_desde=None, fecha_hasta=None):
    conn = get_db()
    sql = "SELECT * FROM migraines WHERE 1=1"
    params = []
    if fecha_desde:
        sql += " AND fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND fecha <= ?"
        params.append(fecha_hasta)
    sql += " ORDER BY fecha DESC, inicio DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_migraine(mid):
    conn = get_db()
    row = conn.execute("SELECT * FROM migraines WHERE id=?", (mid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_migraine(data):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO migraines (fecha, inicio, fin, intensidad, localizacion,
                               tipo_dolor, aura, medicacion, comentarios)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        data["fecha"], data["inicio"], data.get("fin"),
        data["intensidad"],
        json.dumps(data.get("localizacion", [])),
        data.get("tipo_dolor", ""),
        1 if data.get("aura") else 0,
        data.get("medicacion", ""),
        data.get("comentarios", ""),
    ))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def update_migraine(mid, data):
    conn = get_db()
    fields = []
    params = []
    for k in ("fecha", "inicio", "fin", "intensidad", "tipo_dolor", "aura", "medicacion", "comentarios"):
        if k in data:
            val = data[k]
            if k == "aura":
                val = 1 if val else 0
            fields.append(f"{k}=?")
            params.append(val)
    if "localizacion" in data:
        fields.append("localizacion=?")
        params.append(json.dumps(data["localizacion"]))
    if not fields:
        return
    params.append(mid)
    conn.execute(f"UPDATE migraines SET {','.join(fields)} WHERE id=?", params)
    conn.commit()
    conn.close()


def delete_migraine(mid):
    conn = get_db()
    conn.execute("DELETE FROM migraines WHERE id=?", (mid,))
    conn.commit()
    conn.close()


def get_calendar_data(year, month):
    fecha_desde = f"{year}-{month:02d}-01"
    if month == 12:
        fecha_hasta = f"{year+1}-01-01"
    else:
        fecha_hasta = f"{year}-{month+1:02d}-01"
    conn = get_db()
    rows = conn.execute(
        "SELECT fecha, intensidad, inicio, fin FROM migraines WHERE fecha >= ? AND fecha < ? ORDER BY inicio",
        (fecha_desde, fecha_hasta)
    ).fetchall()
    conn.close()
    by_day = {}
    for r in rows:
        d = r["fecha"]
        if d not in by_day:
            by_day[d] = []
        by_day[d].append(dict(r))
    return by_day


def get_config(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()
