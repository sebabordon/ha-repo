"""
BBVA Argentina PDF parser (Mastercard Black and Visa Signature).

Both products share the same statement layout:
  FECHA  DESCRIPCIÓN  NRO. CUPÓN  PESOS  DÓLARES
  DD-Mmm-YY  ...      XXXXXX     ARS    [USD]

Column x-boundaries (points):
  date      : x0 ≈ 62,  x1 < 110
  description: x0 ≈ 113, x1 < 390
  coupon    : x0 ≈ 399
  ARS amount: x0 ≈ 456,  x0 < 520
  USD amount: x0 ≈ 551,  x0 >= 520

Taxes (IIBB, IVA, DB.RG, CR.RG) also have DD-Mmm-YY dates;
they are filtered by description prefix.

Installment entries (C.03/12) are assigned to the statement close
date's month/year instead of the original purchase date, so they
appear in the correct billing period.
"""
import calendar
import re
from datetime import date
from typing import BinaryIO, Optional

import pdfplumber

from config import TITULAR2_NAME
from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import (
    collect_amount, group_by_y, parse_ar_amount, parse_date_dmy, row_text, words_in_band
)

_TITULAR2_RE = re.compile(rf"Consumos\s+{re.escape(TITULAR2_NAME)}", re.IGNORECASE) if TITULAR2_NAME else None

_DATE_RE    = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")
_INSTALL_RE = re.compile(r"\s+C\.(\d+)/(\d+)$")
# Only digits, dots, commas and optional leading minus — filters out watermark/letterhead
# text that sometimes bleeds into the amount columns (e.g. "ocnaB" = "Banco" mirrored).
_AMOUNT_WORD_RE = re.compile(r"^-?[\d.,]+$")

# "SU PAGO EN PESOS" / "SU PAGO EN DOLARES" se importan como egresos (monto > 0)
# — el PDF los muestra negativos (crédito sobre la deuda), pero se aplica abs()
# abajo para que queden positivos, consistente con monto > 0 = egreso.
# SALDO / TOTAL CONSUMOS ya están excluidos por el guard _DATE_RE de arriba.
_SKIP_RE = re.compile(r"(?!)")  # nunca hace match — placeholder por si hace falta en el futuro

# Column boundaries
_ARS_X0 = 440.0
_ARS_X1 = 520.0
_USD_X0 = 520.0

# Patterns to find the statement close/end date in PDF header text
# e.g. "AL 31/01/26", "AL 31/01/2026", "CIERRE: 31/01/26"
_STMT_DATE_PATS = [
    re.compile(r"\bAL\s+(\d{2})/(\d{2})/(\d{2,4})\b"),
    re.compile(r"(?:CIERRE|VENCIMIENTO)[:\s]+(\d{2})/(\d{2})/(\d{2,4})", re.IGNORECASE),
]


def _detect_statement_date(pdf) -> Optional[date]:
    """Scan first 3 pages for the statement billing-period end date."""
    for page in pdf.pages[:3]:
        text = page.extract_text() or ""
        for pat in _STMT_DATE_PATS:
            m = pat.search(text)
            if m:
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if year < 100:
                    year += 2000
                try:
                    return date(year, month, day)
                except ValueError:
                    continue
    return None


def _detect_vencimiento_bbva(pdf) -> tuple[Optional[date], Optional[date], Optional["Decimal"], Optional["Decimal"]]:
    """
    Locate the 'CIERRE ACTUAL  VENCIMIENTO ACTUAL' column-header row, then read
    the following data line.
    Returns (fecha_cierre, fecha_venc, saldo_ars, saldo_usd).

    Example header : 'CIERRE ACTUAL VENCIMIENTO ACTUAL SALDO ACTUAL $ SALDO ACTUAL U$S ...'
    Example data   : '21-May-26 03-Jun-26 595.951,81 736,56 375.400,00'
                       idx 0      idx 1    idx 2       idx 3   idx 4

    fecha_cierre (dates[0]) is also used as stmt_date for installment date
    remapping — _detect_statement_date() cannot parse the DD-Mmm-YY format that
    BBVA uses, so we derive it here instead.
    """
    from parsers.utils import parse_ar_amount
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "VENCIMIENTO ACTUAL" in line.upper() and "CIERRE ACTUAL" in line.upper():
                if i + 1 < len(lines):
                    tokens = lines[i + 1].split()
                    dates   = [t for t in tokens if _DATE_RE.match(t)]
                    amounts = [t for t in tokens if _AMOUNT_WORD_RE.match(t) and not _DATE_RE.match(t)]
                    cierre = parse_date_dmy(dates[0]) if len(dates) >= 1 else None
                    venc   = parse_date_dmy(dates[1]) if len(dates) >= 2 else None
                    s_ars  = parse_ar_amount(amounts[0]) if len(amounts) >= 1 else None
                    s_usd  = parse_ar_amount(amounts[1]) if len(amounts) >= 2 else None
                    return cierre, venc, s_ars, s_usd
    return None, None, None, None


def _detect_proximo_bbva(pdf) -> tuple[Optional[date], Optional[date]]:
    """
    Locate the 'PRÓXIMO CIERRE  PRÓXIMO VENCIMIENTO' column header and read the
    data line beneath it.  BBVA prints four dates on that row:
      [cierre_ant]  [venc_ant]  [proximo_cierre]  [proximo_venc]

    Example header : 'CIERRE ANTERIOR VENCIMIENTO ANTERIOR PRÓXIMO CIERRE PRÓXIMO VENCIMIENTO'
    Example data   : '19-Feb-26 02-Mar-26 23-Abr-26 04-May-26'
                       idx 0      idx 1    idx 2       idx 3
    """
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "PRÓXIMO CIERRE" in line.upper() or "PROXIMO CIERRE" in line.upper():
                # Data may be on the same line or on one of the next 3 lines
                for j in range(i + 1, min(i + 4, len(lines))):
                    tokens = lines[j].split()
                    dates = [t for t in tokens if _DATE_RE.match(t)]
                    if len(dates) >= 4:
                        proximo_cierre = parse_date_dmy(dates[2])
                        proximo_venc   = parse_date_dmy(dates[3])
                        return proximo_cierre, proximo_venc
                    if len(dates) >= 2:
                        # Partial match: take last two as próximo cierre/venc
                        proximo_cierre = parse_date_dmy(dates[-2])
                        proximo_venc   = parse_date_dmy(dates[-1])
                        return proximo_cierre, proximo_venc
    return None, None


def _installment_date(original: date, stmt: date) -> date:
    """Return a date in stmt's year/month, capping day to last valid day."""
    last = calendar.monthrange(stmt.year, stmt.month)[1]
    return date(stmt.year, stmt.month, min(original.day, last))


class BBVAParser(BaseParser):
    def __init__(self, fuente: Fuente):
        self.fuente = fuente

    def parse(self, file: BinaryIO, filename: str):
        gastos = []
        current_usuario: Optional[str] = None

        with pdfplumber.open(file) as pdf:
            # _detect_vencimiento_bbva parses DD-Mmm-YY dates (BBVA's format);
            # the old _detect_statement_date() used DD/MM/YY patterns and always
            # returned None for BBVA, leaving stmt_date=None and preventing
            # installment date remapping.
            stmt_date, self.fecha_vencimiento, self.stmt_total_ars, self.stmt_total_usd = _detect_vencimiento_bbva(pdf)
            self.proximo_cierre, self.proximo_venc = _detect_proximo_bbva(pdf)

            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words)

                for row in rows:
                    if not row:
                        continue
                    first = row[0]["text"]
                    rtext = row_text(row)

                    # Section header detection ("Consumos <Name>")
                    if re.match(r"^Consumos\s+\S", rtext, re.IGNORECASE) and not _DATE_RE.match(first):
                        current_usuario = "Adicional" if (_TITULAR2_RE and _TITULAR2_RE.search(rtext)) else None
                        continue

                    # End of named section ("TOTAL CONSUMOS DE …")
                    if re.match(r"TOTAL CONSUMOS DE\b", rtext, re.IGNORECASE):
                        current_usuario = None
                        continue

                    if not _DATE_RE.match(first):
                        continue

                    fecha = parse_date_dmy(first)
                    if fecha is None:
                        continue

                    # Description: words between x0=110 and x0=390 (excludes coupon and amounts)
                    desc_words = words_in_band(row, 110.0, 390.0)
                    desc_raw = " ".join(w["text"] for w in desc_words).strip()

                    # Normalise installment suffix: "C.03/12" → "03/12" at end.
                    # Keeping the fraction makes the cuotas projection work and
                    # prevents conciliation from matching different installments of
                    # the same purchase against each other.
                    m_inst = _INSTALL_RE.search(desc_raw)
                    is_installment = bool(m_inst)
                    if m_inst:
                        base = _INSTALL_RE.sub("", desc_raw).strip()
                        cur_n = int(m_inst.group(1))
                        tot_n = int(m_inst.group(2))
                        description = f"{base} {cur_n:02d}/{tot_n:02d}"
                    else:
                        description = desc_raw

                    if not description or _SKIP_RE.match(description):
                        continue
                    # Skip header/summary rows where description looks like a date or balance
                    if re.match(r"^\d{2}-[A-Za-z]{3}-\d{2}", description):
                        continue

                    # Fix date for installments: use statement month/year
                    if is_installment and stmt_date is not None:
                        fecha = _installment_date(fecha, stmt_date)

                    # Amounts by column — filter out non-numeric words (e.g. mirrored
                    # letterhead/watermark text that bleeds into the amount columns).
                    ars_words = [w for w in words_in_band(row, _ARS_X0, _ARS_X1)
                                 if _AMOUNT_WORD_RE.match(w["text"])]
                    usd_words = [w for w in row
                                 if w["x0"] >= _USD_X0 and _AMOUNT_WORD_RE.match(w["text"])]

                    ars = parse_ar_amount("".join(w["text"] for w in ars_words))
                    usd = parse_ar_amount("".join(w["text"] for w in usd_words))

                    # "SU PAGO EN PESOS/DOLARES": el PDF los muestra como negativos
                    # (crédito sobre el saldo), pero en el sistema deben ser positivos
                    # (egreso = pago de tarjeta) para ser consistentes con la convención
                    # monto > 0 = egreso.  El pago_confirmado usa ABS() así que funciona
                    # con cualquier signo, pero el display en la tab Gastos queda correcto.
                    if re.match(r"^SU PAGO\b", description, re.IGNORECASE):
                        if ars: ars = abs(ars)
                        if usd: usd = abs(usd)

                    # Include both positive (charges) and negative (credits/refunds).
                    # upload.py normalises the sign for all CC sources at import time.
                    if usd:
                        gastos.append(self._gasto(fecha, description, usd, Moneda.USD, filename, usuario=current_usuario))
                    elif ars:
                        gastos.append(self._gasto(fecha, description, ars, Moneda.ARS, filename, usuario=current_usuario))

        return gastos
