"""
Pagos / vencimientos manuales (feature b2).

CRUD de pagos que no se scrapean (servicios, alquiler, expensas...). Entran al
mismo notifier de antelación que los vencimientos de tarjeta (ver
vencimiento_notifier.py). Todo per-usuario vía el contexto del request.
"""
from datetime import date

from fastapi import APIRouter, Request, HTTPException

from auth import require_auth

router = APIRouter()


def _valid_fecha(s: str) -> str:
    try:
        return date.fromisoformat(str(s)[:10]).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(400, "fecha_vencimiento inválida (usá YYYY-MM-DD)")


@router.get("/pagos")
def get_pagos(request: Request, estado: str = ""):
    require_auth(request)
    from db import list_pagos
    return {"pagos": list_pagos(estado or None)}


@router.post("/pagos")
def post_pago(body: dict, request: Request):
    require_auth(request)
    from db import add_pago
    desc = str(body.get("descripcion", "")).strip()
    if not desc:
        raise HTTPException(400, "Falta la descripción.")
    fecha = _valid_fecha(body.get("fecha_vencimiento", ""))
    try:
        monto = float(body["monto"]) if body.get("monto") not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(400, "monto inválido")
    moneda = "USD" if str(body.get("moneda", "ARS")).upper() == "USD" else "ARS"
    recur  = "mensual" if body.get("recurrencia") == "mensual" else "unico"
    pid = add_pago(desc, monto, moneda, fecha, recur, str(body.get("categoria", "")).strip())
    return {"id": pid}


@router.put("/pagos/{pago_id}")
def put_pago(pago_id: int, body: dict, request: Request):
    require_auth(request)
    from db import update_pago
    fields: dict = {}
    if "descripcion" in body:
        d = str(body["descripcion"]).strip()
        if not d:
            raise HTTPException(400, "La descripción no puede quedar vacía.")
        fields["descripcion"] = d
    if "monto" in body:
        try:
            fields["monto"] = float(body["monto"]) if body["monto"] not in (None, "") else None
        except (TypeError, ValueError):
            raise HTTPException(400, "monto inválido")
    if "moneda" in body:
        fields["moneda"] = "USD" if str(body["moneda"]).upper() == "USD" else "ARS"
    if "fecha_vencimiento" in body:
        fields["fecha_vencimiento"] = _valid_fecha(body["fecha_vencimiento"])
    if "recurrencia" in body:
        fields["recurrencia"] = "mensual" if body["recurrencia"] == "mensual" else "unico"
    if "categoria" in body:
        fields["categoria"] = str(body["categoria"]).strip()
    if "estado" in body and body["estado"] in ("pendiente", "pagado"):
        fields["estado"] = body["estado"]
    update_pago(pago_id, fields)
    return {"ok": True}


@router.post("/pagos/{pago_id}/pagar")
def pagar_pago(pago_id: int, request: Request):
    require_auth(request)
    from db import mark_pago_pagado
    nuevo = mark_pago_pagado(pago_id)
    return {"ok": True, "siguiente": nuevo}


@router.delete("/pagos/{pago_id}")
def del_pago(pago_id: int, request: Request):
    require_auth(request)
    from db import delete_pago
    delete_pago(pago_id)
    return {"ok": True}
