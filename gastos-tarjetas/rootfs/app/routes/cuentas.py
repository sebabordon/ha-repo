from fastapi import APIRouter, HTTPException, Request
from auth import require_auth
from db import get_cuentas, update_cuenta

router = APIRouter()


@router.get("/cuentas")
def list_cuentas(request: Request):
    require_auth(request)
    return get_cuentas()


@router.put("/cuentas/{fuente}")
def put_cuenta(fuente: str, body: dict, request: Request):
    require_auth(request)
    # Fetch current values so callers can send only changed fields
    current = next((c for c in get_cuentas() if c["fuente"] == fuente), None)
    if not current:
        raise HTTPException(404, f"Cuenta {fuente} no encontrada")
    update_cuenta(
        fuente=fuente,
        saldo=float(body.get("saldo", current["saldo"])),
        moneda=body.get("moneda", current["moneda"]),
        activa=int(body.get("activa", current["activa"])),
        auto_saldo=int(body.get("auto_saldo", current["auto_saldo"])),
    )
    return {"ok": True}
