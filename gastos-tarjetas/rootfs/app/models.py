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
    BBVA_CUENTA = "bbva_cuenta"
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
    descripcion_editada: Optional[str] = None

    class Config:
        json_encoders = {Decimal: str}


class ReglaCategoria(BaseModel):
    palabras: list[str] = []
    patron: Optional[str] = None   # backward compat: old regex-based rules
    categoria: str
    especial: bool = False
    solo_egresos: Optional[bool] = None
    fuentes: list[str] = []


class ReglasCategorias(BaseModel):
    reglas: list[ReglaCategoria] = []


class ReglaEmparejado(BaseModel):
    nombre: str = ""
    patron_a: str = ""
    fuente_a: str = ""   # empty = any fuente
    patron_b: str = ""   # empty = skip side B
    fuente_b: str = ""   # empty = skip side B
    ventana_dias: int = 3
    categoria: str = "Transferencia"


class ReglasEmparejado(BaseModel):
    reglas: list[ReglaEmparejado] = []


class Cuenta(BaseModel):
    fuente: str
    nombre: str
    saldo: float = 0
    moneda: str = "ARS"
    fecha_actualizacion: Optional[str] = None
    activa: int = 1
    auto_saldo: int = 1


class Presupuesto(BaseModel):
    categoria: str
    monto_mensual: float = 0
    moneda: str = "ARS"
