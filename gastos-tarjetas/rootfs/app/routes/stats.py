from typing import Optional
from fastapi import APIRouter, Request, Query
from auth import require_auth
from db import (
    stats_by_category, stats_by_fuente, stats_by_usuario,
    stats_top_descriptions, stats_monthly_by_category, stats_forecast,
)

router = APIRouter()


@router.get("/stats")
def get_stats(
    request: Request,
    fuente:              Optional[str] = Query(None),
    usuario:             Optional[str] = Query(None),
    mes:                 Optional[str] = Query(None),
    meses:               int  = Query(6),
    moneda:              str  = Query('ARS'),
    excluir_especiales:  bool = Query(True),
    categoria:           Optional[str] = Query(None),
):
    require_auth(request)
    if moneda not in ('ARS', 'USD'):
        moneda = 'ARS'
    kw = dict(fuente=fuente, usuario=usuario, mes=mes, meses=meses, moneda=moneda,
              excluir_especiales=excluir_especiales, categoria=categoria)
    return {
        "by_category":         stats_by_category(**kw),
        "by_fuente":           stats_by_fuente(usuario=usuario, mes=mes, meses=meses, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria),
        "by_usuario":          stats_by_usuario(fuente=fuente, mes=mes, meses=meses, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria),
        "top_descriptions":    stats_top_descriptions(**kw),
        "monthly_by_category": stats_monthly_by_category(fuente=fuente, usuario=usuario, meses=meses, moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria),
    }


@router.get("/stats/forecast")
def get_forecast(
    request: Request,
    meses:        int = Query(6),
    historico:    int = Query(3),
    exclude_cats: Optional[str] = Query(None),
):
    require_auth(request)
    excl = [c.strip() for c in exclude_cats.split(",") if c.strip()] if exclude_cats else None
    return stats_forecast(meses_futuro=meses, meses_historico=historico, exclude_income_cats=excl)
