"""
Galicia Mastercard Argentina PDF parser.

Layout:
  FECHA  REFERENCIA  COMPROBANTE  PESOS  DÓLARES
  DD-Mmm-YY  ...     XXXXX        ARS    [USD]

Column x-boundaries (points):
  date       : x0 ≈ 22,  x1 < 75
  description: x0 ≈ 79,  x1 < 340
  comprobante: x0 ≈ 340
  ARS amount : x0 ≈ 440,  x0 < 530
  USD amount : x0 >= 530

Installments (CUOTA DEL MES) and automatic debits (DEBITOS AUTOMATICOS):
  - Description contains a "NN/NN" indicator (e.g. "06/06", "03/26") at
    x0 ≈ 160–220, within the description band.
  - The date column shows the *original purchase date*, which may be months
    in the past.  We remap it to the statement month (same as BBVA parser).
  - The NN/NN indicator is kept in the stored description.

Statement close date:
  - Page 1 header row has 6 consecutive DD-Mmm-YY dates; index [2] is the
    cierre date (e.g. "30-Abr-26" for the April 2026 statement).

Commission (COMISION MANT DE CTA) handling:
  - When the user's spending exceeds the threshold, Galicia credits the
    commission back as "BONIF.COM.MEN.MANT.C" in the DETALLE section
    (has a date prefix → parsed as ingreso, negative monto).
  - When spending is below the threshold, the commission + IVA appear only
    in the CONSOLIDADO summary (no date → not in DETALLE rows).  We extract
    them from the page text and add them as egresos at the statement date.
  - Net result: months with bonif → commission shows as egreso + ingreso = 0;
    months without bonif → commission shows as egreso only.

Interest charges (INTERESES DE FINANCIACION / INTERESES PUNITORIOS) handling:
  - These only appear in the CONSOLIDADO summary (no date row in DETALLE).
  - Extracted via regex from the page text and added as separate egresos at
    the statement close date, so they are visible and categorizable.
"""
import calendar
import re
from datetime import date
from typing import BinaryIO, Optional

import pdfplumber

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import (
    group_by_y, parse_ar_amount, parse_date_dmy, words_in_band
)

_DATE_RE        = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")
_AMOUNT_WORD_RE = re.compile(r"^-?[\d.,]+$")

_SKIP_DESC = re.compile(
    r"^(PAGO CAJERO|SALDO|TOTAL|COMISION|SUBTOTAL|CUOTA DEL MES|"
    r"COMPRAS DEL MES|DEBITOS AUTOMATICOS)",
    re.IGNORECASE,
)
# Note: BONIF. is intentionally NOT in _SKIP_DESC — we include it as ingreso.

# Installment indicator inside the description band: NN/NN or NN/NNN
_INSTALL_WORD_RE = re.compile(r"^\d{1,2}/\d{2,3}$")

_ARS_X0 = 440.0
_ARS_X1 = 530.0
_USD_X0 = 530.0

# Patterns to extract charges from the CONSOLIDADO summary text
_COMISION_RE         = re.compile(r"COMISION\s+MANT\s+DE\s+CTA\s+([\d\.]+,\d+)", re.IGNORECASE)
_IVA_RE              = re.compile(r"I\.V\.A\.\s+[\d,]+%\s+([\d\.]+,\d+)", re.IGNORECASE)
_INTERES_FINANC_RE   = re.compile(r"INTERESES\s+DE\s+FINANCIACION\s+([\d\.]+,\d+)", re.IGNORECASE)
_INTERES_PUNITOR_RE  = re.compile(r"INTERESES\s+PUNITORIOS\s+([\d\.]+,\d+)", re.IGNORECASE)
# TOTAL A PAGAR line: "TOTAL A PAGAR 497.631,26 0,00"
_TOTAL_PAGAR_RE = re.compile(r"TOTAL\s+A\s+PAGAR\s+([\d\.]+,\d+)(?:\s+([\d\.]+,\d+))?", re.IGNORECASE)


def _detect_statement_dates(pdf) -> tuple[Optional[date], Optional[date], Optional[date], Optional[date]]:
    """
    Scan first 2 pages for the 6-date timeline row that Galicia prints at the
    top of each page.  Format (graphical labels not extractable by pdfplumber):
      [Cierre Ant]  [Venc Ant]  [Cierre Act]  [Venc Act]  [Próx Cierre]  [Próx Venc]
       26-Mar-26     07-Abr-26   30-Abr-26     11-May-26   28-May-26      08-Jun-26
       idx 0         idx 1       idx 2         idx 3       idx 4          idx 5

    Returns (fecha_cierre, fecha_vencimiento, proximo_cierre, proximo_venc).
    Los dos últimos pueden ser None si la fila trae solo 4 fechas.
    """
    for page in pdf.pages[:2]:
        words = page.extract_words(keep_blank_chars=False)
        rows = group_by_y(words)
        for row in rows:
            date_words = [w["text"] for w in row if _DATE_RE.match(w["text"])]
            if len(date_words) >= 4:
                try:
                    cierre = parse_date_dmy(date_words[2])
                    venc   = parse_date_dmy(date_words[3])
                except Exception:
                    continue
                proximo_cierre = proximo_venc = None
                if len(date_words) >= 6:
                    try:
                        proximo_cierre = parse_date_dmy(date_words[4])
                        proximo_venc   = parse_date_dmy(date_words[5])
                    except Exception:
                        proximo_cierre = proximo_venc = None
                return cierre, venc, proximo_cierre, proximo_venc
    return None, None, None, None


def _detect_total_galicia(pdf) -> tuple[Optional["Decimal"], Optional["Decimal"]]:
    """Extract TOTAL A PAGAR ARS and USD from the CONSOLIDADO summary."""
    from parsers.utils import parse_ar_amount
    for page in pdf.pages[:3]:
        txt = page.extract_text() or ""
        m = _TOTAL_PAGAR_RE.search(txt)
        if m:
            ars = parse_ar_amount(m.group(1))
            usd = parse_ar_amount(m.group(2)) if m.group(2) else None
            return ars, usd
    return None, None


def _extract_comision(pdf) -> Optional[float]:
    """
    Scan CONSOLIDADO section (first 2 pages) for commission + IVA lines.
    Returns the total amount to add as an egreso, or None if not found.
    Both lines may be absent (when the commission was waived via bonif).
    """
    total = 0.0
    found = False
    for page in pdf.pages[:2]:
        txt = page.extract_text() or ""
        m = _COMISION_RE.search(txt)
        if m:
            v = parse_ar_amount(m.group(1))
            if v:
                total += float(v)
                found = True
        m = _IVA_RE.search(txt)
        if m:
            v = parse_ar_amount(m.group(1))
            if v:
                total += float(v)
    return total if found else None


def _extract_intereses(pdf) -> tuple[Optional[float], Optional[float]]:
    """
    Scan CONSOLIDADO section for interest charges that only appear in the
    summary (no date row in DETALLE).  Returns (financiacion, punitorios).
    """
    financiacion = None
    punitorios = None
    for page in pdf.pages[:2]:
        txt = page.extract_text() or ""
        if financiacion is None:
            m = _INTERES_FINANC_RE.search(txt)
            if m:
                v = parse_ar_amount(m.group(1))
                if v:
                    financiacion = float(v)
        if punitorios is None:
            m = _INTERES_PUNITOR_RE.search(txt)
            if m:
                v = parse_ar_amount(m.group(1))
                if v:
                    punitorios = float(v)
    return financiacion, punitorios


def _installment_date(original: date, stmt: date) -> date:
    """Return a date in stmt's year/month, capping day to the last valid day."""
    last = calendar.monthrange(stmt.year, stmt.month)[1]
    return date(stmt.year, stmt.month, min(original.day, last))


class GaliciaParser(BaseParser):
    fuente = Fuente.GALICIA_MC

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        with pdfplumber.open(file) as pdf:
            (stmt_date, self.fecha_vencimiento,
             self.proximo_cierre, self.proximo_venc) = _detect_statement_dates(pdf)
            self.stmt_total_ars, self.stmt_total_usd = _detect_total_galicia(pdf)
            comision  = _extract_comision(pdf)
            interes_financ, interes_punitor = _extract_intereses(pdf)

            # Add commission as egreso at the statement close date (when charged).
            # Months where the bonif appears in DETALLE will produce an offsetting
            # ingreso entry, bringing the net to zero automatically.
            if comision and stmt_date:
                gastos.append(self._gasto(
                    stmt_date, "COMISION MANT DE CTA", comision, Moneda.ARS, filename
                ))

            # Interest charges only appear in CONSOLIDADO (no DETALLE row).
            if interes_financ and stmt_date:
                gastos.append(self._gasto(
                    stmt_date, "INTERESES DE FINANCIACION", interes_financ, Moneda.ARS, filename
                ))
            if interes_punitor and stmt_date:
                gastos.append(self._gasto(
                    stmt_date, "INTERESES PUNITORIOS", interes_punitor, Moneda.ARS, filename
                ))

            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words)

                for row in rows:
                    if not row:
                        continue
                    first = row[0]["text"]

                    if not _DATE_RE.match(first):
                        continue

                    fecha = parse_date_dmy(first)
                    if fecha is None:
                        continue

                    desc_words = words_in_band(row, 75.0, 340.0)
                    desc_raw = " ".join(w["text"] for w in desc_words).strip()

                    # Detect installment: NN/NN word inside the description band
                    is_installment = any(
                        _INSTALL_WORD_RE.match(w["text"]) for w in desc_words
                    )
                    # Keep the NN/NN indicator in the stored description
                    description = desc_raw

                    if not description or _SKIP_DESC.match(description):
                        continue

                    # Remap installment dates to the statement billing month
                    if is_installment and stmt_date is not None:
                        fecha = _installment_date(fecha, stmt_date)

                    ars_words = [w for w in words_in_band(row, _ARS_X0, _ARS_X1)
                                 if _AMOUNT_WORD_RE.match(w["text"])]
                    usd_words = [w for w in row
                                 if w["x0"] >= _USD_X0 and _AMOUNT_WORD_RE.match(w["text"])]

                    ars = parse_ar_amount("".join(w["text"] for w in ars_words))
                    usd = parse_ar_amount("".join(w["text"] for w in usd_words))

                    if usd and usd != 0:
                        gastos.append(self._gasto(fecha, description, usd, Moneda.USD, filename))
                    elif ars and ars != 0:
                        gastos.append(self._gasto(fecha, description, ars, Moneda.ARS, filename))

        return gastos
