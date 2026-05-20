## 0.1.5

- Fix cuotas: el parser BBVA ahora detecta la fecha de cierre del resumen (patrón "AL DD/MM/YY" / "CIERRE: DD/MM/YY") y reemplaza el mes/año de los movimientos en cuotas por el del resumen, en lugar del mes de compra original
- Transferencias entre cuentas: botón "🔁 Transferencias" detecta automáticamente pares BBVA Cuenta ↔ MercadoPago con mismo monto (±3 días); al confirmar los marca como categoría "Transferencia" y los excluye del gráfico mensual
- UI responsive para mobile: filtros apilados, chart más compacto, fuentes reducidas, columna Moneda oculta en pantallas pequeñas, tabs scrolleables

## 0.1.4

- Nuevo parser: BBVA Cuenta (caja de ahorro/cuenta corriente PDF) — débito = egreso (negativo), crédito = ingreso (positivo)
- Gráfico mensual ARS arriba de los tabs: barras de Egresos y Ingresos mes a mes
- Filtro por mes: dropdown poblado automáticamente con los meses que tienen datos
- Filtro de categorías tipo slicer: chips multi-seleccionables con las categorías existentes
- Filtros colapsables: botón para mostrar/ocultar el panel de filtros
- Al importar, el chart y las categorías se actualizan automáticamente

## 0.1.3

- Reglas de categorización ahora usan palabras clave en lugar de regex — interfaz de etiquetas, escribís y Enter para agregar
- Nueva columna "Usuario" en gastos (Seba / Mada), auto-asignado por fuente (BBVA y MercadoPago → Seba)
- Exportar gastos a Excel con filtros aplicados
- Corregido crash al cargar rules.yaml con escape inválido (`\+` en string YAML con comillas dobles)

## 0.1.2

- Corregido error de sintaxis YAML en default_rules.yaml (`star\+` en string con comillas dobles)
- `run.sh` valida `rules.yaml` al iniciar y lo reemplaza si está corrupto
- Errores de YAML en reglas ya no crashean la app (devuelve lista vacía)

## 0.1.1

- Corregido loop de redirección 307 con HA Ingress — se lee el header `X-Ingress-Path`
- Rutas JS (fetch) y links de auth usan el prefijo de Ingress
- Corregido crash en upload: `PARSERS[fuente]` es una instancia, no una clase

## 0.1.0

- Parser de extractos PDF: AMEX, BBVA Mastercard, BBVA Visa, Galicia Mastercard
- Parser de exportación XLSX: MercadoPago
- Categorización automática por reglas YAML con fallback opcional a Claude API
- Autenticación local con usuarios `@sbsoft.com.ar`
- Interfaz web con tabs: Gastos / Importar / Reglas
- Compatibilidad aarch64 (Raspberry Pi 5) y amd64
