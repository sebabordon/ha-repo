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

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import (
    collect_amount, group_by_y, parse_ar_amount, parse_date_dmy, row_text, words_in_band
)

_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")
_INSTALL_RE = re.compile(r"\s+C\.(\d+)/(\d+)$")

_TAX_SKIP = re.compile(
    r"^(IIBB|IVA RG|DB\.RG|CR\.RG|SU PAGO|SALDO|TOTAL CONSUMOS|TOTAL DE CARGOS)",
    re.IGNORECASE,
)

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


def _installment_date(original: date, stmt: date) -> date:
    """Return a date in stmt's year/month, capping day to last valid day."""
    last = calendar.monthrange(stmt.year, stmt.month)[1]
    return date(stmt.year, stmt.month, min(original.day, last))


class BBVAParser(BaseParser):
    def __init__(self, fuente: Fuente):
        self.fuente = fuente

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        with pdfplumber.open(file) as pdf:
            stmt_date = _detect_statement_date(pdf)

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

                    # Description: words between x0=110 and x0=390 (excludes coupon and amounts)
                    desc_words = words_in_band(row, 110.0, 390.0)
                    desc_raw = " ".join(w["text"] for w in desc_words).strip()

                    # Detect installment BEFORE stripping suffix
                    is_installment = bool(_INSTALL_RE.search(desc_raw))

                    # Remove installment suffix (C.03/12) from stored description
                    description = _INSTALL_RE.sub("", desc_raw).strip()

                    if not description or _TAX_SKIP.match(description):
                        continue
                    # Skip header/summary rows where description looks like a date or balance
                    if re.match(r"^\d{2}-[A-Za-z]{3}-\d{2}", description):
                        continue

                    # Fix date for installments: use statement month/year
                    if is_installment and stmt_date is not None:
                        fecha = _installment_date(fecha, stmt_date)

                    # Amounts by column
                    ars_words = words_in_band(row, _ARS_X0, _ARS_X1)
                    usd_words = [w for w in row if w["x0"] >= _USD_X0]

                    ars = parse_ar_amount("".join(w["text"] for w in ars_words))
                    usd = parse_ar_amount("".join(w["text"] for w in usd_words))

                    if usd and usd > 0:
                        gastos.append(self._gasto(fecha, description, usd, Moneda.USD, filename))
                    elif ars and ars > 0:
                        gastos.append(self._gasto(fecha, description, ars, Moneda.ARS, filename))

        return gastos
