from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional
import re

_MONTHS = {
    "Ene": 1, "Jan": 1, "Feb": 2, "Mar": 3,
    "Abr": 4, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Aug": 8, "Sep": 9,
    "Oct": 10, "Nov": 11, "Dic": 12, "Dec": 12,
}

_MONTHS_ES_LONG = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4,
    "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8,
    "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
}


def group_by_y(words, tol: float = 2.0):
    """
    Group pdfplumber word dicts into rows using a tolerance window.
    BBVA PDFs render date, description, and amount at slightly different
    baselines (up to ~0.6pt apart) — rounding to integers splits them.
    tol=2.0 merges sub-pixel offsets while keeping separate rows apart
    (inter-row gaps in BBVA are ~12pt).
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: w["top"])
    rows: list = []
    current_row = [sorted_words[0]]
    row_start_y = sorted_words[0]["top"]

    for w in sorted_words[1:]:
        if w["top"] - row_start_y <= tol:
            current_row.append(w)
        else:
            rows.append(sorted(current_row, key=lambda w: w["x0"]))
            current_row = [w]
            row_start_y = w["top"]

    if current_row:
        rows.append(sorted(current_row, key=lambda w: w["x0"]))
    return rows


def parse_ar_amount(s: str) -> Optional[Decimal]:
    """Parse Argentine number format: '1.234.567,89' → Decimal('1234567.89')"""
    s = s.strip().replace(" ", "")
    if not s:
        return None
    try:
        if "," in s:
            int_part, dec_part = s.rsplit(",", 1)
            int_part = int_part.replace(".", "")
            s = f"{int_part}.{dec_part}"
        else:
            s = s.replace(".", "")
        d = Decimal(s)
        return d
    except (InvalidOperation, ValueError):
        return None


def parse_date_dmy(s: str) -> Optional[date]:
    """Parse 'DD-Mmm-YY' (e.g. '07-Feb-26') → date(2026, 2, 7)"""
    m = re.match(r"^(\d{2})-([A-Za-zé]{3})-(\d{2})$", s)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2).capitalize(), 0)
    year = int(m.group(3)) + 2000
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_dmy_long(day: int, month_name: str, year: int) -> Optional[date]:
    """Parse AMEX date parts: day=7, month_name='Febrero', year=2026."""
    month = _MONTHS_ES_LONG.get(month_name.capitalize(), 0)
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def row_text(row_words: list) -> str:
    return " ".join(w["text"] for w in row_words)


def words_in_band(row_words: list, x_min: float, x_max: float) -> list:
    return [w for w in row_words if x_min <= w["x0"] < x_max]


def collect_amount(row_words: list, x_min: float) -> Optional[Decimal]:
    """Collect and join all word texts at x0 >= x_min, then parse as AR amount."""
    parts = [w["text"] for w in row_words if w["x0"] >= x_min]
    if not parts:
        return None
    return parse_ar_amount("".join(parts))
