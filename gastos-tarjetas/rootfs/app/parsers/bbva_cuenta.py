"""
BBVA Argentina savings account (Cuenta Corriente / Caja de Ahorro) PDF parser.

Layout observations (from real PDFs):
  - Amounts are RIGHT-ALIGNED → a large number's x0 is well to the LEFT of
    its column header, so band/header detection is unreliable.
  - Each transaction row ends with a running SALDO (always the rightmost
    number in the row).
  - Movement amount is everything to the left of SALDO:
      negative  → DÉBITO  (money leaving, stored as negative monto)
      positive  → CRÉDITO (money entering, stored as positive monto)
  - Amount words always contain a comma (Argentine decimal separator ',').
    This reliably distinguishes them from reference codes like '70378120'
    or account numbers like '316-393325/9'.
  - The PDF may contain a second "intervinientes" table (transfer recipients)
    whose date rows only have ONE amount (the transfer value, no SALDO) →
    they are skipped by the "need ≥ 2 amounts" rule.
"""
import re
from datetime import date, datetime
from typing import BinaryIO, Optional

import pdfplumber

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import group_by_y, parse_ar_amount

_DATE_RE = re.compile(r"^\d{2}/\d{2}$")

_SKIP_DESC = re.compile(
    r"^(FECHA|ORIGEN|CONCEPTO|DÉB|DEB|CRÉ|CRED|SALDO|TOTAL|BANCO|EMPRESA|"
    r"REFERENCIA|MON$|DOCUMENTO|PERÍODO|HOJA|ANTERIOR)",
    re.IGNORECASE,
)

# CONCEPTO column starts here; ORIGEN code (x0≈96-132) is excluded.
_DESC_X_MIN = 134.0
# Safe upper bound for description words — amounts never start this early.
_DESC_X_MAX = 340.0
# Amounts can start anywhere right of here (they're right-aligned so x0
# may be left of their column header).
_AMT_X_MIN  = 340.0


def _detect_year(pdf) -> int:
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        m = re.search(r"\b(20\d{2})\b", text)
        if m:
            return int(m.group(1))
    return datetime.now().year


def _parse_date_dm(s: str, year: int) -> Optional[date]:
    try:
        day, month = int(s[:2]), int(s[3:5])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


class BBVACuentaParser(BaseParser):
    fuente = Fuente.BBVA_CUENTA

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        with pdfplumber.open(file) as pdf:
            year = _detect_year(pdf)

            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words, tol=2.0)

                for row in rows:
                    if not row:
                        continue
                    if not _DATE_RE.match(row[0]["text"]):
                        continue

                    fecha = _parse_date_dm(row[0]["text"], year)
                    if fecha is None:
                        continue

                    # ── Description ──────────────────────────────────────────
                    desc_words = [
                        w for w in row
                        if _DESC_X_MIN <= w["x0"] < _DESC_X_MAX
                    ]
                    description = " ".join(w["text"] for w in desc_words).strip()
                    if not description or _SKIP_DESC.match(description):
                        continue

                    # ── Amounts ───────────────────────────────────────────────
                    # Only words that contain ',' (Argentine decimal separator).
                    # This filters out reference numbers, account numbers, etc.
                    amount_candidates = sorted(
                        [
                            (w["x0"], parse_ar_amount(w["text"]))
                            for w in row
                            if w["x0"] >= _AMT_X_MIN and "," in w["text"]
                        ],
                        key=lambda t: t[0],
                    )
                    # Remove unparseable entries
                    amount_candidates = [(x, v) for x, v in amount_candidates if v is not None]

                    # Need at least 2: one movement + one SALDO.
                    if len(amount_candidates) < 2:
                        continue

                    # Rightmost value is always the running SALDO — discard it.
                    movement_amounts = [v for _, v in amount_candidates[:-1]]
                    monto = sum(movement_amounts)

                    if monto > 0:
                        gastos.append(self._gasto(fecha, description, monto, Moneda.ARS, filename))
                    elif monto < 0:
                        gastos.append(self._gasto(fecha, description, monto, Moneda.ARS, filename))
                    # monto == 0 → skip (zero-value or offsetting entries)

        return gastos
