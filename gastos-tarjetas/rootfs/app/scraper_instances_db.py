"""
CRUD para la tabla `scraper_instances` (v0.4.0+).

Cada instancia representa una configuración independiente de un scraper:
  - Un set de credenciales propio (encriptado o plaintext según SCRAPER_ENCRYPTION_KEY).
  - Su propio schedule, enabled flag y status.
  - Alimenta a una o más cuentas auto-fed (via cuentas.scraper_instance_id).

Con Decision 1=B (1 cuenta = 1 instancia), típicamente cada instancia alimenta
UNA sola cuenta.  Pero el schema permite N cuentas → 1 instancia por flexibilidad
futura (si se quiere consolidar logins).
"""

import json
import logging
from datetime import datetime
from typing import Optional

from scraper_crypto import decrypt_str, encrypt_str
from scrapers_db import _conn   # mismo helper de conexión

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convierte una fila de scraper_instances a dict, descifrando config."""
    if row is None:
        return None
    d = dict(row)
    raw   = d.pop("config", "") or ""
    is_enc = bool(d.pop("config_encrypted", 0))
    try:
        plaintext = decrypt_str(raw, is_enc)
        d["config"] = json.loads(plaintext) if plaintext else {}
    except Exception as exc:
        logger.error(
            "Error decodificando config de instancia id=%s: %s",
            d.get("id"), exc,
        )
        d["config"] = {}
    return d


def list_instances(banco: Optional[str] = None,
                   enabled_only: bool = False) -> list[dict]:
    """Lista todas las instancias (opcionalmente filtradas por banco/enabled)."""
    q = "SELECT * FROM scraper_instances WHERE 1=1"
    params: list = []
    if banco:
        q += " AND banco=?"; params.append(banco)
    if enabled_only:
        q += " AND enabled=1"
    q += " ORDER BY banco, nombre"
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_instance(instance_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scraper_instances WHERE id=?", (instance_id,)
        ).fetchone()
    return _row_to_dict(row)


def get_instance_by_banco_default(banco: str) -> Optional[dict]:
    """
    Devuelve la PRIMERA instancia (por id) del banco dado.  Usado por
    endpoints legacy (/api/scrapers/<banco>/...) que asumen una sola instancia
    por banco — equivale a la "instancia default" creada por la migración.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scraper_instances WHERE banco=? ORDER BY id LIMIT 1",
            (banco,),
        ).fetchone()
    return _row_to_dict(row)


def create_instance(banco: str, nombre: str, config: dict,
                    schedule: Optional[str] = None,
                    enabled: bool = True) -> int:
    """Crea una nueva instancia.  Devuelve su id."""
    config_json = json.dumps(config or {}, ensure_ascii=False)
    config_data, is_enc = encrypt_str(config_json)
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO scraper_instances
               (banco, nombre, config, config_encrypted, schedule, enabled)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (banco, nombre, config_data, 1 if is_enc else 0,
             schedule, 1 if enabled else 0),
        )
        return cur.lastrowid


def update_instance(instance_id: int,
                    nombre: Optional[str] = None,
                    config: Optional[dict] = None,
                    schedule: Optional[str] = None,
                    enabled: Optional[bool] = None) -> bool:
    """Actualiza campos no-None de una instancia.  Re-encripta config si cambia."""
    sets: list[str] = []
    params: list = []
    if nombre is not None:
        sets.append("nombre=?"); params.append(nombre)
    if config is not None:
        config_json = json.dumps(config, ensure_ascii=False)
        config_data, is_enc = encrypt_str(config_json)
        sets.append("config=?"); params.append(config_data)
        sets.append("config_encrypted=?"); params.append(1 if is_enc else 0)
    if schedule is not None:
        sets.append("schedule=?"); params.append(schedule)
    if enabled is not None:
        sets.append("enabled=?"); params.append(1 if enabled else 0)
    if not sets:
        return False
    sets.append("updated_at=?"); params.append(datetime.utcnow().isoformat())
    params.append(instance_id)
    with _conn() as conn:
        cur = conn.execute(
            f"UPDATE scraper_instances SET {', '.join(sets)} WHERE id=?",
            params,
        )
        return cur.rowcount > 0


def delete_instance(instance_id: int) -> bool:
    """
    Borra una instancia.  Las cuentas que la referenciaban quedan con
    scraper_instance_id=NULL (efectivamente "sin scraper", siguen siendo
    cuentas auto pero sin alimentación automática).
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE cuentas SET scraper_instance_id=NULL, scraper_product_key=NULL "
            "WHERE scraper_instance_id=?",
            (instance_id,),
        )
        cur = conn.execute("DELETE FROM scraper_instances WHERE id=?", (instance_id,))
        return cur.rowcount > 0


def update_instance_status(instance_id: int, **fields) -> None:
    """
    Actualiza campos de status (ultimo_run/ok/estado/error_msg/saldos/etc.).
    Lo separamos de update_instance para no re-encriptar config en cada run.

    Mirror legacy: también actualiza la tabla `scraper_status` (keyed por banco)
    para que el UI viejo (`/api/scrapers/status`) siga funcionando sin cambios
    mientras v0.4.0 conserve back-compat con la tab Scrapers existente.
    """
    allowed = {
        "ultimo_run", "ultimo_ok", "estado", "error_msg",
        "saldo_ars", "saldo_usd", "movimientos_nuevos", "last_log",
    }
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k}=?"); params.append(v)
    if not sets:
        return

    # Update en scraper_instances
    with _conn() as conn:
        params_inst = list(params) + [instance_id]
        conn.execute(
            f"UPDATE scraper_instances SET {', '.join(sets)} WHERE id=?",
            params_inst,
        )
        # Mirror al legacy scraper_status (keyed por banco) sólo si esta es la
        # primera/única instancia del banco (la "default"). Si hay multi-instancia,
        # el legacy scraper_status muestra el status de la default — el UI nuevo
        # de v0.4.1 leerá directo de scraper_instances.
        row = conn.execute(
            "SELECT banco FROM scraper_instances WHERE id=?", (instance_id,)
        ).fetchone()
        if row:
            banco = row["banco"]
            first = conn.execute(
                "SELECT id FROM scraper_instances WHERE banco=? ORDER BY id LIMIT 1",
                (banco,),
            ).fetchone()
            if first and first["id"] == instance_id:
                # Esta es la default → mirror a scraper_status
                try:
                    from scrapers_db import upsert_scraper_status
                    mirror_fields = {k: v for k, v in fields.items() if k in allowed}
                    upsert_scraper_status(banco, **mirror_fields)
                except Exception:
                    pass  # no crítico


def get_cuentas_for_instance(instance_id: int) -> list[dict]:
    """
    Devuelve las cuentas que están mapeadas a esta instancia, con su
    `product_key`.  El scraper usa esta lista para saber qué productos
    procesar y a qué fuente emitir los movimientos.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT fuente, nombre, moneda, scraper_product_key AS product_key "
            "FROM cuentas WHERE scraper_instance_id=? AND activa=1",
            (instance_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_instance_for_cuenta(fuente: str) -> Optional[dict]:
    """Devuelve la instancia (con config descifrada) que alimenta esta cuenta."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT si.* FROM scraper_instances si "
            "JOIN cuentas c ON c.scraper_instance_id = si.id "
            "WHERE c.fuente=?",
            (fuente,),
        ).fetchone()
    return _row_to_dict(row)


def link_cuenta(cuenta_fuente: str, instance_id: int, product_key: str) -> None:
    """Asigna una cuenta a una instancia con un product_key."""
    with _conn() as conn:
        conn.execute(
            "UPDATE cuentas SET scraper_instance_id=?, scraper_product_key=? "
            "WHERE fuente=?",
            (instance_id, product_key, cuenta_fuente),
        )


def unlink_cuenta(cuenta_fuente: str) -> None:
    """Desasigna una cuenta de cualquier instancia (queda sin auto-feed)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE cuentas SET scraper_instance_id=NULL, scraper_product_key=NULL "
            "WHERE fuente=?",
            (cuenta_fuente,),
        )
