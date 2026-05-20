import sqlite3
import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Optional

from config import DB_PATH


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
                archivo_origen TEXT
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
            """INSERT INTO gastos (fecha, descripcion, monto, moneda, fuente, categoria, categoria_fuente, archivo_origen)
               VALUES (:fecha, :descripcion, :monto, :moneda, :fuente, :categoria, :categoria_fuente, :archivo_origen)""",
            [{**g, "fecha": str(g["fecha"]), "monto": str(g["monto"])} for g in gastos],
        )
        return conn.execute("SELECT changes()").fetchone()[0]


def list_gastos(fuente: Optional[str] = None, categoria: Optional[str] = None) -> list[dict]:
    query = "SELECT * FROM gastos WHERE 1=1"
    params: list = []
    if fuente:
        query += " AND fuente = ?"
        params.append(fuente)
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    query += " ORDER BY fecha DESC"
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_categoria(gasto_id: int, categoria: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE gastos SET categoria = ?, categoria_fuente = 'manual' WHERE id = ?",
            (categoria, gasto_id),
        )


def delete_gastos_by_archivo(archivo: str):
    with _conn() as conn:
        conn.execute("DELETE FROM gastos WHERE archivo_origen = ?", (archivo,))
