"""
AMEX Argentina PDF parser.

Format: text-based PDF, transactions as:
  DD de MES  MERCHANT [optional ref]  AMOUNT
Amount words appear at x0 > 500, split by thousands dot.
Two sections: "Nuevos Cargos en PESOS" (ARS) and "Nuevos Cargos en DOLARES" (USD).
"""
import re
from datetime import date as _date
from decimal import Decimal
from typing import BinaryIO, Optional

import pdfplumber

from config import TITULAR2_NAME
from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import (
    group_by_y, collect_amount, parse_date_dmy_long, row_text, words_in_band
)

_TITULAR2_UPPER = TITULAR2_NAME.upper() if TITULAR2_NAME else ""

_DATE_RE = re.compile(r"^(\d{1,2})$")
_SKIP_DESC = re.compile(
    r"^(DE TARJ\.|Referencia|Número de|Cuota|Socio:|Facturación|Página|The Platinum|Estado de|"
    r"Próxima|Centro|Membership|Información|Saldo Anterior|Limite|Tasa|Intereses|"
    r"Estimado|American Express|Comprobante|INSTRUCCIONES|PARA EL PAGO|"
    r"Ingresando|través|Con pesos|Recuerde|Importante|American)",
    re.IGNORECASE,
)
_AMOUNT_X = 500.0  # amount words start at x0 > 500

# Matches DD/MM/YY or DD/MM/YYYY date tokens in the AMEX header
_AMEX_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")


def _detect_vencimiento_amex(pdf) -> Optional[_date]:
    """
    Locate the 'Facturación  Vencimiento' column header on page 1, then scan
    the next 5 lines for one containing two DD/MM/YY dates.  The second date
    is the current statement's due date (Vencimiento).

    Example header row : 'Titular  Número de Cuenta  Facturación  Vencimiento'
    Example data row   : 'SEBASTIAN ... 3701-320597-11005  28/04/26  06/05/26'
    Note: there may be an intermediate line ('Argentina') between header and data.
    """
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if re.search(r"Facturaci", line, re.IGNORECASE) and re.search(r"Vencimiento", line, re.IGNORECASE):
                # Scan the next 5 lines for a row with ≥2 dates
                for j in range(i + 1, min(i + 6, len(lines))):
                    matches = _AMEX_DATE_RE.findall(lines[j])
                    if len(matches) >= 2:
                        d, m, y = matches[-1]  # last = Vencimiento column
                        year = int(y) + (2000 if len(y) == 2 else 0)
                        try:
                            return _date(year, int(m), int(d))
                        except ValueError:
                            pass
    return None


class AmexParser(BaseParser):
    fuente = Fuente.AMEX

    def parse(self, file: BinaryIO, filename: str):
        gastos = []
        current_moneda: Optional[Moneda] = None
        current_usuario: Optional[str] = None  # None → upload default ("Titular")
        facturacion_year: int = 2026

        with pdfplumber.open(file) as pdf:
            self.fecha_vencimiento = _detect_vencimiento_amex(pdf)
            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words)

                for row in rows:
                    rtext = row_text(row)

                    # Extract year from statement header
                    m = re.search(r"Facturación\s+\d{2}/\d{2}/(\d{2,4})", rtext)
                    if m:
                        y = int(m.group(1))
                        facturacion_year = y + 2000 if y < 100 else y

                    # Section detection — also detects secondary cardholder name
                    if "Nuevos Cargos en PESOS" in rtext:
                        current_moneda = Moneda.ARS
                        current_usuario = "Adicional" if (_TITULAR2_UPPER and _TITULAR2_UPPER in rtext.upper()) else None
                        continue
                    if "Nuevos Cargos en DOLARES" in rtext or "Nuevos Cargos en DÓLARES" in rtext:
                        current_moneda = Moneda.USD
                        current_usuario = "Adicional" if (_TITULAR2_UPPER and _TITULAR2_UPPER in rtext.upper()) else None
                        continue
                    if "Total de Cargos en" in rtext or "Fecha y detalle" in rtext:
                        current_moneda = None
                        continue

                    if current_moneda is None:
                        continue
                    if not row:
                        continue

                    # Transaction lines start with day number ("04"), "de", month
                    first = row[0]["text"]
                    if not _DATE_RE.match(first):
                        continue
                    if len(row) < 3 or row[1]["text"].lower() != "de":
                        continue

                    month_name = row[2]["text"] if len(row) > 2 else ""

                    # Amount: rightmost words (x0 > _AMOUNT_X)
                    amount = collect_amount(row, _AMOUNT_X)
                    if amount is None or amount <= 0:
                        continue

                    # Description: words between month (index 3) and amount area
                    desc_words = words_in_band(row, row[2]["x1"] + 1, _AMOUNT_X)
                    description = " ".join(w["text"] for w in desc_words).strip()

                    if not description:
                        continue
                    if _SKIP_DESC.match(description):
                        continue
                    # Skip payments and devolutions
                    if "Gracias por su pago" in description or description.startswith("DEV "):
                        continue

                    # Clean USD description artefacts: "MERCHANT 31.80 US DOLLA" → "MERCHANT"
                    description = re.sub(r"\s+\d+[.,]\d+\s+US\s+DOLL.*$", "", description)
                    description = re.sub(r"\s+\d+\s+US\s+DOLL.*$", "", description)

                    fecha = parse_date_dmy_long(int(first), month_name, facturacion_year)
                    if fecha is None:
                        continue

                    gastos.append(self._gasto(fecha, description, amount, current_moneda, filename, usuario=current_usuario))

        return gastos
