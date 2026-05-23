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

_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")

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

# Patterns to extract commission + IVA from the CONSOLIDADO summary text
_COMISION_RE = re.compile(r"COMISION\s+MANT\s+DE\s+CTA\s+([\d\.]+,\d+)", re.IGNORECASE)
_IVA_RE      = re.compile(r"I\.V\.A\.\s+[\d,]+%\s+([\d\.]+,\d+)", re.IGNORECASE)


def _detect_statement_date(pdf) -> Optional[date]:
    """
    Scan first 2 pages for the 6-date header row that Galicia prints at the
    top of each page.  Its format is:
      26-Mar-26  07-Abr-26  30-Abr-26  11-May-26  28-May-26  08-Jun-26
    Index 2 (0-based) is the statement close date (fecha de cierre).
    """
    for page in pdf.pages[:2]:
        words = page.extract_words(keep_blank_chars=False)
        rows = group_by_y(words)
        for row in rows:
            date_words = [w["text"] for w in row if _DATE_RE.match(w["text"])]
            if len(date_words) >= 4:
                try:
                    return parse_date_dmy(date_words[2])
                except Exception:
                    continue
    return None


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


def _installment_date(original: date, stmt: date) -> date:
    """Return a date in stmt's year/month, capping day to the last valid day."""
    last = calendar.monthrange(stmt.year, stmt.month)[1]
    return date(stmt.year, stmt.month, min(original.day, last))


class GaliciaParser(BaseParser):
    fuente = Fuente.GALICIA_MC

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        with pdfplumber.open(file) as pdf:
            stmt_date = _detect_statement_date(pdf)
            comision  = _extract_comision(pdf)

            # Add commission as egreso at the statement close date (when charged).
            # Months where the bonif appears in DETALLE will produce an offsetting
            # ingreso entry, bringing the net to zero automatically.
            if comision and stmt_date:
                gastos.append(self._gasto(
                    stmt_date, "COMISION MANT DE CTA", comision, Moneda.ARS, filename
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

                    ars_words = words_in_band(row, _ARS_X0, _ARS_X1)
                    usd_words = [w for w in row if w["x0"] >= _USD_X0]

                    ars = parse_ar_amount("".join(w["text"] for w in ars_words))
                    usd = parse_ar_amount("".join(w["text"] for w in usd_words))

                    if usd and usd != 0:
                        gastos.append(self._gasto(fecha, description, usd, Moneda.USD, filename))
                    elif ars and ars != 0:
                        gastos.append(self._gasto(fecha, description, ars, Moneda.ARS, filename))

        return gastos
