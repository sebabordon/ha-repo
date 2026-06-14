"""
BBVA Argentina savings account (Cuenta Corriente / Caja de Ahorro) PDF parser.

Layout observations (from real PDFs):
  - Amounts are RIGHT-ALIGNED → a large number's x0 is well to the LEFT of
    its column header, so band/header detection is unreliable.
  - Each transaction row ends with a running SALDO (always the rightmost
    number in the row).
  - Movement amount is everything to the left of SALDO:
      negative  → DEBITO  (money leaving, stored as negative monto)
      positive  → CREDITO (money entering, stored as positive monto)
  - Amount words always contain a comma (Argentine decimal separator ',').
    This reliably distinguishes them from reference numbers like '70378120'
    or account numbers like '316-393325/9'.
  - The PDF may contain a second "intervinientes" table (transfer recipients)
    whose date rows only have ONE amount (the transfer value, no SALDO) ->
    they are skipped by the "need >= 2 amounts" rule.

Debit card section ("Tarjetas de Debito"):
  - Date format: DD/MM/YYYY (full year), distinct from movements (DD/MM).
  - Merchant name in COMERCIO column (x0 ~218-405).
  - Amount in IMPORTE column (x0 ~480+), always negative (expense).
  - The same purchases reappear in "Movimientos" as "PAGO CON VISA DEBITO"
    (generic). We use the debit-section entries for the merchant name and
    skip the corresponding duplicate movement rows.
"""
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO, Optional

import pdfplumber

from models import Fuente, Moneda
from parsers.base import BaseParser
from parsers.utils import group_by_y, parse_ar_amount, row_text

# Movements section: date is DD/MM
_DATE_RE = re.compile(r"^\d{2}/\d{2}$")
# Debit card section: date is DD/MM/YYYY
_DEBIT_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_SKIP_DESC = re.compile(
    r"^(FECHA|ORIGEN|CONCEPTO|D[EÉ]B|CR[EÉ]D|SALDO|TOTAL|BANCO|EMPRESA|"
    r"REFERENCIA|MON$|DOCUMENTO|PER[IÍ]ODO|HOJA|ANTERIOR)",
    re.IGNORECASE,
)

# Generic description used for debit-card purchases in the Movimientos section.
# These are duplicates of the richer Tarjetas de Debito section.
_DEBIT_CARD_DESC = re.compile(r"^PAGO CON VISA DEBITO\b", re.IGNORECASE)

# CONCEPTO column starts here; ORIGEN code (x0~96-132) is excluded.
_DESC_X_MIN = 134.0
# Safe upper bound for description words — amounts never start this early.
_DESC_X_MAX = 340.0
# Amounts can start anywhere right of here (right-aligned, so x0 may be
# well left of the column header).
_AMT_X_MIN = 340.0

# Debit card section column boundaries
_COMERCIO_X_MIN = 218.0   # COMERCIO column start
_COMERCIO_X_MAX = 405.0   # COMERCIO column end
_DEBIT_AMT_X_MIN = 480.0  # IMPORTE column start


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


def _parse_date_dmy(s: str) -> Optional[date]:
    """Parse DD/MM/YYYY full date from the Tarjetas de Debito section."""
    try:
        day, month, year = int(s[:2]), int(s[3:5]), int(s[6:10])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def _parse_transfer_details(pdf, year: int) -> dict:
    """
    Lee la sección 'Transferencias' del extracto (subtablas RECIBIDAS y ENVIADAS) y
    devuelve {(fecha, abs_importe): [nombre, ...]} para enriquecer las descripciones
    genéricas 'TRANSFERENCIA' de la sección de movimientos.

    - RECIBIDAS: el nombre es la empresa/servicio de origen (ej. 'INVERTIRONLINE',
      'TARJ VIRTUAL BB'), que aparece entre el código de empresa y 'TR. E/'.
    - ENVIADAS:  el nombre es el apellido del destinatario (ej. 'SAENZ').

    La correlación con el movimiento se hace por fecha (DD/MM) + importe. Se guarda
    una lista por clave para resolver el caso de varias transferencias del mismo
    monto en el mismo día (se consumen en orden).
    """
    details: dict = defaultdict(list)
    section: Optional[str] = None   # 'recibidas' | 'enviadas'
    for page in pdf.pages:
        for line in (page.extract_text() or "").split("\n"):
            up = line.upper()
            if "RECIBIDAS" in up and "INFORMACI" in up:
                section = "recibidas"; continue
            if up.startswith("ENVIADAS"):
                section = "enviadas"; continue
            if up.startswith("LEGALES"):
                section = None; continue
            if up.startswith("FECHA"):
                continue
            if section is None:
                continue
            m = re.match(r"^(\d{2})/(\d{2})\b", line)
            if not m:
                continue
            amts = re.findall(r"[\d.]+,\d{2}", line)
            if not amts:
                continue
            importe = parse_ar_amount(amts[-1])
            fecha = _parse_date_dm(f"{m.group(1)}/{m.group(2)}", year)
            if importe is None or fecha is None:
                continue
            if section == "recibidas":
                nm = re.search(r"^\d{2}/\d{2}\s+\S+\s+\d+\s+(.+?)\s+TR\.\s*E/", line)
            else:
                nm = re.search(r"^\d{2}/\d{2}\s+\d+\s+([A-Za-zÁÉÍÓÚÑáéíóúñ\.\s]+?)\s+\d", line)
            if not nm:
                continue
            nombre = re.sub(r"\s+", " ", nm.group(1).strip())
            if nombre:
                details[(fecha, abs(importe))].append(nombre)
    return details


class BBVACuentaParser(BaseParser):
    fuente = Fuente.BBVA_CUENTA

    def parse(self, file: BinaryIO, filename: str):
        gastos = []
        last_saldo = None

        with pdfplumber.open(file) as pdf:
            year = _detect_year(pdf)

            # Detalle de transferencias (RECIBIDAS/ENVIADAS) para enriquecer las
            # descripciones genéricas "TRANSFERENCIA" con el nombre de la contraparte.
            transfer_details = _parse_transfer_details(pdf, year)

            # ── Pass 1: collect debit-card purchases from "Tarjetas de Debito" ──
            # These have the real merchant name and a full DD/MM/YYYY date.
            # Maps abs(monto) -> list of (fecha, comercio, monto) for dedup.
            debit_purchases: dict[Decimal, list] = defaultdict(list)
            in_debit = False

            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False)
                rows = group_by_y(words, tol=2.0)

                for row in rows:
                    if not row:
                        continue
                    rt = row_text(row)
                    first = row[0]["text"]

                    # Enter debit card sub-section on header rows
                    if re.search(r"Compras\s+Visa\s+D", rt, re.IGNORECASE) or \
                       re.search(r"CUENTA\s+D[EÉ]BITO", rt, re.IGNORECASE):
                        in_debit = True
                        continue

                    # Exit when we reach the next main section heading
                    if in_debit and not _DEBIT_DATE_RE.match(first):
                        if re.match(r"^(Cuentas|Movimientos|CONSOLIDADO|DETALLE)", rt, re.IGNORECASE):
                            in_debit = False
                        continue

                    if not in_debit or not _DEBIT_DATE_RE.match(first):
                        continue

                    fecha = _parse_date_dmy(first)
                    if fecha is None:
                        continue

                    comercio_words = [
                        w for w in row
                        if _COMERCIO_X_MIN <= w["x0"] < _COMERCIO_X_MAX
                    ]
                    comercio = " ".join(w["text"] for w in comercio_words).strip()
                    if not comercio:
                        continue

                    amt_words = [
                        w for w in row
                        if w["x0"] >= _DEBIT_AMT_X_MIN and "," in w["text"]
                    ]
                    monto = parse_ar_amount("".join(w["text"] for w in amt_words))
                    if monto is None or monto == 0:
                        continue

                    debit_purchases[abs(monto)].append((fecha, comercio, monto))

            # Add debit-card purchases with their merchant names
            for entries in debit_purchases.values():
                for fecha, comercio, monto in entries:
                    gastos.append(self._gasto(fecha, comercio, monto, Moneda.ARS, filename))

            # ── Pass 2: "Movimientos en cuentas" ─────────────────────────────────
            # Skip "PAGO CON VISA DEBITO" rows that were already captured above.
            debit_consumed: dict[Decimal, int] = defaultdict(int)

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
                    # Only words containing ',' (Argentine decimal separator).
                    amount_candidates = sorted(
                        [
                            (w["x0"], parse_ar_amount(w["text"]))
                            for w in row
                            if w["x0"] >= _AMT_X_MIN and "," in w["text"]
                        ],
                        key=lambda t: t[0],
                    )
                    amount_candidates = [(x, v) for x, v in amount_candidates if v is not None]

                    # Need at least 2: one movement + one SALDO.
                    if len(amount_candidates) < 2:
                        continue

                    last_saldo = amount_candidates[-1][1]
                    movement_amounts = [v for _, v in amount_candidates[:-1]]
                    monto = sum(movement_amounts)

                    if monto == 0:
                        continue

                    # Skip generic debit-card rows already captured with
                    # merchant names from the Tarjetas de Debito section.
                    if _DEBIT_CARD_DESC.match(description):
                        key = abs(monto)
                        if debit_consumed[key] < len(debit_purchases.get(key, [])):
                            debit_consumed[key] += 1
                            continue

                    # Enriquecer transferencias genéricas con el nombre de la
                    # contraparte tomado de la tabla de detalle (por fecha+importe).
                    if description.upper().startswith("TRANSFERENCIA"):
                        nombres = transfer_details.get((fecha, abs(monto)))
                        if nombres:
                            description = f"{description} — {nombres.pop(0)}"

                    gastos.append(self._gasto(fecha, description, monto, Moneda.ARS, filename))

        # Expose the final running balance so upload.py can persist it.
        if last_saldo is not None:
            self.saldo_final = float(last_saldo)

        return gastos
