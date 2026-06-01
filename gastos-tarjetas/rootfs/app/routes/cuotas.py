"""
Endpoint /api/cuotas — calcula cuotas pendientes a partir de los gastos.

Detecta tres formatos de cuotas en las descripciones:
  - AMEX explicit:  "DESCRIPCION CUOTA 01/06"  (agregado por el parser amex.py)
  - BBVA / Galicia: "DESCRIPCION 03/12"        (standalone fraction)

Para AMEX, el parser captura la línea de continuación "Cuota NN de NN" y la
normaliza a "CUOTA NN/NN" al final de la descripción.

Para cada compra agrupa por (desc_base, total_cuotas, fuente, moneda, usuario)
y toma el estado más reciente (cuota más alta vista), luego proyecta los
pagos restantes mes a mes.
"""
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Request

from auth import require_auth
from db import list_gastos

router = APIRouter()

# Explicit marker added by parsers (AMEX / BBVA): "CUOTA 01/06"
_CUOTA_CAP = re.compile(r'\bCUOTA\s+(\d{1,3})/(\d{1,3})\b', re.IGNORECASE)
# Galicia-style standalone fraction: "03/12" (not preceded/followed by digit or "/")
_FRAC_CAP  = re.compile(r'(?<![/\d])(\d{1,2})/(\d{2,3})(?![/\d])')
# Date ranges like "04/26 - 03/27" that must NOT be misread as installments
_DATE_RANGE_RE = re.compile(r'\d{1,2}/\d{2,4}\s*[-–]\s*\d{1,2}/\d{2,4}')

# Strip versions for normalising the base description
_CUOTA_STRIP = re.compile(r'\s*\bCUOTA\s+\d{1,3}/\d{1,3}\b\s*', re.IGNORECASE)
_FRAC_STRIP  = re.compile(r'\s*(?<![/\d])\d{1,2}/\d{2,3}(?![/\d])\s*')


def _parse_installment(desc: str):
    """Retorna (cuota_actual, total_cuotas) o None."""
    # Explicit CUOTA marker takes priority (AMEX / BBVA parser output)
    m = _CUOTA_CAP.search(desc)
    if m:
        cur, tot = int(m.group(1)), int(m.group(2))
        if tot >= 2:
            return cur, tot
    # Galicia/BBVA style: remove date ranges first, then search for standalone fractions.
    # Skip if tot >= 25: in a 2-digit suffix that number is almost certainly a year
    # (e.g. "PERSFLOW49010001 03/26" = billing month March 2026, not installment 3/26).
    # Real Argentine installment plans are 2–24 months; 25+ is not a standard plan.
    clean = _DATE_RANGE_RE.sub(' ', desc)
    m = _FRAC_CAP.search(clean)
    if m:
        cur, tot = int(m.group(1)), int(m.group(2))
        if 2 <= tot <= 24 and cur <= tot:
            return cur, tot
    return None


def _base_desc(desc: str) -> str:
    """Elimina el indicador de cuota para obtener la descripción base."""
    d = _CUOTA_STRIP.sub(' ', desc)
    d = _DATE_RANGE_RE.sub(' ', d)   # remove date ranges before stripping fractions
    d = _FRAC_STRIP.sub(' ', d)
    return ' '.join(d.split())


def _add_months(year: int, month: int, n: int) -> str:
    """Retorna YYYY-MM sumando n meses a (year, month)."""
    m0 = month - 1 + n  # 0-indexed
    return f"{year + m0 // 12}-{m0 % 12 + 1:02d}"


@router.get("/cuotas")
def get_cuotas(
    request: Request,
    fuente: Optional[str] = Query(None),
    usuario: Optional[str] = Query(None),
    moneda: Optional[str] = Query(None),
    excluir_especiales: bool = Query(False),
):
    require_auth(request)

    all_gastos = list_gastos(
        fuente=fuente,
        usuario=usuario,
        moneda=moneda,
        excluir_especiales=excluir_especiales,
    )

    # Agrupar por (desc_base, total_cuotas, fuente, moneda, usuario).
    # Dentro de cada grupo conservar la fila con la cuota más alta vista
    # (o la más reciente en caso de empate).
    groups: dict = {}
    for g in all_gastos:
        info = _parse_installment(g['descripcion'])
        if not info:
            continue
        cur, tot = info
        base = _base_desc(g['descripcion'])
        key = (base, tot, g['fuente'], g['moneda'], g.get('usuario') or '')

        prev = groups.get(key)
        if (prev is None
                or cur > prev['cuota_actual']
                or (cur == prev['cuota_actual'] and g['fecha'] > prev['fecha_base'])):
            groups[key] = {
                'descripcion':          base,
                'descripcion_original': g['descripcion'],
                'fuente':               g['fuente'],
                'moneda':               g['moneda'],
                'usuario':              g.get('usuario') or '',
                'categoria':            g.get('categoria') or '',
                'monto_cuota':          float(g['monto']),
                'cuota_actual':         cur,
                'total_cuotas':         tot,
                'fecha_base':           g['fecha'],  # YYYY-MM-DD
            }

    today_ym = f"{date.today().year}-{date.today().month:02d}"

    cuotas = []
    # por_mes: mes -> {mes, total_ars, total_usd, ars_por_fuente, usd_por_fuente}
    por_mes: dict = {}

    for inst in groups.values():
        remaining = inst['total_cuotas'] - inst['cuota_actual']
        if remaining <= 0:
            continue

        try:
            bd = date.fromisoformat(inst['fecha_base'])
        except (ValueError, TypeError):
            continue

        base_year, base_month = bd.year, bd.month

        proyeccion = []
        for i in range(1, remaining + 1):
            mes = _add_months(base_year, base_month, i)
            proyeccion.append({
                'mes':       mes,
                'cuota_num': inst['cuota_actual'] + i,
                'monto':     inst['monto_cuota'],
            })

            if mes not in por_mes:
                por_mes[mes] = {
                    'mes':           mes,
                    'total_ars':     0.0,
                    'total_usd':     0.0,
                    'ars_por_fuente': {},
                    'usd_por_fuente': {},
                }
            pm = por_mes[mes]
            f  = inst['fuente']
            amt = inst['monto_cuota']
            if inst['moneda'] == 'ARS':
                pm['total_ars'] += amt
                pm['ars_por_fuente'][f] = pm['ars_por_fuente'].get(f, 0.0) + amt
            else:
                pm['total_usd'] += amt
                pm['usd_por_fuente'][f] = pm['usd_por_fuente'].get(f, 0.0) + amt

        cuotas.append({
            **inst,
            'restantes':      remaining,
            'total_adeudado': remaining * inst['monto_cuota'],
            'proyeccion':     proyeccion,
        })

    cuotas.sort(key=lambda x: -x['total_adeudado'])

    por_mes_list = sorted(por_mes.values(), key=lambda x: x['mes'])

    # Resúmenes
    proximo_mes_ars = proximo_mes_usd = 0.0
    total_adeudado_ars = total_adeudado_usd = 0.0
    _got_prox_ars = _got_prox_usd = False

    for pm in por_mes_list:
        total_adeudado_ars += pm['total_ars']
        total_adeudado_usd += pm['total_usd']
        if not _got_prox_ars and pm['mes'] >= today_ym and pm['total_ars'] > 0:
            proximo_mes_ars = pm['total_ars']
            _got_prox_ars = True
        if not _got_prox_usd and pm['mes'] >= today_ym and pm['total_usd'] > 0:
            proximo_mes_usd = pm['total_usd']
            _got_prox_usd = True

    return {
        'cuotas':             cuotas,
        'por_mes':            por_mes_list,
        'proximo_mes_ars':    proximo_mes_ars,
        'proximo_mes_usd':    proximo_mes_usd,
        'total_adeudado_ars': total_adeudado_ars,
        'total_adeudado_usd': total_adeudado_usd,
    }
