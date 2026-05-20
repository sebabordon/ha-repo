"""
BBVA Argentina savings account (Cuenta Corriente / Caja de Ahorro) PDF parser.

Main transaction table layout (points):
  FECHA (DD/MM)  x0 ≈  62
  ORIGEN (code)  x0 ≈  96   (3-digit code, skipped)
  CONCEPTO       x0 ≈ 134,  end < 407
  DÉBITO         x0 407–473  → negative monto (egreso: money leaving account)
  CRÉDITO        x0 474–551  → positive monto  (ingreso: money entering account)
  SALDO          x0 ≥ 552    → skipped
"""
import re
from datetime import date, datetime
from typing import BinaryIO, Optional

import pdfplumber

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import group_by_y, parse_ar_amount, words_in_band

_DATE_RE = re.compile(r"^\d{2}/\d{2}$")

_SKIP_DESC = re.compile(
    r"^(FECHA|ORIGEN|CONCEPTO|DÉB|DEB|CRÉ|CRED|SALDO|TOTAL|BANCO|EMPRESA|REFERENCIA|MON$|DOCUMENTO)",
    re.IGNORECASE,
)

_DESC_MIN = 134.0
_DESC_MAX = 407.0
_DEB_MIN  = 407.0
_DEB_MAX  = 474.0
_CRE_MIN  = 474.0
_CRE_MAX  = 552.0


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

                    desc_words = words_in_band(row, _DESC_MIN, _DESC_MAX)
                    description = " ".join(w["text"] for w in desc_words).strip()
                    if not description or _SKIP_DESC.match(description):
                        continue

                    deb = parse_ar_amount("".join(w["text"] for w in words_in_band(row, _DEB_MIN, _DEB_MAX)))
                    cre = parse_ar_amount("".join(w["text"] for w in words_in_band(row, _CRE_MIN, _CRE_MAX)))

                    if cre is not None and cre > 0:
                        gastos.append(self._gasto(fecha, description, cre, Moneda.ARS, filename))
                    elif deb is not None and deb > 0:
                        gastos.append(self._gasto(fecha, description, -deb, Moneda.ARS, filename))

        return gastos
