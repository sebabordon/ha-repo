"""
BBVA Argentina savings account (Cuenta Corriente / Caja de Ahorro) PDF parser.

Column layout is calibrated dynamically from the table header row
(the row containing DÉBITO / CRÉDITO / SALDO) so it works regardless of
exact x-coordinates in the specific PDF version. Hardcoded fallbacks are
kept for safety.

Sign convention:
  DÉBITO  → money leaving the account  → stored as negative monto
  CRÉDITO → money entering the account → stored as positive monto
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
    r"^(FECHA|ORIGEN|CONCEPTO|DÉB|DEB|CRÉ|CRED|SALDO|TOTAL|BANCO|EMPRESA|REFERENCIA|MON$|DOCUMENTO|PERÍODO|HOJA)",
    re.IGNORECASE,
)

# Fallback column boundaries (used only when header detection fails)
_DESC_MIN_FB = 100.0
_DEB_MIN_FB  = 380.0
_DEB_MAX_FB  = 470.0
_CRE_MIN_FB  = 470.0
_CRE_MAX_FB  = 560.0


def _norm(s: str) -> str:
    """Uppercase + strip common Spanish accent variations for comparison."""
    return (s.upper()
            .replace("É", "E").replace("Ó", "O")
            .replace("Á", "A").replace("Í", "I").replace("Ú", "U"))


def _detect_columns(pdf):
    """
    Scan first pages for the transaction-table header row.
    Returns (desc_min, deb_min, deb_max, cre_min, cre_max) or None.
    """
    _DEB_KEYS = {"DEBITO", "DEB", "DEBE"}
    _CRE_KEYS = {"CREDITO", "CRED", "HABER"}
    _SAL_KEYS = {"SALDO", "SAL"}

    for page in pdf.pages[:8]:
        words = page.extract_words(keep_blank_chars=False)
        rows = group_by_y(words, tol=3.0)
        for row in rows:
            norms = {_norm(w["text"]): w for w in row}
            deb_w = next((norms[k] for k in _DEB_KEYS if k in norms), None)
            cre_w = next((norms[k] for k in _CRE_KEYS if k in norms), None)
            sal_w = next((norms[k] for k in _SAL_KEYS if k in norms), None)

            if deb_w and cre_w:
                deb_x = deb_w["x0"]
                cre_x = cre_w["x0"]
                sal_x = sal_w["x0"] if sal_w else cre_x + 90

                # description column ends just before the debit column
                desc_end = deb_x - 2

                # Each amount column spans from its header x0 to the next header x0
                deb_min, deb_max = deb_x - 2, cre_x - 2
                cre_min, cre_max = cre_x - 2, sal_x - 2

                return desc_end, deb_min, deb_max, cre_min, cre_max

    return None


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
            col = _detect_columns(pdf)

            if col:
                desc_max, deb_min, deb_max, cre_min, cre_max = col
            else:
                # Fallback: use hardcoded estimates
                desc_max = _DEB_MIN_FB - 2
                deb_min, deb_max = _DEB_MIN_FB, _DEB_MAX_FB
                cre_min, cre_max = _CRE_MIN_FB, _CRE_MAX_FB

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

                    # Description: from left margin up to debit column
                    desc_words = [w for w in row if w["x0"] >= _DESC_MIN_FB and w["x0"] < desc_max]
                    description = " ".join(w["text"] for w in desc_words).strip()
                    if not description or _SKIP_DESC.match(description):
                        continue

                    deb_str = "".join(w["text"] for w in words_in_band(row, deb_min, deb_max))
                    cre_str = "".join(w["text"] for w in words_in_band(row, cre_min, cre_max))

                    deb = parse_ar_amount(deb_str) if deb_str.strip() else None
                    cre = parse_ar_amount(cre_str) if cre_str.strip() else None

                    if cre is not None and cre > 0:
                        gastos.append(self._gasto(fecha, description, cre, Moneda.ARS, filename))
                    elif deb is not None and deb > 0:
                        gastos.append(self._gasto(fecha, description, -deb, Moneda.ARS, filename))

        return gastos
