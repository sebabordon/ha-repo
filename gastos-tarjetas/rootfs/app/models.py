from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Moneda(str, Enum):
    ARS = "ARS"
    USD = "USD"


class Fuente(str, Enum):
    AMEX = "amex"
    BBVA_MC = "bbva_mc"
    BBVA_VISA = "bbva_visa"
    GALICIA_MC = "galicia_mc"
    MERCADOPAGO = "mercadopago"


class Gasto(BaseModel):
    id: Optional[int] = None
    fecha: date
    descripcion: str
    monto: Decimal
    moneda: Moneda
    fuente: Fuente
    categoria: Optional[str] = None
    categoria_fuente: Optional[str] = None  # "regla", "claude", "manual"
    archivo_origen: Optional[str] = None
    usuario: Optional[str] = None

    class Config:
        json_encoders = {Decimal: str}


class ReglaCategoria(BaseModel):
    palabras: list[str]
    categoria: str


class ReglasCategorias(BaseModel):
    reglas: list[ReglaCategoria] = []
