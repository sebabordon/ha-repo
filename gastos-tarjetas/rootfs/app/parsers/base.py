from abc import ABC, abstractmethod
from decimal import Decimal
from typing import BinaryIO

from models import Gasto, Fuente, Moneda


class BaseParser(ABC):
    fuente: Fuente
    saldo_final = None  # parsers that can detect a balance set this after parse()

    @abstractmethod
    def parse(self, file: BinaryIO, filename: str) -> list[Gasto]:
        """Parse file and return list of Gasto objects (without categoria)."""
        ...

    def _gasto(self, fecha, descripcion: str, monto: Decimal, moneda: Moneda, archivo: str) -> Gasto:
        return Gasto(
            fecha=fecha,
            descripcion=descripcion.strip(),
            monto=monto,
            moneda=moneda,
            fuente=self.fuente,
            archivo_origen=archivo,
        )
