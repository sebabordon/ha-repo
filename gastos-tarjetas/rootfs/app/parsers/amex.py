"""
AMEX Argentina PDF parser.

Format: text-based PDF, transactions as:
  DD de MES  MERCHANT [optional ref]  AMOUNT
Amount words appear at x0 ≥ 490, split by thousands dot.
Large amounts (≥ 12 characters) start slightly to the left (~495) because AMEX
right-aligns them in a fixed-width column that ends at ~542.
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
    group_by_y, parse_ar_amount, parse_date_dmy_long, row_text, words_in_band
)

_TITULAR2_UPPER = TITULAR2_NAME.upper() if TITULAR2_NAME else ""

_DATE_RE = re.compile(r"^(\d{1,2})$")
_SKIP_DESC = re.compile(
    r"^(DE TARJ\.|Referencia|Número de|Socio:|Facturación|Página|The Platinum|Estado de|"
    r"Próxima|Centro|Membership|Información|Saldo Anterior|Limite|Tasa|"
    r"Estimado|American Express|Comprobante|INSTRUCCIONES|PARA EL PAGO|"
    r"Ingresando|través|Con pesos|Recuerde|Importante|American)",
    re.IGNORECASE,
)
# Amount words start at x0 ≥ 490.  AMEX right-aligns amounts in a column that
# ends at ~542pt.  Larger amounts (e.g. "2.362.741,92" — 12 chars) start at
# ~495pt; smaller ones at ~502pt.  Description reference numbers stay below
# x0 ≈ 240pt so 490 is a safe boundary.
_AMOUNT_X = 490.0

# Matches DD/MM/YY or DD/MM/YYYY date tokens in the AMEX header
_AMEX_DATE_RE  = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")
# "- + = 6.722.726,82 01/06/26" — captures amount and optional date (próximo venc)
_AMEX_SALDO_RE = re.compile(r"-\s+\+\s+=\s+([\d.,]+)(?:\s+(\d{2}/\d{2}/\d{2,4}))?")
_AMEX_DATE2_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")


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


def _detect_totals_amex(pdf) -> tuple[Optional["Decimal"], Optional["Decimal"], Optional[_date]]:
    """
    Extract ARS and USD 'saldo a pagar' plus próximo vencimiento from the AMEX
    summary header.

    ARS: line matching '- + = [amount] DD/MM/YY'  (first occurrence = ARS section)
         The DD/MM/YY on this line is the PRÓXIMO VENCIMIENTO (next due date).
    USD: same pattern a few lines later             (second occurrence = USD section)

    Example:
      '- + = 6.722.726,82 01/06/26'   → ARS saldo + próximo venc = 01/06/26
      '- + = cargos recibidos ...'     → (no amount here for USD)
      '5.469,31 28 de Abril 2026'      → USD saldo is on the NEXT line after the '- + =' line
    """
    from parsers.utils import parse_ar_amount
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        lines = text.split("\n")
        ars: Optional["Decimal"] = None
        usd: Optional["Decimal"] = None
        proximo_venc: Optional[_date] = None
        for i, line in enumerate(lines):
            m = _AMEX_SALDO_RE.search(line)
            if m:
                if ars is None:
                    ars = parse_ar_amount(m.group(1))
                    # group(2) is the date suffix — próximo vencimiento
                    if m.group(2):
                        dm = _AMEX_DATE2_RE.match(m.group(2))
                        if dm:
                            d, mo, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                            y = y + 2000 if y < 100 else y
                            try:
                                proximo_venc = _date(y, mo, d)
                            except ValueError:
                                pass
                else:
                    usd = parse_ar_amount(m.group(1))
                    break
            # USD section: "- + = cargos..." puts the amount on the next line
            if ars is not None and usd is None and re.search(r"-\s+\+\s+=", line):
                # Check the NEXT line for a standalone amount
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    first_tok = nxt.split()[0] if nxt.split() else ""
                    if re.match(r"^[\d.,]+$", first_tok):
                        usd = parse_ar_amount(first_tok)
                        break
        if ars is not None:
            return ars, usd, proximo_venc
    return None, None, None


class AmexParser(BaseParser):
    fuente = Fuente.AMEX

    def parse(self, file: BinaryIO, filename: str):
        gastos = []
        current_moneda: Optional[Moneda] = None
        current_usuario: Optional[str] = None  # None → upload default ("Titular")
        facturacion_year: int = 2026

        with pdfplumber.open(file) as pdf:
            self.fecha_vencimiento = _detect_vencimiento_amex(pdf)
            self.stmt_total_ars, self.stmt_total_usd, self.proximo_venc = _detect_totals_amex(pdf)
            self.proximo_cierre = None  # AMEX does not publish the next billing date
            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words)

                for i, row in enumerate(rows):
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
                    if "Total de Cargos en" in rtext or "Fecha y detalle" in rtext or "Total de transacciones" in rtext:
                        current_moneda = None
                        continue

                    # Financial charges section (intereses, IVA) — appears after the
                    # last per-cardholder sub-section, before the USD section.
                    if "Transacciones financieras" in rtext:
                        current_moneda = Moneda.ARS
                        current_usuario = None  # account-level charges → Titular
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

                    # Amount: rightmost words (x0 > _AMOUNT_X).
                    # AMEX marks credits with a "CR" token.  It may appear:
                    #   (a) on the same row as the amount (grouped by group_by_y), or
                    #   (b) on a separate sub-row just below (y-gap > 2pt tolerance).
                    # Collect numeric and CR parts separately so parse_ar_amount
                    # doesn't choke on "1.234,56CR".
                    amount_words = [w for w in row if w["x0"] >= _AMOUNT_X]
                    is_cr = any(w["text"].upper() == "CR" for w in amount_words)

                    # (b) peek at next row: if it's a standalone CR in the amount
                    #     band and not the start of a new transaction, absorb it.
                    if not is_cr and i + 1 < len(rows):
                        nxt = rows[i + 1]
                        nxt_amt = [w for w in nxt if w["x0"] >= _AMOUNT_X]
                        if nxt_amt and all(w["text"].upper() == "CR" for w in nxt_amt):
                            if not _DATE_RE.match(nxt[0]["text"]):
                                is_cr = True

                    numeric_str = "".join(
                        w["text"] for w in amount_words if w["text"].upper() != "CR"
                    )
                    amount = parse_ar_amount(numeric_str) if numeric_str else None
                    if is_cr and amount is not None:
                        amount = -amount   # credit → ingreso (negative monto)
                    if not amount:         # None or zero
                        continue

                    # Description: words between month (index 3) and amount area
                    desc_words = words_in_band(row, row[2]["x1"] + 1, _AMOUNT_X)
                    description = " ".join(w["text"] for w in desc_words).strip()

                    if not description:
                        continue
                    if _SKIP_DESC.match(description):
                        continue
                    # Skip only actual payment rows; "DEV PERCEPCION …" tax credits
                    # are legitimate ingresos and must not be filtered here.
                    if "Gracias por su pago" in description:
                        continue

                    # Clean USD description artefacts: "MERCHANT 31.80 US DOLLA" → "MERCHANT"
                    description = re.sub(r"\s+\d+[.,]\d+\s+US\s+DOLL.*$", "", description)
                    description = re.sub(r"\s+\d+\s+US\s+DOLL.*$", "", description)

                    # Peek at continuation rows for "Cuota NN de NN" installment info.
                    # AMEX renders this on a separate line ~8pt below the transaction line
                    # e.g. "Cuota 02 de 02" (annual fee) or "Plan de Cuotas . Cuota 01 de 03"
                    for j in range(i + 1, min(i + 4, len(rows))):
                        cont_row = rows[j]
                        if not cont_row:
                            break
                        if (_DATE_RE.match(cont_row[0]["text"])
                                and len(cont_row) > 1
                                and cont_row[1]["text"].lower() == "de"):
                            break  # next transaction starts here
                        cont_text = " ".join(w["text"] for w in cont_row)
                        m_cont = re.search(
                            r'\bCuota\s+(\d{1,2})\s+de\s+(\d{1,2})\b',
                            cont_text, re.IGNORECASE,
                        )
                        if m_cont:
                            cur_n = int(m_cont.group(1))
                            tot_n = int(m_cont.group(2))
                            description += f" CUOTA {cur_n:02d}/{tot_n:02d}"
                            break

                    fecha = parse_date_dmy_long(int(first), month_name, facturacion_year)
                    if fecha is None:
                        continue

                    gastos.append(self._gasto(fecha, description, amount, current_moneda, filename, usuario=current_usuario))

        return gastos
