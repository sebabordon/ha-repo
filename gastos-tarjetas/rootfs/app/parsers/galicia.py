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

Negative amounts (credits/refunds/bonuses) are skipped.
"""
import re
from typing import BinaryIO

import pdfplumber

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import (
    group_by_y, parse_ar_amount, parse_date_dmy, words_in_band
)

_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")

_SKIP_DESC = re.compile(
    r"^(PAGO CAJERO|SALDO|TOTAL|BONIF\.|COMISION|SUBTOTAL|CUOTA DEL MES|"
    r"COMPRAS DEL MES|DEBITOS AUTOMATICOS)",
    re.IGNORECASE,
)

_ARS_X0 = 440.0
_ARS_X1 = 530.0
_USD_X0 = 530.0


class GaliciaParser(BaseParser):
    fuente = Fuente.GALICIA_MC

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        with pdfplumber.open(file) as pdf:
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
                    description = " ".join(w["text"] for w in desc_words).strip()

                    if not description or _SKIP_DESC.match(description):
                        continue

                    ars_words = words_in_band(row, _ARS_X0, _ARS_X1)
                    usd_words = [w for w in row if w["x0"] >= _USD_X0]

                    ars = parse_ar_amount("".join(w["text"] for w in ars_words))
                    usd = parse_ar_amount("".join(w["text"] for w in usd_words))

                    if usd and usd != 0:
                        gastos.append(self._gasto(fecha, description, usd, Moneda.USD, filename))
                    elif ars and ars != 0:
                        gastos.append(self._gasto(fecha, description, ars, Moneda.ARS, filename))

        return gastos
