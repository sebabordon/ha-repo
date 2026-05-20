"""
MercadoPago Argentina XLSX parser.

Export format (row 3 = headers, row 4+ = data):
  RELEASE_DATE  TRANSACTION_TYPE  REFERENCE_ID  TRANSACTION_NET_AMOUNT  PARTIAL_BALANCE

All non-zero transactions are imported.
Negative amounts = debits (egresos); positive = credits (ingresos).
The sign is preserved in monto; categoria_fuente carries "ingreso" / "egreso".
Date format: "DD-MM-YYYY".
Amount format: Argentine "1.234,56" or "-1.234,56".
"""
from datetime import datetime
from decimal import Decimal
from typing import BinaryIO

import openpyxl

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import parse_ar_amount

_HEADER_ROW = 3  # 0-based index of the header row
_COL_DATE   = 0
_COL_TYPE   = 1
_COL_AMOUNT = 3


class MercadoPagoParser(BaseParser):
    fuente = Fuente.MERCADOPAGO

    def parse(self, file: BinaryIO, filename: str):
        gastos = []

        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i <= _HEADER_ROW:
                continue

            raw_date   = row[_COL_DATE]
            raw_type   = str(row[_COL_TYPE] or "").strip()
            raw_amount = str(row[_COL_AMOUNT] or "").strip()

            if not raw_date or not raw_type or not raw_amount:
                continue

            amount = parse_ar_amount(raw_amount)
            if amount is None or amount == 0:
                continue

            try:
                if isinstance(raw_date, datetime):
                    fecha = raw_date.date()
                else:
                    raw_str = str(raw_date).strip()
                    try:
                        fecha = datetime.strptime(raw_str, "%d-%m-%Y").date()
                    except ValueError:
                        fecha = datetime.strptime(raw_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            gastos.append(self._gasto(fecha, raw_type, amount, Moneda.ARS, filename))

        return gastos
