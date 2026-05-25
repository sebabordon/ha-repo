from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import BinaryIO, Optional

from models import Gasto, Fuente, Moneda


class BaseParser(ABC):
    fuente: Fuente
    saldo_final = None                          # account balance detected after parse()
    fecha_vencimiento: Optional[date] = None   # payment due date of the statement
    stmt_total_ars: Optional[Decimal] = None   # SALDO ACTUAL / TOTAL A PAGAR in ARS
    stmt_total_usd: Optional[Decimal] = None   # SALDO ACTUAL / TOTAL A PAGAR in USD

    @abstractmethod
    def parse(self, file: BinaryIO, filename: str) -> list[Gasto]:
        """Parse file and return list of Gasto objects (without categoria)."""
        ...

    def _gasto(self, fecha, descripcion: str, monto: Decimal, moneda: Moneda, archivo: str, usuario: str = None) -> Gasto:
        return Gasto(
            fecha=fecha,
            descripcion=descripcion.strip(),
            monto=monto,
            moneda=moneda,
            fuente=self.fuente,
            archivo_origen=archivo,
            usuario=usuario,
        )
